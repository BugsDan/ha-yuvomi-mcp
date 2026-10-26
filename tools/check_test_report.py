"""Fail HA CI on skipped/absent tests; print auditable JUnit counts."""

import argparse
from pathlib import Path
from xml.etree import ElementTree


def check(path, no_skips=False):
    root = ElementTree.parse(path).getroot()
    cases = list(root.iter("testcase"))
    failed = sum(c.find("failure") is not None or c.find("error") is not None for c in cases)
    skipped = sum(c.find("skipped") is not None for c in cases)
    print(
        f"Tests: {len(cases)}; passed: {len(cases) - failed - skipped}; failed: {failed}; skipped: {skipped}"
    )
    if not cases or failed or (no_skips and skipped):
        raise ValueError("Missing, failed or unexpectedly skipped HA tests")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--no-skips", action="store_true")
    args = parser.parse_args()
    check(args.report, args.no_skips)
