"""SEO / GEO watch: the audit's answer, the baseline, the drift between runs, the alerts and the schedule."""

import json

import pytest
from conftest import Harness

from cassandra_hoard import seo_watch as W
from cassandra_hoard.seo_watch import EV_CRITICAL, EV_DROP, compare, normalize_report
from cassandra_hoard.sites import validate_site

CRITICAL = {"id": "noindex", "severity": "critical", "title": "The home page is set to noindex", "category": "technical"}
MEDIUM = {"id": "meta-description", "severity": "medium", "title": "Missing meta description", "category": "technical"}


def make(tmp_path, **site):
    h = Harness(tmp_path)
    events = []
    h.services.seo.emit = lambda t, d: events.append((t, d))
    entry = {"url": "https://luissalet.github.io/Portfolio/", "id": "portfolio", "name": "Portfolio", "seo_interval_h": 24, **site}
    site_ = h.services.sites.store.upsert(entry)[0]
    return h, h.services.seo, site_, events


def run_after(h, seo, site, hours=24, **report):
    h.clock.advance(hours * 3600)
    h.audit.set(**report)
    return seo.run(site)


# -- the audit's answer -------------------------------------------------------------------------------------------------

def test_the_report_is_read_from_the_usual_shapes():
    full = normalize_report({"score": 71.5, "categories": {"technical": 80, "ai": "62%"}, "findings": [
        {"id": "a", "severity": "Warning", "title": "  Two   spaces ", "category": "technical"}, {"title": "No id", "severity": "blocker", "category": "ai"},
        {"id": "a", "severity": "low", "title": "duplicate"}, "junk", {"severity": "low"}]})
    assert full["score"] == 71.5 and full["categories"] == {"technical": 80.0, "ai": 62.0}
    assert [f["severity"] for f in full["findings"]] == ["critical", "medium"] and full["findings"][1]["title"] == "Two spaces"
    assert full["counts"]["critical"] == 1 and full["findings_total"] == 2
    assert normalize_report({"result": {"scores": {"total": 90, "seo": 95}, "findings": []}})["categories"] == {"seo": 95.0}
    assert normalize_report(json.dumps({"audit": {"categories": [{"id": "a", "score": 60}, {"name": "b", "score": 80}]}}))["score"] == 70.0
    assert normalize_report({"score": {"score": 8, "max": 10}})["score"] == 80.0


@pytest.mark.parametrize("bad", [{}, {"findings": []}, {"score": 140}, {"score": "high"}, "not json", [1, 2], None])
def test_an_answer_without_a_usable_score_is_refused(bad):
    with pytest.raises(ValueError):
        normalize_report(bad)


def test_compare_finds_what_appeared_and_what_was_resolved():
    before = normalize_report({"score": 80, "categories": {"a": 80, "b": 70}, "findings": [MEDIUM]})
    after = normalize_report({"score": 74, "categories": {"a": 80, "b": 60}, "findings": [CRITICAL]})
    drift = compare(before, after)
    assert drift["score_delta"] == -6 and drift["categories"] == {"b": -10}
    assert [f["id"] for f in drift["new"]] == ["noindex"] and [f["id"] for f in drift["resolved"]] == ["meta-description"]
    assert [f["id"] for f in drift["new_critical"]] == ["noindex"] and drift["critical_open"] == 1
    assert compare(None, after)["score_delta"] is None and compare(after, after)["new"] == []


def test_a_finding_without_id_is_the_same_by_category_and_title():
    one = normalize_report({"score": 50, "findings": [{"title": "Slow LCP", "category": "cwv", "severity": "high"}]})
    two = normalize_report({"score": 50, "findings": [{"title": "slow  lcp", "category": "CWV", "severity": "high"}]})
    assert compare(one, two)["new"] == [] and compare(one, two)["resolved"] == []


# -- the list ----------------------------------------------------------------------------------------------------------

def test_the_schedule_fields_exist_only_when_set():
    plain = validate_site({"url": "https://example.com/"})
    assert "seo_interval_h" not in plain and "seo_drop_points" not in plain
    on = validate_site({"url": "https://example.com/", "seo_interval_h": 24, "seo_drop_points": 3})
    assert on["seo_interval_h"] == 24.0 and on["seo_drop_points"] == 3.0
    assert "seo_interval_h" not in validate_site({"seo_interval_h": 0}, on) and validate_site({"seo_interval_h": 12}, on)["seo_drop_points"] == 3.0
    for bad in ({"seo_interval_h": 0.5}, {"seo_interval_h": 721}, {"seo_interval_h": "daily"}, {"seo_drop_points": 0.1}):
        with pytest.raises(ValueError):
            validate_site({"url": "https://example.com/", **bad})


