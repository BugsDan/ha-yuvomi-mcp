# Contributing

Keep the domain yuvomi_mcp, config-entry format and persistent journal compatible. Do not use production Home Assistant or Yuvomi data for tests. Preserve prepared/unknown execution barriers and never add automatic retries for ambiguous writes.

Run:

```shell
python -m pip install -e ".[test]"
python -m pytest -q
ruff check custom_components tests tools
ruff format --check custom_components tests tools
python tools/check_repository.py
```

The Linux CI additionally installs Home Assistant 2026.10.2 under Python 3.14 and runs the real HA platform/Store/options tests. Local Python 3.12 tests intentionally skip that module.

Before release, update manifest.json, const.VERSION and project.version together, add release notes, run all checks, then use a matching vMAJOR.MINOR.PATCH tag. Tags must never be moved after release. See docs/GITHUB_HACS.md. Do not change dependency versions through a global application-version replacement.
