import subprocess

import make_new_release as release


def test_latest_release_tag_is_the_highest_version(make_repo, monkeypatch):
    """Numeric order, and tags from before the v prefix still count."""
    path = make_repo()
    for name in ["0.9.0", "v0.10.0", "nightly"]:
        subprocess.run(["git", "tag", name], cwd=path, check=True)
    monkeypatch.chdir(path)
    assert release.get_latest_release_tag() == "v0.10.0"
