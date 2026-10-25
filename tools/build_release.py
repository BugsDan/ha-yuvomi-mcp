"""Build reproducible, credential-free integration and source archives."""

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]


def archive(name, files, *, output_dir=None):
    target = (output_dir if output_dir is not None else ROOT / "dist") / name
    target.parent.mkdir(exist_ok=True)
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as output:
        for path in sorted(files):
            info = ZipInfo(path.relative_to(ROOT).as_posix(), date_time=(2026, 10, 25, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            output.writestr(info, path.read_bytes())
    return target, hashlib.sha256(target.read_bytes()).hexdigest()


def build(output_dir=None):
    from check_repository import validate
    from repository_files import public_files

    if validate():
        raise ValueError("Publication check failed; run tools/check_repository.py")

    files = public_files()
    version = json.loads((ROOT / "custom_components/yuvomi_mcp/manifest.json").read_text(encoding="utf-8"))[
        "version"
    ]
    component = [p for p in files if p.relative_to(ROOT).parts[0] == "custom_components"]
    documentation = [
        p
        for p in files
        if p.relative_to(ROOT).parts[0] == "docs"
        or p.name in {"README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"}
    ]
    results = [
        archive(f"yuvomi_mcp-{version}.zip", component + documentation, output_dir=output_dir),
        archive(f"yuvomi_mcp-{version}-source.zip", files, output_dir=output_dir),
    ]
    checksum = "".join(f"{digest}  {path.name}\n" for path, digest in results)
    folder = output_dir if output_dir is not None else ROOT / "dist"
    (folder / "SHA256SUMS.txt").write_text(checksum, encoding="utf-8")
    (folder / f"SHA256SUMS-{version}.txt").write_text(checksum, encoding="utf-8")
    return checksum


if __name__ == "__main__":
    print(build())
