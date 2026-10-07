"""Native Codex plugin's local dispatch transport."""
from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
os.environ["SKY_PLUGIN_ROOT"] = str(Path(__file__).resolve().parents[1])
from sky.codexdispatch import serve

serve()