# -- the schedule ------------------------------------------------------------------------------------------------------

def test_only_opted_in_sites_are_audited_and_each_one_when_its_time_comes(tmp_path):
    h, seo, site, events = make(tmp_path)
    h.services.sites.store.upsert({"url": "https://plain.example/", "id": "plain"})
    assert seo.tick() == ["portfolio"] and h.audit.calls == ["https://luissalet.github.io/Portfolio/"]
    assert seo.tick() == []  # not due again
    h.clock.advance(23 * 3600)
    assert seo.tick() == []
    h.clock.advance(3600)
    assert seo.tick() == ["portfolio"] and len(h.audit.calls) == 2
    assert {s["id"]: s["state"] for s in seo.status_all()} == {"portfolio": "ok", "plain": "off"}


def test_a_site_that_is_paused_or_opted_out_is_left_alone(tmp_path):
    h, seo, site, _ = make(tmp_path, enabled=False)
    assert seo.tick() == []
    off = h.services.sites.store.upsert({"id": "portfolio", "enabled": True, "seo_interval_h": 0})[0]
    assert seo.tick() == [] and "seo_interval_h" not in off


def test_a_failed_audit_is_stored_with_its_cause_retried_in_an_hour_and_never_alerts(tmp_path):
    h, seo, site, events = make(tmp_path)
    h.audit.failure = ("tool_missing", "x")
    seo.tick()
    status = seo.status_one(site)
    assert status["state"] == "unavailable" and "site_audit" in status["error"] and status["score"] is None
    assert seo.tick() == []
    h.clock.advance(3599)
    assert seo.tick() == []
    h.clock.advance(2)
    assert seo.tick() == ["portfolio"] and len(h.audit.calls) == 2
    h.audit.failure = None
    h.clock.advance(3601)
    seo.tick()
    status = seo.status_one(site)
    assert status["state"] == "ok" and status["score"] == 80 and events == []
    assert [r["ok"] for r in seo.history(site)["runs"]] == [True, False, False]


def test_a_broken_answer_is_a_failed_run_not_a_crash(tmp_path):
    h, seo, site, _ = make(tmp_path)
    h.audit.report = {"findings": []}
    run = seo.run(site)
    assert not run["ok"] and run["error_kind"] == "bad_answer" and "score" in run["error"]
    h.audit.audit_fn = lambda url: (_ for _ in ()).throw(RuntimeError("boom"))
    seo.audit_fn = h.audit.audit_fn
    assert "boom" in seo.run(site)["error"]


def test_asking_for_an_audit_now_runs_it_on_the_next_tick(tmp_path):
    h, seo, site, _ = make(tmp_path, seo_interval_h=720)
    seo.tick()
    assert seo.request(site) is True and seo.busy("portfolio")
    assert seo.tick() == ["portfolio"] and not seo.busy("portfolio") and len(h.audit.calls) == 2


# -- baseline, drift and alerts ----------------------------------------------------------------------------------------

def test_the_first_run_is_the_baseline_and_announces_nothing_even_with_a_critical_finding(tmp_path):
    h, seo, site, events = make(tmp_path)
    h.audit.set(findings=[CRITICAL, MEDIUM])
    run = seo.run(site)
    assert run["baseline"] is True and run["drift"]["score_delta"] is None and events == []
    status = seo.status_one(site)
    assert status["score"] == 80 and status["baseline_score"] == 80 and status["delta_baseline"] == 0
    assert [f["id"] for f in status["critical"]] == ["noindex"] and status["new_critical"] == []


def test_a_drop_of_the_threshold_or_more_raises_one_alert_and_a_stable_low_score_stays_quiet(tmp_path):
    h, seo, site, events = make(tmp_path)
    seo.run(site)
    run_after(h, seo, site, score=79)          # 1 point: below the default threshold of 2
    assert events == []
    run_after(h, seo, site, score=72)          # 7 below the best (80), lower than before
    assert [t for t, _ in events] == [EV_DROP]
    data = events[0][1]
    assert data["site"] == "portfolio" and data["score"] == 72 and data["previous"] == 79 and data["best"] == 80 and data["drop"] == 8
    run_after(h, seo, site, score=72)          # still low, no longer falling
    assert len(events) == 1
    run_after(h, seo, site, score=70)          # falling again
    assert [t for t, _ in events] == [EV_DROP, EV_DROP]
    row = h.services.db.query("SELECT detail FROM events WHERE service = 'site:portfolio' AND kind = 'seo' ORDER BY id")[0]["detail"]
    assert "72" in row and "recent best" in row


