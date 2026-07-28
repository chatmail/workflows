#!/usr/bin/env python3
"""Generic release driver for chatmail Python projects.

Run from the root of a project repository (cmsend, cmping, cmtop, ...):

    python /path/to/workflows/scripts/make_new_release.py

It gates on lint/format/tests, picks the next version, updates the
changelog (via git-cliff if a cliff.toml is present), creates a
"chore: release vX.Y.Z" commit plus an annotated vX.Y.Z tag, and
offers to push. The actual PyPI upload happens in CI: pushing the tag
triggers the repo's release.yml, which builds and publishes via
trusted publishing (OIDC). No twine, no local credentials.

Projects with heavier release gates (e.g. cmlxc's Incus fullrun) keep
their own specialized script.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

RUFF_VERSION = "0.16.0"  # keep in sync with py-checks.yml default
GIT_CLIFF_VERSION = "2.13.1"


def run(cmd, capture=False):
    """Run a command, returning output (capture=True) or the exit code."""
    print(f"$ {' '.join(cmd)}")
    if capture:
        return subprocess.check_output(cmd, text=True).strip()
    return subprocess.run(cmd, check=False).returncode


def ask(prompt):
    """Prompt the user for yes/no confirmation."""
    try:
        return input(prompt).strip().lower() == "y"
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)


def read_pyproject():
    """Reads pyproject.toml of the current project."""
    import tomllib

    with open("pyproject.toml", "rb") as f:
        return tomllib.load(f)


def get_project_name():
    """Reads the project name from pyproject.toml."""
    return read_pyproject()["project"]["name"]


def get_test_dependencies():
    """Returns the "test" dependency group, as py-checks installs it."""
    return read_pyproject().get("dependency-groups", {}).get("test", [])


def get_tagged_versions():
    """Returns all released versions, as (major, minor, micro) tuples.

    Both "1.2.3" and "v1.2.3" tags count: repositories that switched to
    the v prefix still have older unprefixed tags.
    """
    versions = []
    for tag in run(["git", "tag"], capture=True).split():
        match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", tag)
        if match:
            versions.append(tuple(int(part) for part in match.groups()))
    return versions


def get_release_tag_at_head():
    """Returns the vX.Y.Z tag pointing at HEAD, if there is one.

    A tagged HEAD means an earlier run got as far as committing and
    tagging but did not push, typically because branch protection
    rejected the branch.
    """
    for tag in run(["git", "tag", "--points-at", "HEAD"], capture=True).split():
        if re.fullmatch(r"v\d+\.\d+\.\d+", tag):
            return tag
    return None


def remote_has_tag(tag):
    """Tells whether origin already carries the tag."""
    return bool(run(["git", "ls-remote", "--tags", "origin", tag], capture=True))


def remote_main_is_at_head():
    """Tells whether origin's main is the commit checked out here."""
    remote = run(["git", "ls-remote", "origin", "refs/heads/main"], capture=True)
    if not remote:
        return False
    return remote.split()[0] == run(["git", "rev-parse", "HEAD"], capture=True)


def get_current_version():
    """Gets the highest released version.

    Deliberately not "git describe": that only sees tags reachable from
    HEAD, and would happily propose a version that was already released
    from a branch which never got merged.
    """
    versions = get_tagged_versions()
    return ".".join(str(part) for part in max(versions)) if versions else "0.0.0"


def bump_version(current, part):
    """Calculates the next version according to 0.X.Y rules."""
    parts = list(map(int, current.split(".")))
    while len(parts) < 3:
        parts.append(0)
    _major, minor, micro = parts
    if part == "minor":
        return f"0.{minor + 1}.0"
    return f"0.{minor}.{micro + 1}"


def check_clean_main():
    if not Path("cliff.toml").exists():
        print("Error: no cliff.toml, which git-cliff needs to write the")
        print("changelog. Copy one from a sibling repository and adapt the")
        print("repository URL in its commit_preprocessors.")
        sys.exit(1)
    branch = run(["git", "branch", "--show-current"], capture=True)
    if branch != "main":
        print(f"Error: not on branch 'main' (currently on {branch!r}).")
        sys.exit(1)
    if (
        run(["git", "diff", "--quiet"]) != 0
        or run(["git", "diff", "--cached", "--quiet"]) != 0
    ):
        print("Error: uncommitted changes in the repository.")
        sys.exit(1)


def run_checks(skip_tests):
    print("--- Running ruff checks ---")
    ruff = f"ruff@{RUFF_VERSION}"
    if run(["uvx", ruff, "check", "."]) != 0:
        print("Error: ruff check failed.")
        sys.exit(1)
    if run(["uvx", ruff, "format", "--check", "."]) != 0:
        print("Error: ruff format check failed (run: uvx ruff format .).")
        sys.exit(1)

    if skip_tests:
        return
    has_tests = Path("tests").is_dir() or list(Path(".").glob("test_*.py"))
    if has_tests:
        run_tests_against_built_package()


