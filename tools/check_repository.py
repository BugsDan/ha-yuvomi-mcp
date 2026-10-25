"""Local metadata, version/tag and publication hygiene checks. Never print secrets."""

import argparse
import ast
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from repository_files import ROOT, allowed, public_files

PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github-token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    "openai-token": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{24,}"),
    "aws-key": re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    "internal-ip": re.compile(
        r"(?<![\d.])(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?![\d.])"
    ),
    "personal-path": re.compile(r"(?:[A-Za-z]:[\\/]+Users[\\/]+[^\s\\/]+|/home/[A-Za-z0-9_.-]+/)", re.I),
}
ASSIGNMENT = re.compile(
    r"(?:api[_-]?token|password|secret|token)[\"']?\s*[:=]\s*[\"']([^\"'\n]{8,})[\"']", re.I
)
DUMMY_VALUES = {"test-secret-token", "local-test-token", "secret-token"}
PUBLIC_LABELS = {"api_token", "API-Token", "Neuer API-Token", "Neuer API-Token (optional)"}


def scan(path, data):
    if path.suffix == ".png":
        return []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [f"{path.as_posix()}: unexpected binary content"]
    errors = []
    for number, line in enumerate(text.splitlines(), 1):
        for kind, pattern in PATTERNS.items():
            if pattern.search(line):
                errors.append(f"{path.as_posix()}:{number}: {kind}")
        for match in ASSIGNMENT.finditer(line):
            if match[1] not in PUBLIC_LABELS and not (path.parts[0] == "tests" and match[1] in DUMMY_VALUES):
                errors.append(f"{path.as_posix()}:{number}: credential-like literal")
    return errors


def validate(root=ROOT, tag=None):
    manifest = json.loads((root / "custom_components/yuvomi_mcp/manifest.json").read_text(encoding="utf-8"))
    hacs = json.loads((root / "hacs.json").read_text(encoding="utf-8"))
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    tree = ast.parse((root / "custom_components/yuvomi_mcp/const.py").read_text(encoding="utf-8"))
    constants = {
        n.targets[0].id: ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "VERSION"
    }
    version = manifest["version"]
    errors = []
    if (
        not re.fullmatch(r"\d+\.\d+\.\d+", version)
        or version != constants["VERSION"]
        or version != project["project"]["version"]
    ):
        errors.append("Application versions are inconsistent")
    if tag is not None and tag != f"v{version}":
        errors.append("Git tag must equal v + manifest version")
    if manifest["domain"] != "yuvomi_mcp" or manifest.get("codeowners") != ["@BugsDan"]:
        errors.append("Domain/maintainer metadata differs from the intended repository")
    base = "https://github.com/BugsDan/ha-yuvomi-mcp"
    if manifest.get("documentation") != base or manifest.get("issue_tracker") != base + "/issues":
        errors.append("Repository links are incomplete")
    integrations = [
        p.name for p in (root / "custom_components").iterdir() if p.is_dir() and not p.name.startswith("_")
    ]
    if (
        integrations != ["yuvomi_mcp"]
        or hacs.get("content_in_root") is not False
        or hacs.get("zip_release") is not False
    ):
        errors.append("HACS must install the single integration from the tag source tree")
    if hacs.get("homeassistant") != "2026.10.2" or hacs.get("hide_default_branch") is not True:
        errors.append("HACS release/minimum-version policy missing")
    if not (root / "custom_components/yuvomi_mcp/brand/icon.png").is_file():
        errors.append("Local brand icon missing")
    if not (root / "docs" / f"RELEASE_{version}.md").is_file():
        errors.append("Versioned release notes missing")
    for path in public_files(root):
        errors.extend(scan(path.relative_to(root), path.read_bytes()))
    return errors


def staged_errors(root=ROOT):
    result = subprocess.run(["git", "ls-files", "-z", "--cached"], cwd=root, capture_output=True, check=True)
    errors = []
    for name in result.stdout.decode("utf-8").split("\0"):
        if not name:
            continue
        path = Path(name)
        if not allowed(path):
            errors.append(f"{name}: file outside publication allowlist")
            continue
        blob = subprocess.run(["git", "show", ":" + name], cwd=root, capture_output=True, check=True).stdout
        errors.extend(scan(path, blob))
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag")
    parser.add_argument(
        "--staged", action="store_true", help="Also inspect index blobs, not just working files"
    )
    args = parser.parse_args()
    errors = validate(tag=args.tag)
    if args.staged:
        try:
            errors.extend(staged_errors())
        except subprocess.CalledProcessError:
            errors.append("Staged check requires an initialized Git repository")
    for error in errors:
        print(error)
    print(f"Publication check: {len(errors)} findings; {len(public_files())} candidate files")
    sys.exit(bool(errors))
