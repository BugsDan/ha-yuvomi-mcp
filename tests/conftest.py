"""Load the protocol/runtime package without importing HA on Windows.

HA-specific tests import the real installed HA when available. This namespace
only defers the integration setup module, it does not simulate Home Assistant.
"""

import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
package = ModuleType("custom_components.yuvomi_mcp")
package.__path__ = [str(ROOT / "custom_components" / "yuvomi_mcp")]
sys.modules.setdefault("custom_components.yuvomi_mcp", package)
