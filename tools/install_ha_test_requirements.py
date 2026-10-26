"""Install exact optional integration dependencies from the installed pinned HA manifest."""

import json
import subprocess
import sys
from importlib.metadata import version
from importlib.resources import files


def main():
    if version("homeassistant") != "2026.10.2":
        raise RuntimeError("HA runtime tests require exactly Home Assistant 2026.10.2")
    manifest = files("homeassistant").joinpath("components/conversation/manifest.json")
    requirements = json.loads(manifest.read_text(encoding="utf-8"))["requirements"]
    if not requirements or any("==" not in item for item in requirements):
        raise RuntimeError("Expected pinned Conversation dependencies")
    subprocess.run([sys.executable, "-m", "pip", "install", *requirements], check=True)


if __name__ == "__main__":
    main()
