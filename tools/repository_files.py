"""Explicit publication file set; no recursive copy of the development workspace."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = frozenset(
    {
        ".gitignore",
        ".gitattributes",
        "hacs.json",
        "LICENSE",
        "README.md",
        "pyproject.toml",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "THIRD_PARTY_NOTICES.md",
    }
)
SUFFIXES = {
    "custom_components": {".py", ".json", ".png", ".svg"},
    "tests": {".py"},
    "tools": {".py"},
    "docs": {".md", ".json"},
    ".github": {".yml", ".yaml", ".md"},
}


def allowed(path):
    path = Path(path)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "__pycache__" in path.parts
        or any(part.startswith(".") for part in path.parts[1:])
    ):
        return False
    if path.as_posix() in ROOT_FILES or path.as_posix() == ".github/CODEOWNERS":
        return True
    return len(path.parts) > 1 and path.parts[0] in SUFFIXES and path.suffix in SUFFIXES[path.parts[0]]


def public_files(root=ROOT):
    files = [root / name for name in ROOT_FILES if (root / name).is_file()]
    for folder in SUFFIXES:
        files.extend(p for p in (root / folder).rglob("*") if p.is_file() and allowed(p.relative_to(root)))
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Symlink/outside path is not publishable")
    return sorted(files)
