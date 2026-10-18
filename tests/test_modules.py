import json
import sys
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from talos_hoard.app import create_app


@pytest.fixture
def quiet_engines(monkeypatch, tmp_path):
    values = {"ECHO_BACKEND": "fake", "ARGUS_CAPTURE": "fake", "ARGUS_WINDOW": "fake", "ARGUS_VISUAL": "none",
              "SCRIBE_AUDIO": "fake", "SCRIBE_TRANSCRIBER": "fake", "CASSANDRA_AUTOSTART": "0",
              "CASSANDRA_GPU": "0", "CASSANDRA_BUS": "0", "CASSANDRA_EXTERNALS": "0",
              "CASSANDRA_HUB_REGISTRY": "0", "CASSANDRA_DEFAULT_LOGS": "0", "CASSANDRA_ROOTS": str(tmp_path),
              "HOARD_HUB_URL": "http://127.0.0.1:1", "HOARD_FAUSTUS_URL": "http://127.0.0.1:1"}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    from funes_hoard import api
    from funes_hoard.collectors.fake import FakeProbe
    from funes_hoard.core.spans import Sample
    monkeypatch.setattr(api, "_pick_probe", lambda demo: FakeProbe([Sample(1700000000, "Fixture", "fixture.exe", "Synthetic", 1, 0, False)]))
    monkeypatch.setattr(api, "windows_recent_dir", lambda: None)


def client(app):
    return TestClient(app, base_url="http://127.0.0.1:5220")


def test_defaults_and_discovery_never_create_module_data(tmp_path):
    app = create_app(tmp_path, port=5220)
    before = {t.ident for t in threading.enumerate()}
    with client(app) as c:
        assert not any(m["enabled"] for m in c.get("/api/modules").json()["modules"])
        assert len(c.get("/api/agent/tools").json()["tools"]) == 93
        for key in app.state.modules:
            assert c.get(f"/{key}/api/health").status_code == 409
            assert not (tmp_path / key).exists()
        assert not any(t.name.startswith(("argus", "echo-", "funes", "dh-")) and t.ident not in before for t in threading.enumerate())
        response = c.post("/api/agent/call", headers={"Authorization": "Bearer " + app.state.token},
                          json={"name": "clip_recent", "arguments": {}})
        assert response.status_code == 409


def test_clipboard_independent_persistent_and_no_bypass(tmp_path, quiet_engines):
    app = create_app(tmp_path, port=5220)
    with client(app) as c:
        assert c.put("/api/modules/clipboard", json={"enabled": True}).status_code == 200
        assert not app.state.modules["screen"].app
        assert c.post("/clipboard/api/clips", json={"text": "Talos preserved clip"}).status_code < 300
        assert c.put("/api/modules/clipboard", json={"enabled": False}).status_code == 200
        assert c.post("/clipboard/api/resume", json={}).status_code == 409
        assert c.put("/api/modules/clipboard", json={"enabled": True}).status_code == 200
        response = c.post("/api/agent/call", headers={"Authorization": "Bearer " + app.state.token},
                          json={"name": "clip_search", "arguments": {"q": "Talos preserved clip"}})
        assert response.status_code == 200, response.text
        assert "Talos preserved clip" in response.text
    with client(create_app(tmp_path, port=5220)) as c:
        assert next(m for m in c.get("/api/modules").json()["modules"] if m["id"] == "clipboard")["enabled"]
        assert c.post("/api/modules/stop-all").status_code == 200
    with client(create_app(tmp_path, port=5220)) as c:
        assert not any(m["enabled"] for m in c.get("/api/modules").json()["modules"])


@pytest.mark.parametrize("module", ["screen", "activity", "audio", "services", "disk"])
def test_native_modules_start_stop_and_keep_catalog(module, tmp_path, quiet_engines):
    app = create_app(tmp_path, port=5220)
    with client(app) as c:
        response = c.put(f"/api/modules/{module}", json={"enabled": True})
        assert response.status_code == 200, response.text
        response = c.get(f"/{module}/api/health")
        assert response.status_code == 200, response.text
        catalog = c.get(f"/{module}/api/agent/tools")
        assert catalog.status_code == 200, catalog.text
        assert catalog.json()["tools"]
        assert c.get(f"/{module}/").status_code == 200
        assert c.put(f"/api/modules/{module}", json={"enabled": False}).status_code == 200
        assert app.state.modules[module].app is None
        assert c.get(f"/{module}/api/health").status_code == 409


def test_disabled_external_data_never_opened_or_changed(tmp_path):
    source = tmp_path / "original"
    source.mkdir()
    marker = source / "echo-hoard.db"
    marker.write_bytes(b"existing data must never be opened while disabled")
    config_dir = tmp_path / "host"
    config_dir.mkdir()
    (config_dir / "modules.json").write_text(json.dumps({"enabled": [], "data_paths": {"clipboard": str(source)}}))
    with client(create_app(config_dir, port=5220)) as c:
        assert c.get("/api/agent/tools").status_code == 200
        assert c.get("/clipboard/api/status").status_code == 409
    assert marker.read_bytes() == b"existing data must never be opened while disabled"
    assert list(source.iterdir()) == [marker]


def test_invalid_control_and_cross_site_requests(tmp_path):
    with client(create_app(tmp_path, port=5220)) as c:
        assert c.put("/api/modules/clipboard", json={"enabled": "false"}).status_code == 422
        assert c.put("/api/modules/missing", json={"enabled": True}).status_code == 404
        assert c.put("/api/modules/clipboard", json={"enabled": True}, headers={"Origin": "https://example.com"}).status_code == 403


def test_funes_compatibility_reaches_audio_without_activity(tmp_path, quiet_engines):
    app = create_app(tmp_path, port=5220)
    with client(app) as c:
        assert c.put("/api/modules/audio", json={"enabled": True}).status_code == 200
        assert app.state.modules["activity"].app is None
        token = (tmp_path / "activity/mcp-token").read_text(encoding="utf-8").strip()
        response = c.post("/legacy/funes/api/agent/call", headers={"Authorization": "Bearer " + token},
                          json={"name": "scribe_status", "arguments": {}})
        assert response.status_code == 200, response.text
        assert c.get("/legacy/funes/api/health").status_code == 200
        assert c.put("/api/modules/audio", json={"enabled": False}).status_code == 200
        assert c.get("/legacy/funes/api/health").status_code == 409