def test_a_better_score_never_alerts_and_the_threshold_is_per_site(tmp_path):
    h, seo, site, events = make(tmp_path, seo_drop_points=10)
    seo.run(site)
    run_after(h, seo, site, score=90)
    run_after(h, seo, site, score=85)          # 5 below the best: under the site's own threshold of 10
    assert events == []
    run_after(h, seo, site, score=79)
    assert [t for t, _ in events] == [EV_DROP] and events[0][1]["threshold"] == 10.0


def test_a_new_critical_finding_raises_an_alert_once_and_not_while_it_stays(tmp_path):
    h, seo, site, events = make(tmp_path)
    seo.run(site)
    run_after(h, seo, site, findings=[MEDIUM, CRITICAL])
    assert [t for t, _ in events] == [EV_CRITICAL]
    assert events[0][1]["count"] == 1 and events[0][1]["findings"] == ["The home page is set to noindex"]
    run_after(h, seo, site, findings=[MEDIUM, CRITICAL])
    assert len(events) == 1
    status = seo.status_one(site)
    assert [f["id"] for f in status["critical"]] == ["noindex"] and status["new_critical"] == [] and status["new_since_baseline"][0]["id"] == "noindex"
    run_after(h, seo, site, findings=[MEDIUM])
    assert [f["id"] for f in seo.status_one(site)["resolved_findings"]] == ["noindex"] and len(events) == 1
    run_after(h, seo, site, findings=[CRITICAL])  # it comes back: announced again
    assert len(events) == 2


def test_the_status_compares_with_the_previous_run_the_baseline_and_per_category(tmp_path):
    h, seo, site, _ = make(tmp_path)
    seo.run(site)
    run_after(h, seo, site, score=90, categories={"technical": 95, "structured_data": 70, "ai_crawlers": 80})
    run_after(h, seo, site, score=86, categories={"technical": 95, "structured_data": 60, "ai_crawlers": 80})
    status = seo.status_one(site)
    assert (status["score"], status["previous_score"], status["delta_previous"], status["baseline_score"], status["delta_baseline"]) == (86, 90, -4, 80, 6)
    by_name = {c["name"]: c for c in status["categories"]}
    assert by_name["structured_data"]["delta_previous"] == -10 and by_name["structured_data"]["delta_baseline"] == -10
    assert by_name["technical"]["delta_previous"] is None and by_name["technical"]["delta_baseline"] == 10
    assert status["runs"] == 3 and status["next_run"] and status["interval_h"] == 24.0


def test_rebaseline_moves_the_reference_to_the_latest_good_run(tmp_path):
    h, seo, site, _ = make(tmp_path)
    with pytest.raises(LookupError):
        seo.rebaseline(site)
    seo.run(site)
    run_after(h, seo, site, score=60)
    h.audit.failure = ("app_down", "x")
    run_after(h, seo, site, hours=1)
    assert seo.rebaseline(site)["score"] == 60
    status = seo.status_one(site)
    assert status["baseline_score"] == 60 and status["delta_baseline"] == 0 and status["state"] == "unavailable"
    assert [r["baseline"] for r in seo.history(site)["runs"]] == [False, True, False]


def test_old_runs_are_trimmed_but_the_baseline_stays(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "MAX_RUNS_KEPT", 3)
    h, seo, site, _ = make(tmp_path)
    for _ in range(6):
        run_after(h, seo, site, hours=1)
    runs = seo.history(site)["runs"]
    assert len(runs) == 4 and runs[-1]["baseline"] is True


def test_the_state_survives_a_restart(tmp_path):
    h, seo, site, _ = make(tmp_path)
    seo.run(site)
    run_after(h, seo, site, score=70)
    again = W.SeoWatcher(h.services.db, h.services.sites.store, emit=lambda t, d: None, clock_fn=h.clock, audit_fn=h.audit.audit_fn)
    assert again.status_one(site)["score"] == 70 and again.status_one(site)["baseline_score"] == 80 and again.tick() == []
