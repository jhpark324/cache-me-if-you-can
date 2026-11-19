"""The published reference must match tools/list and its sample calls must still work."""
from pathlib import Path
import subprocess
import sys


def test_published_mcp_reference_matches_the_server():
    exporter = Path(__file__).resolve().parents[1] / "scripts/export_mcp_guide.py"
    subprocess.run([sys.executable, str(exporter), "--check"], check=True)
