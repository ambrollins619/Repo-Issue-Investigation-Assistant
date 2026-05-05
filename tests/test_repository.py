from pathlib import Path
import os
import subprocess

import pytest

from backend.app.repository import Repository


def test_containment_and_exclusions(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "ok.py").write_text("def hello():\n    return 1\n")
    (root / ".env").write_text("KEY=private")
    (root / "credentials.json").write_text('{}')
    (root / "binary.py").write_bytes(b"a\x00b")
    (root / "big.py").write_text("x" * 100_001)
    (root / "leak.py").write_text('api_key = "1234567890123456"')
    (root / ".git").mkdir()
    (root / ".git" / "config.py").write_text("hidden")
    repo = Repository(root)
    assert repo.list_files() == ["ok.py"]
    for path in ["../outside.py", str(tmp_path / "outside.py"), ".env", ".git/config.py", "ok.py:stream"]:
        with pytest.raises((ValueError, OSError)):
            repo.read_file(path)
    assert repo.search_code(["hello"])[0]["start_line"] == 1
    with pytest.raises(ValueError):
        repo.read_file("ok.py", 0)


def test_symlink_escape(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    target = tmp_path / "outside.py"
    target.write_text("private")
    try:
        (root / "link.py").symlink_to(target)
    except OSError:
        pytest.skip("OS does not grant symlink creation")
    repo = Repository(root)
    assert repo.list_files() == []
    with pytest.raises(ValueError):
        repo.read_file("link.py")


def test_budgets(tmp_path):
    for n in range(12):
        (tmp_path / f"a{n}.py").write_text("needle\n" * 100)
    repo = Repository(tmp_path)
    assert len(repo.search_code(["needle"], 999)) == 8
    assert repo.read_file("a0.py", 1, 999)["end_line"] == 40


@pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
def test_junction_escape(tmp_path):
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "hidden.py").write_text("private")
    # Paths are pytest-owned temporary directories, supplied as arguments, not shell code.
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "New-Item -ItemType Junction -Path $env:TEST_LINK_PATH -Target $env:TEST_TARGET_PATH | Out-Null"],
                   env={**os.environ, "TEST_LINK_PATH": str(root / "linked"), "TEST_TARGET_PATH": str(outside)}, check=True)
    repo = Repository(root)
    assert repo.list_files() == []
    with pytest.raises(ValueError):
        repo.read_file("linked/hidden.py")
