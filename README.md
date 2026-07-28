# chatmail workflows: shared CI and releasing for Python projects

Central home for everything shareable between chatmail Python projects:
a reusable GitHub Actions workflow for all Python checks, caller
templates, and the release script that every project releases with.


## What is here

- `.github/workflows/py-checks.yml`
  The reusable workflow. In one job, and in this order, it runs:

  - `ruff check` and `ruff format --check` (ruff version pinned
    centrally in this file)

  - `uv build` plus `twine check`, uploading the distributions as a
    `dist` artifact for release workflows

  - pytest

  Each is a separate step, so a failing run names the step that
  failed.

- `templates/ci.yml`, `templates/release.yml` and `templates/cliff.toml`
  Copy-paste starting points for consuming repositories.

- `scripts/make_new_release.py`
  The way releases are made. See "Releasing" below.


## py-checks inputs

Both optional:

| input            | default  | purpose                               |
|------------------|----------|---------------------------------------|
| `python-version` | `"3.11"` | Python used for tests and build       |
| `pytest`         | `true`   | set `false` for test suites that need live infrastructure |

The default Python is the 3.11 line that Debian 12 ships (CI uses
the newest available 3.11.x build).


## Testing standard

pytest is the test runner for all chatmail Python projects and runs
by default on a plain ubuntu-latest runner. A repository without
tests passes without configuration ("no tests collected" is fine).
Repositories whose only tests need live infrastructure (a deployed
relay, containers) set `pytest: false` in their stubs.

pyproject.toml is the source of truth for testing:

- pytest options live in `[tool.pytest.ini_options]`.

- test-only dependencies live in `[dependency-groups] test`
  (PEP 735); py-checks installs the group when it is present.

tox is not used.


## Adopting py-checks in a repository

1. Copy `templates/ci.yml` to `.github/workflows/ci.yml`.

2. Copy `templates/release.yml` to `.github/workflows/release.yml`.

3. Copy `templates/cliff.toml` to `cliff.toml` and replace REPO with
   the repository name. The release script requires it.

4. Make sure `ruff check .` and `ruff format --check .` pass at the
   repository root.

5. Set up trusted publishing as described below, then release with
   `scripts/make_new_release.py`.


## Releasing

Releases are made with the shared script, run from the root of the
project repository:

    python ../workflows/scripts/make_new_release.py

It is the only supported way to release; tagging by hand skips the
guards below. What it does for you:

- **Refuses to release from a dubious state.** Requires the `main`
  branch, a clean working tree and a `cliff.toml`.

- **Runs the same checks as CI**, with the same pinned ruff version,
  and fails on the same things.

- **Tests the wheel it is about to release**, not the working tree,
  so packaging mistakes such as a module missing from the wheel are
  caught before publishing. Test dependencies come from
  `[dependency-groups] test`. `--skip-tests` overrides.

- **Proposes the next version** from the highest existing tag, and
  refuses versions that were already released, because PyPI uploads
  are immutable.

- **Writes the changelog entry** with git-cliff from the Conventional
  Commits since the last release, then opens it in your editor, and
  commits it only if you changed something.

- **Pushes the release commit and its tag atomically**, so a branch
  rejected by branch protection cannot leave a dangling tag that
  would publish from a commit which is not on main.

- **Resumes an interrupted release.** Run it again after a failed
  push and it detects the tagged HEAD, skips straight to pushing,
  and tells you when a release is already complete.

Pushing the tag is what triggers `release.yml`, which builds and
publishes to PyPI. Nothing is uploaded from a developer machine and
no PyPI token exists anywhere.


## PyPI trusted publishing (OIDC) setup

One-time, per project. The publish job runs without any stored
secret: PyPI trusts the GitHub workflow identity directly.

1. On PyPI, add a trusted publisher under
   Manage project -> Publishing:

   - Owner: the GitHub owner of the repository

   - Repository: the project repository name

   - Workflow name: `release.yml`

   - Environment: `pypi`

   For a project not yet on PyPI, create a **pending publisher** at
   https://pypi.org/manage/account/publishing/ with the same values
   plus the PyPI project name, which must exactly match `name` in
   the project's pyproject.toml.

2. In the GitHub repository, create an environment named `pypi`
   (Settings -> Environments). It can stay empty; add required
   reviewers there if you want a manual approval gate before
   publishing.

PEP 740 attestations are generated automatically by
`pypa/gh-action-pypi-publish` when using trusted publishing.


## Why the publish step is not centralized

PyPI validates the OIDC claim against the workflow file in the
project's own repository. Publishing from inside a reusable workflow
is rejected (`invalid-publisher`); see
https://github.com/pypi/warehouse/issues/11096.

So each repository keeps a small `publish` job (download the `dist`
artifact, run `pypa/gh-action-pypi-publish`) while lint, format,
build and tests live here.


## Cross-organization use

Reusable workflows from this repository work for repositories in
other accounts as long as this repository is **public**. No settings
are needed on the chatmail side.


## Pinning

Consumers reference `py-checks.yml@main` so refinements propagate
immediately. The ruff version is pinned in py-checks.yml and bumped
centrally there. Actions are pinned to their major tags, except
`astral-sh/setup-uv`, which publishes no moving major tag and is
pinned to an exact version.


## Conventions assumed

- pyproject.toml with setuptools + setuptools-git-versioning
  (version derived from git tags; py-checks checks out with
  `fetch-depth: 0` for this reason).

- ruff for linting and formatting, configured in pyproject.toml.

- pytest for tests, options and test dependencies declared in
  pyproject.toml.

- Python 3.11 (Debian 12) as the common interpreter line.

- uv as the installer, in CI and in READMEs: `uv tool install <tool>`
  for users, `uv pip install -e .` for development.

- Conventional Commits, since git-cliff generates the changelog entry
  from them. CHANGELOG.md carries no top-level title: the release
  script prepends each new section at the top of the file.

- uv.lock is not tracked. Nothing consumes it -- CI installs from
  pyproject.toml so that upstream breakage surfaces early -- and an
  unchecked lockfile only goes stale.

- Tags are `vX.Y.Z`, created by the release script. The `v` prefix is
  what release.yml triggers on; PyPI itself places no requirement on
  tag names. Repositories with older unprefixed tags can switch over
  without renaming them: setuptools-git-versioning picks the newest
  tag and PEP 440 drops the `v`.
