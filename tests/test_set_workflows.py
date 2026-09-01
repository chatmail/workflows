import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "set-workflows.sh"


def install(path):
    """Runs set-workflows.sh in the repository and returns the result."""
    return subprocess.run(
        [str(SCRIPT)], cwd=path, capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize(
    "origin,slug",
    [
        ("git@github.com:hpk42/cmtop.git", "hpk42/cmtop"),
        ("https://github.com/chatmail/cmping.git", "chatmail/cmping"),
        ("https://github.com/acme/tool", "acme/tool"),
    ],
)
def test_changelog_links_point_at_origin(make_repo, origin, slug):
    path = make_repo(origin)
    assert install(path).returncode == 0
    cliff = (path / "cliff.toml").read_text()
    assert f"https://github.com/{slug}/pull/" in cliff
    assert f"https://github.com/{slug}\\" in cliff
    assert "OWNER/REPO" not in cliff
    assert "# Copy to" not in cliff


@pytest.mark.parametrize("origin", [None, "git@codeberg.org:someone/thing.git"])
def test_origin_without_a_github_path_is_refused(make_repo, origin):
    path = make_repo(origin)
    assert install(path).returncode == 1
    assert not (path / "cliff.toml").exists()
