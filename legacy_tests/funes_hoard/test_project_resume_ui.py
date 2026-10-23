from fastapi.testclient import TestClient

from funes_hoard import api
from legacy_tests.funes_hoard.fakes import FakeLink


def test_project_resume_ui_delegates_validated_arguments_without_writing_records(tmp_path, monkeypatch):
    monkeypatch.setattr(api.Collector, "start", lambda self: None)
    monkeypatch.setattr(api.Collector, "stop", lambda self: None)
    monkeypatch.setattr(api.BackgroundScheduler, "start", lambda self: None)
    monkeypatch.setattr(api.BackgroundScheduler, "stop", lambda self: None)
    monkeypatch.setattr(api, "windows_recent_dir", lambda: None)
    from funes_hoard.collectors.fake import FakeProbe
    from funes_hoard.core.spans import Sample
    monkeypatch.setattr(api, "_pick_probe", lambda demo: FakeProbe([Sample(1700000000, "Fixture", "fixture.exe", "Synthetic", 1, 0, False)]))
    calls = []
    def native(db, project, days, limit):
        calls.append((project, days, limit))
        return {"project": project, "since": 0, "until": 100, "last_activity": None,
                "active_s": 0, "recent_windows": [], "recent_files": [{"path": "fiction/ñ.txt", "ts": 10}],
                "recent_commits": [], "found": True, "evidence_limit": "native"}
    monkeypatch.setattr(api.queries, "activity_project_resume", native)
    app = api.create_app(tmp_path, port=63346, link_factory=FakeLink, audio_enabled=False)
    with TestClient(app, base_url="http://127.0.0.1:63346") as client:
        result = client.post("/api/projects/resume", json={"project": "Proyecto ñ", "days": 7, "limit": 2})
        assert result.status_code == 200
        assert result.json()["last_activity"] is None and result.json()["found"] is True
        assert result.json()["recent_files"][0]["path"] == "fiction/ñ.txt"
        for invalid in ({"days": 0}, {"days": 181}, {"limit": 0}, {"limit": 11}):
            assert client.post("/api/projects/resume", json={"project": "Proyecto ñ", **invalid}).status_code == 400
        assert calls == [("Proyecto ñ", 7, 2)]
        assert app.state.db.query_one("SELECT COUNT(*) c FROM agent_calls")["c"] == 0
