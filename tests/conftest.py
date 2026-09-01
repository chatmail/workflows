import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))


@pytest.fixture
def make_repo(tmp_path):
    """Returns a factory for a git repository with one commit."""

    def make(origin=None):
        path = tmp_path / "project"
        path.mkdir()
        (path / "pyproject.toml").write_text("[project]\n")
        for args in [
            ["init", "-q", "."],
            ["config", "user.email", "t@example.org"],
            ["config", "user.name", "t"],
            ["commit", "-q", "--allow-empty", "-m", "first"],
        ]:
            subprocess.run(["git", *args], cwd=path, check=True)
        if origin:
            subprocess.run(
                ["git", "remote", "add", "origin", origin], cwd=path, check=True
            )
        return path

    return make
