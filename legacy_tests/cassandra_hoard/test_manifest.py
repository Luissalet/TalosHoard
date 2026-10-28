"""faustus-plugin.json stays in sync with the code."""

import json
from pathlib import Path

from cassandra_hoard.agent_tools import TOOLS

ROOT = Path(__file__).resolve().parents[2]


def test_manifest_matches_code():
    """In Talos the manifest is the root one: it absorbs Cassandra, and every Cassandra tool is in the Services part of the catalogue."""
    manifest = json.loads((ROOT / "faustus-plugin.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "talos" and manifest["name"] == "Talos's Hoard"
    assert "cassandra_hoard" in manifest["x-family"]["absorbs"]
    assert manifest["app"]["health"]["expect"]["service"] == "talos-hoard"
    catalog = {tool["name"]: tool for tool in json.loads((ROOT / "talos_hoard" / "catalog.json").read_text(encoding="utf-8"))}
    for tool in TOOLS:
        assert catalog[tool.name]["module"] == "services", tool.name
    # the catalogue is generated from the code: a tool added to Cassandra without rebuilding it would be missing above
    inventory = (ROOT / "provenance" / "CAPABILITIES.md").read_text(encoding="utf-8")
    for tool in TOOLS:
        assert f"| services | {tool.name} |" in inventory, tool.name
