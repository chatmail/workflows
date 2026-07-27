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
from pathlib import Path

RUFF_VERSION = "0.16.0"  # keep in sync with py-checks.yml default


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


def get_project_name():
    """Reads the project name from pyproject.toml."""
    import tomllib

    with open("pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["name"]


def get_current_version():
    """Gets the latest version tag from git."""
    try:
        tag = run(["git", "describe", "--tags", "--abbrev=0"], capture=True)
        return tag.lstrip("v")
    except subprocess.CalledProcessError:
        return "0.0.0"


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
        print("--- Running pytest ---")
        if run(["uvx", "--with-editable", ".", "pytest"]) != 0:
            print("Error: tests failed (use --skip-tests to override).")
            sys.exit(1)


def update_changelog(tag):
    """Prepends the release section via git-cliff, if configured."""
    if not Path("cliff.toml").exists():
        print("No cliff.toml; skipping changelog generation (edit by hand).")
        return False
    if (
        run(["git", "cliff", "--unreleased", "--tag", tag, "--prepend", "CHANGELOG.md"])
        != 0
    ):
        print("Error: git-cliff failed.")
        sys.exit(1)
    import os
    import shlex

    editor = os.environ.get("VISUAL", os.environ.get("EDITOR", "vi"))
    run([*shlex.split(editor), "CHANGELOG.md"])
    return True


def main():
    name = get_project_name()
    check_clean_main()

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

    push_cmd = f"git push origin main {tag}"
    if not ask(f"\nPush release? Will run: {push_cmd}\n[y/N]: "):
        print(f"Release {tag} created locally but NOT pushed.")
        print(f"When ready: {push_cmd}")
        return
    if run(["git", "push", "origin", "main", tag]) != 0:
        print("Error: push failed; commit and tag exist locally.")
        sys.exit(1)

    print(f"\nPushed {tag}; the release.yml workflow now builds and")
    print(f"publishes {name} {next_ver} to PyPI via trusted publishing.")


if __name__ == "__main__":
    main()
