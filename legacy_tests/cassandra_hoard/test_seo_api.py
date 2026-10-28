"""SEO / GEO watch through the HTTP API, the agent tools and the notification channel."""

import time
from types import SimpleNamespace

import pytest

from cassandra_hoard.agent_tools import AGENT_INSTRUCTIONS
from cassandra_hoard.hoard_link import family
from cassandra_hoard.notifications import BoopNotifier
from cassandra_hoard.seo_watch import EV_CRITICAL, EV_DROP

URL = "https://luissalet.github.io/Portfolio/"
CRITICAL = {"id": "noindex", "severity": "critical", "title": "The home page is set to noindex", "category": "technical"}


@pytest.fixture
def bus(monkeypatch):
    sent = []
    monkeypatch.setattr(family, "emit", lambda type_, data=None, **kw: sent.append((type_, data)) or True)
    return sent


def auth(client):
    return {"Authorization": f"Bearer {client.h.services.token}"}


def call(client, tool, /, **arguments):
    response = client.post("/api/agent/call", json={"name": tool, "arguments": arguments}, headers=auth(client))
    assert response.status_code == 200, response.text
    return response.json()


def watch(client, **extra):
    response = client.post("/api/sites", json={"url": URL, "id": "portfolio", "name": "Portfolio", "seo_interval_h": 24, **extra})
    assert response.status_code == 201, response.text


def run_now(client):
    return call(client, "sites_seo_run", site="portfolio", wait_s=20)


def test_the_site_list_takes_the_audit_schedule_and_the_overview_lists_every_site(client):
    assert client.get("/api/sites/seo").json()["sites"] == []
    watch(client, seo_drop_points=3)
    client.post("/api/sites", json={"url": "https://plain.example/", "id": "plain"})
    assert client.post("/api/sites", json={"id": "portfolio", "seo_interval_h": 0.2}).status_code == 400
    overview = client.get("/api/sites/seo").json()
    assert overview["source"] == "vitruvius site_audit" and overview["summary"]["watching"] == 1
    states = {s["id"]: s for s in overview["sites"]}
    assert states["portfolio"]["state"] == "pending" and states["portfolio"]["drop_points"] == 3.0 and states["plain"]["state"] == "off"
    assert client.get("/api/status").json()["seo"]["watching"] == 1
    assert client.get("/api/sites/nope/seo").status_code == 404
    assert client.post("/api/sites/seo/run", json={"site": "nope"}).status_code == 404
    assert client.get("/api/sites/seo", headers={"host": "evil.example"}).status_code == 403


def test_an_audit_asked_for_by_hand_runs_in_the_background_and_leaves_its_history(client, bus):
    watch(client)
    queued = client.post("/api/sites/seo/run", json={"site": "portfolio"})
    assert queued.status_code == 202
    for _ in range(100):
        body = client.get("/api/sites/portfolio/seo").json()
        if body["status"]["state"] == "ok":
            break
        time.sleep(0.1)
    assert body["status"]["score"] == 80 and body["status"]["baseline_score"] == 80 and body["runs"][0]["baseline"] is True
    assert client.h.audit.calls == [URL]
    moved = client.post("/api/sites/portfolio/seo/baseline").json()
    assert moved["baseline"]["score"] == 80 and moved["status"]["delta_baseline"] == 0
    assert client.post("/api/sites/plain/seo/baseline").status_code == 404
    client.h.audit.failure = ("app_down", "x")  # a site added now is audited at once: here the auditor is down, so there is nothing to accept
    watch_plain = client.post("/api/sites", json={"url": "https://plain.example/", "id": "plain", "seo_interval_h": 24})
    assert watch_plain.status_code == 201 and client.post("/api/sites/plain/seo/baseline").status_code == 409  # nothing audited yet


