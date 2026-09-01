import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def pinned(path, pattern):
    """Returns the ruff version the file pins."""
    match = re.search(pattern, (REPO / path).read_text())
    assert match, f"no pin matching {pattern!r} in {path}"
    return match.group(1)


def test_ruff_is_pinned_to_one_version():
    """py-checks, the CI of this repository and the release script agree."""
    assert (
        pinned(".github/workflows/py-checks.yml", r'RUFF_VERSION: "(.+)"')
        == pinned(".github/workflows/ci.yml", r'RUFF_VERSION: "(.+)"')
        == pinned("scripts/make_new_release.py", r'RUFF_VERSION = "(.+)"')
    )
