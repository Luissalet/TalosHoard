from pathlib import Path

from legacy_tests.funes_hoard.faustus_manifest import check_repo

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_manifest_is_valid():
    data = check_repo(REPO_ROOT)
    assert data["id"] == "funes"
    assert data["mcp"]["transport"] == "stdio"