def test_the_tools_report_drift_run_now_and_move_the_baseline(client, bus):
    empty = call(client, "sites_seo")
    assert empty["sites"] == [] and "seo_interval_h" in empty["note"]
    added = call(client, "sites_watch", action="add", url=URL, id="portfolio", name="Portfolio", seo_interval_h=24, seo_drop_points=2)
    assert added["site"]["id"] == "portfolio"
    first = run_now(client)
    assert first["finished"] is True and first["site"]["score"] == 80 and first["site"]["state"] == "ok"
    client.h.audit.set(score=70, findings=[CRITICAL])
    client.h.clock.advance(3600)
    second = run_now(client)
    assert second["site"]["delta_previous"] == -10 and second["site"]["new_critical"][0]["id"] == "noindex"
    assert [t for t, d in bus if t in (EV_DROP, EV_CRITICAL)] == [EV_DROP, EV_CRITICAL]
    one = call(client, "sites_seo", site="Portfolio", history=5)
    assert one["site"]["score"] == 70 and one["site"]["delta_baseline"] == -10 and [r["score"] for r in one["history"]] == [70, 80]
    assert one["history"][0]["delta_previous"] == -10 and one["history"][0]["critical"] == 1
    every = call(client, "sites_seo")
    assert every["sites"][0]["score"] == 70 and every["dropped_since_previous"] == ["Portfolio: 70 (-10)"]
    assert every["critical_open"] == ["Portfolio: The home page is set to noindex"]
    assert call(client, "sites_seo_baseline", site="portfolio")["baseline"]["score"] == 70
    assert call(client, "sites_seo", site="portfolio")["site"]["delta_baseline"] == 0
    for bad in ({"name": "sites_seo", "arguments": {"site": "zzz"}}, {"name": "sites_seo_run", "arguments": {"site": "zzz"}},
                {"name": "sites_seo_baseline", "arguments": {"site": "zzz"}}):
        assert client.post("/api/agent/call", json=bad, headers=auth(client)).status_code == 404
    off = call(client, "sites_watch", action="edit", id="portfolio", seo_interval_h=0)
    assert "seo_interval_h" not in client.h.services.sites.store.find("portfolio")
    assert "interval_h" not in call(client, "sites_seo", site="portfolio")["site"]  # no schedule any more; the history stays
    assert call(client, "sites_seo", site="portfolio", history=3)["history"]


def test_a_site_that_is_not_audited_says_how_to_turn_it_on(client):
    client.post("/api/sites", json={"url": "https://plain.example/", "id": "plain"})
    assert "seo_interval_h" in call(client, "sites_seo", site="plain")["note"]


def test_an_unavailable_auditor_is_a_failed_run_with_its_cause(client, bus):
    client.h.audit.failure = ("tool_missing", "x")
    watch(client)
    result = run_now(client)
    assert result["finished"] is True and result["site"]["state"] == "unavailable" and "site_audit" in result["site"]["error"]
    assert "score" not in result["site"] and [t for t, _ in bus if t.startswith("cassandra.site.seo")] == []


def test_instructions_and_descriptions_say_when_to_use_the_seo_tools(client):
    for name in ("sites_seo", "sites_seo_run", "sites_seo_baseline"):
        assert name in AGENT_INSTRUCTIONS
    catalog = {t["name"]: t for t in client.get("/api/agent/tools").json()["tools"]}
    assert catalog["sites_seo"]["annotations"]["readOnlyHint"] is True and catalog["sites_seo_run"]["annotations"]["readOnlyHint"] is False
    assert "seo_interval_h" in catalog["sites_watch"]["inputSchema"]["properties"]


def test_the_seo_alerts_are_notified_without_names_scores_or_findings():
    cfg = SimpleNamespace(boop_url="https://boop.example", boop_api_key="k", public_url="https://cass.example", boop_enabled=True, bus=True)
    sent = []

    class Client:
        def post(self, url, json, headers, timeout, follow_redirects):
            sent.append(json)
            return SimpleNamespace(status_code=202)

    n = BoopNotifier(cfg, client=Client())
    assert n.send(EV_DROP, {"site": "portfolio", "name": "Portfolio", "url": URL, "score": 72, "previous": 79}) is True
    assert n.send(EV_CRITICAL, {"site": "portfolio", "name": "Portfolio", "url": URL, "score": 72, "findings": ["The home page is set to noindex"]}) is True
    assert n.send(EV_DROP, {"name": "no site id"}) is False
    text = str(sent)
    assert "portfolio" not in text.lower() and "noindex" not in text and URL not in text
    assert "score dropped" in sent[0]["title"] and "critical" in sent[1]["title"] and sent[0]["fingerprint"] != sent[1]["fingerprint"]
    assert sent[0]["actions"][0]["url"] == "https://cass.example/#/sites"
