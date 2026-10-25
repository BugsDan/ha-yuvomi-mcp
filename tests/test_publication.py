"""Publication safety, tag consistency and byte-exact artifact boundaries."""

import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / "custom_components/yuvomi_mcp/manifest.json").read_text(encoding="utf-8"))[
    "version"
]
sys.path.insert(0, str(ROOT / "tools"))

from build_release import build  # noqa: E402
from check_repository import scan, staged_errors, validate  # noqa: E402
from prepare_repository import prepare  # noqa: E402
from repository_files import allowed, public_files  # noqa: E402


def test_publication_and_matching_tag_pass():
    assert validate(tag=f"v{VERSION}") == []


@pytest.mark.parametrize("tag", [VERSION, "v0.0.0", f"v{VERSION}-extra"])
def test_mismatched_tag_is_rejected(tag):
    assert any("Git tag" in error for error in validate(tag=tag))


@pytest.mark.parametrize(
    "data,kind",
    [
        ("gh" + "p_" + "x" * 36, "github-token"),
        ("sk-" + "x" * 32, "openai-token"),
        ("-----BEGIN " + "PRIVATE KEY-----", "private-key"),
        ("http://" + ".".join(["10", "1", "2", "3"]), "internal-ip"),
        ("C:" + chr(92) + "Users" + chr(92) + "Example" + chr(92) + "file", "personal-path"),
        (json.dumps({"api_token": "x" * 28}), "credential-like literal"),
    ],
)
def test_sensitive_values_are_blocked_without_echoing_payload(data, kind):
    result = scan(Path("docs/example.md"), data.encode())
    assert any(kind in error for error in result)
    assert not any(data in error for error in result)


def test_known_test_tokens_are_allowed_only_in_tests():
    data = json.dumps({"api_token": "test-secret-token"}).encode()
    assert scan(Path("tests/fixture.py"), data) == []
    assert scan(Path("docs/example.md"), data)


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".storage/entry.json",
        ".venv/private.py",
        "reference/source.py",
        "dist/release.zip",
        "tests/__pycache__/cache.py",
        "docs/.storage/personal.json",
    ],
)
def test_workspace_and_private_files_cannot_enter_publication(name):
    assert not allowed(Path(name))


def test_clean_review_zip_contains_only_audited_files_and_original_bytes(tmp_path):
    target, _ = prepare(tmp_path)
    expected = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in public_files()}
    with ZipFile(target) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(expected)
        assert all(archive.read(name) == data for name, data in expected.items())
        assert "hacs.json" in archive.namelist()
        assert ".github/workflows/release.yml" in archive.namelist()
        assert "custom_components/yuvomi_mcp/brand/icon.png" in archive.namelist()


def test_manual_and_source_release_archives_have_distinct_correct_layouts(tmp_path):
    build(tmp_path)
    with ZipFile(tmp_path / f"yuvomi_mcp-{VERSION}.zip") as archive:
        assert "custom_components/yuvomi_mcp/brand/icon.png" in archive.namelist()
        assert "tests/test_client.py" not in archive.namelist()
    with ZipFile(tmp_path / f"yuvomi_mcp-{VERSION}-source.zip") as archive:
        assert "hacs.json" in archive.namelist()
        assert ".github/CODEOWNERS" in archive.namelist()
        assert "tests/test_client.py" in archive.namelist()


def test_index_scan_reads_staged_blob_instead_of_clean_working_file(tmp_path):
    # An isolated temporary Git index, no commits, remote or network.
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("gh" + "p_" + "x" * 36, encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("Clean working copy", encoding="utf-8")
    assert any("github-token" in error for error in staged_errors(tmp_path))