def run_tests_against_built_package():
    """Runs the tests against the wheel that would be released.

    Building first and installing the wheel non-editable into a fresh
    environment catches packaging mistakes that an editable install of
    the working tree hides, such as files missing from the wheel.
    """
    print("--- Building the package to test ---")
    with tempfile.TemporaryDirectory() as tmp:
        if run(["uv", "build", "--out-dir", tmp]) != 0:
            print("Error: building the package failed.")
            sys.exit(1)
        wheels = list(Path(tmp).glob("*.whl"))
        if len(wheels) != 1:
            print(f"Error: expected exactly one wheel, got {wheels}.")
            sys.exit(1)

        print("--- Running pytest against the built wheel ---")
        cmd = ["uvx", "--with", str(wheels[0]), "--with", "pytest"]
        for dep in get_test_dependencies():
            cmd += ["--with", dep]
        # Without importlib mode pytest puts the repository first on
        # sys.path, so the sources would shadow the installed wheel.
        cmd += ["pytest", "--import-mode=importlib"]
        # Exit code 5 means "no tests collected", like in py-checks.
        if run(cmd) not in (0, 5):
            print("Error: tests failed (use --skip-tests to override).")
            sys.exit(1)


def update_changelog(tag):
    """Generates the release section and opens it for editing.

    git-cliff prepends the section derived from the Conventional
    Commits since the last tag, then the changelog is opened in the
    editor. Returns True if it ended up differing from HEAD.
    """
    print("--- Generating CHANGELOG.md ---")
    cliff = ["uvx", f"git-cliff@{GIT_CLIFF_VERSION}"]
    if run([*cliff, "--unreleased", "--tag", tag, "--prepend", "CHANGELOG.md"]) != 0:
        print("Error: git-cliff failed.")
        sys.exit(1)

    import os
    import shlex

    editor = os.environ.get("VISUAL", os.environ.get("EDITOR", "vi"))
    print(f"--- Opening CHANGELOG.md in {editor} for the {tag} entry ---")
    run([*shlex.split(editor), "CHANGELOG.md"])

    if run(["git", "diff", "--quiet", "--", "CHANGELOG.md"]) == 0:
        print("CHANGELOG.md was left unchanged.")
        return False
    return True


def push_release(name, tag):
    """Pushes the release commit and its tag together.

    --atomic so a branch rejected by branch protection cannot leave the
    tag pushed on its own, which would publish a release from a commit
    that is not on main. Pushing a ref that origin already has is a
    no-op, which is what makes an interrupted release resumable.
    """
    push_cmd = f"git push --atomic origin main {tag}"
    if not ask(f"\nPush release? Will run: {push_cmd}\n[y/N]: "):
        print(f"Release {tag} exists locally but was NOT pushed.")
        print(f"When ready: {push_cmd}")
        return
    if run(["git", "push", "--atomic", "origin", "main", tag]) != 0:
        print("\nError: push failed; commit and tag exist only locally.")
        print("Nothing was published. If main is protected and rejected")
        print("the push, allow it in the repository ruleset, then run")
        print("this script again to resume.")
        sys.exit(1)

    print(f"\nPushed {tag}; the release.yml workflow now builds and")
    print(f"publishes {name} {tag.lstrip('v')} to PyPI via trusted publishing.")


def resume_release(name, tag):
    """Finishes a release whose commit and tag exist but were not pushed."""
    tag_pushed = remote_has_tag(tag)
    if tag_pushed and remote_main_is_at_head():
        print(f"\n{tag} and main are both on origin: this release is complete.")
        print("Commit further work before releasing again.")
        return

    print(f"\nHEAD is already tagged {tag}: resuming that release.")
    print("Checks ran before the tag was created and are not repeated.")
    if tag_pushed:
        print(f"\nNote: origin already has {tag}. Pushing main completes the")
        print("repository state but does not re-trigger release.yml. To make")
        print(f"the release run again: git push --delete origin {tag}, then")
        print("run this script again.")
    push_release(name, tag)


def main():
    name = get_project_name()
    check_clean_main()

    # An earlier run may have committed and tagged but failed to push.
    tag_at_head = get_release_tag_at_head()
    if tag_at_head:
        resume_release(name, tag_at_head)
        return

    skip_tests = "--skip-tests" in sys.argv
    run_checks(skip_tests)

    current = get_current_version()
    print(f"\nProject: {name}, current version: v{current}")
    minor_next = bump_version(current, "minor")
    micro_next = bump_version(current, "micro")
    print(f"  1. Minor (new functionality): v{minor_next}")
    print(f"  2. Micro (fixes only):        v{micro_next}")
    choice = input("Select version (default 2) or enter custom: ").strip()
    if choice in ("", "2"):
        next_ver = micro_next
    elif choice == "1":
        next_ver = minor_next
    else:
        next_ver = choice.lstrip("v")
    if not re.match(r"^\d+\.\d+\.\d+$", next_ver):
        print(f"Error: {next_ver!r} is not an X.Y.Z version.")
        sys.exit(1)
    tag = f"v{next_ver}"

    # A version that was already tagged is already on PyPI, where
    # uploads are immutable: publishing would silently skip the files.
    if tuple(int(part) for part in next_ver.split(".")) in get_tagged_versions():
        print(f"Error: {next_ver} was already released (tag exists).")
        sys.exit(1)

    if not ask(f"\nProceed with release {tag}? [y/N]: "):
        print("Cancelled.")
        return

    changed = update_changelog(tag)
    if changed:
        run(["git", "add", "CHANGELOG.md"])
        if run(["git", "commit", "-m", f"chore: release {tag}"]) != 0:
            print("Error: release commit failed.")
            sys.exit(1)

    if run(["git", "tag", "-a", tag, "-m", f"Release {tag}"]) != 0:
        print("Error: tag creation failed.")
        sys.exit(1)

    push_release(name, tag)


if __name__ == "__main__":
    main()
