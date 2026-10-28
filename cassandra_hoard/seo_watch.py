"""SEO / GEO watch of the public sites: the audit the design Hoard offers (``site_audit``), run on a schedule, with drift.

The sites are the ones the site watcher already knows (``data/sites.json``). A site opts in with ``seo_interval_h``
(hours between audits, 1 to 720); sites without it are never audited. Each audit is one call of the tool ``site_audit``
of the Vitruvius app through the hub (this module checks nothing itself: it reads the audit's score, the score per
category and the findings, and compares them with the run before).

* **Baseline.** The first successful audit of a site is its baseline; ``rebaseline`` accepts the latest one as the new
  reference (after a fix or an intended change).
* **Drift between runs.** Every run stores the score change against the run before, the categories that moved and the
  findings that appeared or were resolved; the view also compares with the baseline.
* **Alerts.** ``cassandra.site.seo_drop`` when the score is at least ``seo_drop_points`` (default 2) below the best of
  the last seven runs and this run is lower than the one before (a score that stays low is announced once, one that
  keeps falling is announced again); ``cassandra.site.seo_critical`` when a critical finding appears that the run before
  did not have. The very first run is a baseline: nothing is announced. A failed audit (Vitruvius not running, no such
  tool yet) is stored with its cause and retried later; it never raises an alert.

The audit's answer is the envelope ``site-audit/1`` of Vitruvius (contract in its ``docs/SITE-AUDIT.md``): ``score`` and
``scores.total`` (0-100), ``categories`` as a list of ``{id, score, measured, findings}`` (a category that could not be measured
has ``score: null`` and is left out, so it is never read as a worsening), the flat ``findings`` list of
``{id, category, severity, title, judgement, url?}`` and, when the audit fails, ``{ok: false, error, error_kind, hint}``.
Findings with ``judgement: true`` need a person to decide: they never score, so they are counted apart and take no part in
the drift or in the alerts. The reader stays tolerant of other shapes: ``categories`` as an object ``{name: score}``,
severity words like ``warning``. A finding is the same finding in two runs when its ``id`` matches (a check that fails on
two pages has two ids), or its category and title when it has none.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Callable, Optional

from .sites import SITE_PREFIX
from .times import iso

DEFAULT_INTERVAL_H = 24.0
MIN_INTERVAL_H = 1.0
MAX_INTERVAL_H = 720.0
DEFAULT_DROP_POINTS = 2.0
RECENT_RUNS = 7
RETRY_S = 3600.0  # a failed audit is tried again an hour later
TICK_S = 60.0
TIMEOUT_S = 600.0
MAX_FINDINGS = 200
MAX_RUNS_KEPT = 400  # per site

EV_DROP = "cassandra.site.seo_drop"
EV_CRITICAL = "cassandra.site.seo_critical"

SEVERITIES = ("critical", "high", "medium", "low", "info")
_SEVERITY_WORDS = {
    "critical": "critical", "blocker": "critical", "severe": "critical", "fatal": "critical",
    "high": "high", "error": "high", "major": "high",
    "medium": "medium", "moderate": "medium", "warning": "medium", "warn": "medium",
    "low": "low", "minor": "low",
    "info": "info", "notice": "info", "pass": "info", "ok": "info", "note": "info",
}


# ---------------------------------------------------------------------------
# the audit's answer -> one flat report
# ---------------------------------------------------------------------------

def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().rstrip("%"))
        except ValueError:
            return None
    return None


def _score(value: Any) -> Optional[float]:
    """A 0-100 score; ``{score, max}`` objects are scaled, out-of-range values refused."""
    if isinstance(value, dict):
        top = _number(value.get("max") or value.get("out_of"))
        raw = _number(value.get("score") if "score" in value else value.get("value"))
        if raw is None:
            return None
        value = raw * 100.0 / top if top and top > 0 and top != 100 else raw
    number = _number(value)
    if number is None or not 0.0 <= number <= 100.0:
        return None
    return round(number, 2)


def _unwrap(data: Any) -> dict[str, Any]:
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError as error:
            raise ValueError("the audit answered with text that is not JSON") from error
    for _ in range(3):
        if not isinstance(data, dict):
            break
        if any(k in data for k in ("score", "scores", "findings", "categories")):
            return data
        inner = next((data[k] for k in ("audit", "report", "result", "data", "envelope") if isinstance(data.get(k), (dict, str))), None)
        if inner is None:
            break
        data = json.loads(inner) if isinstance(inner, str) else inner
    if not isinstance(data, dict):
        raise ValueError("the audit's answer is not an object")
    return data


def _severity(value: Any) -> str:
    return _SEVERITY_WORDS.get(str(value or "").strip().lower(), "medium")


def finding_key(item: dict[str, Any]) -> str:
    ident = str(item.get("id") or "").strip()
    return ident.lower() if ident else (str(item.get("category") or "").strip().lower() + "|" + re.sub(r"\s+", " ", str(item.get("title") or "").strip().lower()))


def normalize_report(data: Any) -> dict[str, Any]:
    """``{score, categories: {name: score}, findings: [{key, id, severity, title, category}], counts}``; ValueError says what is missing
    or why the audit failed. ``counts`` has a number per severity and ``judgement`` (findings left to a person, not in ``findings``)."""
    raw = _unwrap(data)
    if raw.get("ok") is False:
        detail = " ".join(str(raw.get(k)) for k in ("error", "hint") if raw.get(k))
        raise ValueError(f"the audit failed ({raw.get('error_kind') or 'error'}): {detail or 'no detail'}"[:300])
    scores = raw.get("scores")
    total = _score(raw.get("score"))
    if total is None and isinstance(scores, dict):
        total = _score(scores.get("total") if "total" in scores else scores.get("overall"))
    categories: dict[str, float] = {}
    source = raw.get("categories")
    if source is None and isinstance(scores, dict):
        source = {k: v for k, v in scores.items() if k not in ("total", "overall")}
    if isinstance(source, dict):
        for name, value in source.items():
            score = _score(value)
            if score is not None:
                categories[str(name)[:60]] = score
    elif isinstance(source, list):
        for item in source:
            if isinstance(item, dict):
                name = str(item.get("id") or item.get("name") or item.get("category") or "").strip()[:60]
                score = _score(item.get("score"))
                if name and score is not None:
                    categories[name] = score
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    judgement = 0
    for item in raw.get("findings") if isinstance(raw.get("findings"), list) else []:
        if not isinstance(item, dict):
            continue
        if item.get("judgement") is True:
            judgement += 1
            continue
        title = re.sub(r"\s+", " ", str(item.get("title") or item.get("message") or item.get("summary") or "").strip())[:240]
        if not title and not item.get("id"):
            continue
        entry = {"id": str(item.get("id") or "")[:80], "severity": _severity(item.get("severity") or item.get("level") or item.get("priority")),
                 "title": title or str(item.get("id")), "category": str(item.get("category") or item.get("area") or "")[:60]}
        entry["key"] = finding_key(entry)
        if entry["key"] in seen:
            continue
        seen.add(entry["key"])
        findings.append(entry)
    findings.sort(key=lambda f: (SEVERITIES.index(f["severity"]), f["category"], f["title"]))
    if total is None and categories:
        total = round(sum(categories.values()) / len(categories), 2)  # no global score: the mean of the categories
    if total is None:
        raise ValueError("the audit's answer has no score (expected `score`, `scores.total` or `categories`)")
    counts = {sev: sum(1 for f in findings if f["severity"] == sev) for sev in SEVERITIES}
    counts["judgement"] = judgement
    return {"score": total, "categories": categories, "findings": findings[:MAX_FINDINGS], "counts": counts, "findings_total": len(findings)}


def compare(previous: Optional[dict[str, Any]], current: dict[str, Any]) -> dict[str, Any]:
    """What changed from ``previous`` to ``current`` (both normalized reports); ``previous`` None -> everything is new and nothing is a delta."""
    if previous is None:
        return {"score_delta": None, "categories": {}, "new": [], "resolved": [], "new_critical": [], "critical_open": current["counts"]["critical"]}
    before = {f["key"]: f for f in previous["findings"]}
    after = {f["key"]: f for f in current["findings"]}
    new = [f for k, f in after.items() if k not in before]
    resolved = [f for k, f in before.items() if k not in after]
    categories = {}
    for name in sorted(set(previous["categories"]) | set(current["categories"])):
        a, b = previous["categories"].get(name), current["categories"].get(name)
        if a is not None and b is not None and round(b - a, 2) != 0:
            categories[name] = round(b - a, 2)
    return {"score_delta": round(current["score"] - previous["score"], 2), "categories": categories,
            "new": [_brief(f) for f in new], "resolved": [_brief(f) for f in resolved],
            "new_critical": [_brief(f) for f in new if f["severity"] == "critical"], "critical_open": current["counts"]["critical"]}


def _brief(finding: dict[str, Any]) -> dict[str, Any]:
    return {k: finding[k] for k in ("id", "severity", "title", "category") if finding.get(k)}


def vitruvius_audit(url: str) -> dict[str, Any]:
    """The default auditor: the tool ``site_audit`` of the Vitruvius app, through the hub (classified answer, never raises)."""
    from .hoard_link import _famsvc
    return _famsvc.call_tool("vitruvius", "site_audit", {"url": url}, timeout_s=TIMEOUT_S)


_KIND_TEXT = {
    "tool_missing": "Vitruvius does not offer the audit (site_audit) yet: update Vitruvius.",
    "app_missing": "Vitruvius is not registered in the hub.",
    "app_down": "Vitruvius is not running.",
    "hub_down": "The hub is not reachable.",
    "timeout": "The audit took longer than ten minutes.",
    "auth": "The hub refused this app's token.",
}


# ---------------------------------------------------------------------------
# the schedule
# ---------------------------------------------------------------------------

def interval_h(site: dict[str, Any]) -> Optional[float]:
    value = site.get("seo_interval_h")
    return float(value) if value else None


def drop_points(site: dict[str, Any]) -> float:
    return float(site.get("seo_drop_points") or DEFAULT_DROP_POINTS)


class SeoWatcher:
    """Runs the audits (its own thread: an audit can take minutes and must not delay the up/down checks)."""

    def __init__(self, db, store, *, emit: Callable[[str, dict[str, Any]], None], clock_fn: Callable[[], float] = time.time,
                 audit_fn: Optional[Callable[[str], dict[str, Any]]] = None, tick_s: float = TICK_S, enabled: bool = True,
                 retry_s: float = RETRY_S):
        self.db = db
        self.store = store
        self.emit = emit
        self.clock = clock_fn
        self.audit_fn = audit_fn or vitruvius_audit
        self.tick_s = max(1.0, float(tick_s))
        self.enabled = enabled
        self.retry_s = float(retry_s)
        self.running_site: Optional[str] = None
        self.last_error: Optional[str] = None
        self.sent = 0
        self._forced: set[str] = set()
        self._lock = threading.RLock()
        self._run_lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ----- thread
    def start(self) -> None:
        if not self.enabled or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="cassandra-seo", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
                self.last_error = None
            except Exception as error:  # noqa: BLE001 - one bad tick never stops the watch
                self.last_error = f"{type(error).__name__}: {error}"
            self._wake.wait(self.tick_s)
            self._wake.clear()

    def tick(self) -> list[str]:
        """Audit every opted-in site whose time has come (and the ones asked for by hand); returns the ids audited."""
        done: list[str] = []
        for site in self.store.list():
            if self._stop.is_set():
                break
            wanted = site["id"] in self._forced
            if not wanted and (not site["enabled"] or interval_h(site) is None or self.clock() < self.next_due(site)):
                continue
            with self._lock:
                self._forced.discard(site["id"])
            try:
                self.run(site)
            except Exception as error:  # noqa: BLE001
                self.last_error = f"{site['id']}: {type(error).__name__}: {error}"
            done.append(site["id"])
        return done

    def wake(self) -> None:
        self._wake.set()

    def busy(self, sid: str) -> bool:
        """An audit of ``sid`` is running or has been asked for and not started yet."""
        with self._lock:
            return self.running_site == sid or sid in self._forced

    def request(self, site: dict[str, Any]) -> bool:
        """Ask for an audit now (the thread does it). False when that site is being audited already."""
        with self._lock:
            if self.running_site == site["id"]:
                return False
            if not (site["enabled"] and interval_h(site) and self.clock() >= self.next_due(site)):  # a site that is due anyway needs no push
                self._forced.add(site["id"])
        self._wake.set()
        return True

    # ----- storage
    def _rows(self, sid: str, limit: int, ok_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM seo_runs WHERE site = ?" + (" AND ok = 1" if ok_only else "") + " ORDER BY ts DESC, id DESC LIMIT ?"
        return [self._row(r) for r in self.db.query(sql, (sid, limit))]

    @staticmethod
    def _row(row) -> dict[str, Any]:
        out = {k: row[k] for k in row.keys()}
        for key in ("categories", "findings", "counts", "drift"):
            try:
                out[key] = json.loads(out.get(key) or ("{}" if key != "findings" else "[]"))
            except ValueError:
                out[key] = {} if key != "findings" else []
        out["ok"] = bool(out["ok"])
        out["baseline"] = bool(out["baseline"])
        return out

    def last_run(self, sid: str) -> Optional[dict[str, Any]]:
        rows = self._rows(sid, 1)
        return rows[0] if rows else None

    def next_due(self, site: dict[str, Any]) -> float:
        last = self.last_run(site["id"])
        hours = interval_h(site) or DEFAULT_INTERVAL_H
        if last is None:
            return 0.0
        return last["ts"] + (hours * 3600.0 if last["ok"] else min(self.retry_s, hours * 3600.0))

    # ----- one audit
    def run(self, site: dict[str, Any]) -> dict[str, Any]:
        with self._run_lock:
            with self._lock:
                self.running_site = site["id"]
            try:
                return self._audit(site)
            finally:
                with self._lock:
                    self.running_site = None

    def _audit(self, site: dict[str, Any]) -> dict[str, Any]:
        sid = site["id"]
        started = time.monotonic()
        try:
            answer = self.audit_fn(site["url"])
        except Exception as error:  # noqa: BLE001 - a broken auditor is a failed run
            answer = {"ok": False, "kind": "tool_error", "error": f"{type(error).__name__}: {error}"}
        ms = int((time.monotonic() - started) * 1000)
        now = self.clock()
        report: Optional[dict[str, Any]] = None
        kind, error = "", ""
        if answer.get("ok"):
            try:
                report = normalize_report(answer.get("data"))
            except ValueError as problem:
                kind, error = "bad_answer", str(problem)
        else:
            kind = str(answer.get("kind") or "tool_error")
            error = _KIND_TEXT.get(kind) or str(answer.get("error") or "the audit failed")[:300]
            refused = answer.get("data")
            if kind == "tool_error" and isinstance(refused, dict) and refused.get("ok") is False and refused.get("error_kind"):
                # the audit answered `ok: false`: its own cause (and hint) is kept; the run is retried later and the last score stays
                kind = "audit_failed"
                error = " ".join(str(x) for x in (f"{refused['error_kind']}:", refused.get("error"), refused.get("hint")) if x)[:300]
        if report is None:
            self.db.execute(
                "INSERT INTO seo_runs(site, ts, ok, error_kind, error, score, categories, findings, counts, baseline, drift, ms) "
                "VALUES (?, ?, 0, ?, ?, NULL, '{}', '[]', '{}', 0, '{}', ?)", (sid, now, kind, error[:500], ms))
            return self.last_run(sid) or {}
        previous = next(iter(self._rows(sid, 1, ok_only=True)), None)
        recent = self._rows(sid, RECENT_RUNS, ok_only=True)
        has_baseline = bool(self.db.query("SELECT 1 FROM seo_runs WHERE site = ? AND baseline = 1 LIMIT 1", (sid,)))
        drift = compare(previous and {"score": previous["score"], "categories": previous["categories"], "findings": previous["findings"],
                                      "counts": previous["counts"]}, report)
        self.db.execute(
            "INSERT INTO seo_runs(site, ts, ok, error_kind, error, score, categories, findings, counts, baseline, drift, ms) "
            "VALUES (?, ?, 1, '', '', ?, ?, ?, ?, ?, ?, ?)",
            (sid, now, report["score"], json.dumps(report["categories"], ensure_ascii=False), json.dumps(report["findings"], ensure_ascii=False),
             json.dumps({**report["counts"], "total": report["findings_total"]}), 0 if has_baseline else 1, json.dumps(drift, ensure_ascii=False), ms))
        self.db.execute("DELETE FROM seo_runs WHERE site = ? AND baseline = 0 AND id NOT IN "
                        "(SELECT id FROM seo_runs WHERE site = ? ORDER BY ts DESC, id DESC LIMIT ?)", (sid, sid, MAX_RUNS_KEPT))
        if previous is not None:
            self._alerts(site, report, previous, recent, drift, now)
        return self.last_run(sid) or {}

    def _announce(self, type_: str, data: dict[str, Any]) -> None:
        try:
            self.emit(type_, data)
            self.sent += 1
        except Exception:  # noqa: BLE001 - a broken transport never stops the watch
            pass

    def _event(self, sid: str, ts: float, detail: str) -> None:
        self.db.execute("INSERT INTO events(service, ts, kind, from_state, to_state, detail) VALUES (?, ?, 'seo', NULL, NULL, ?)",
                        (SITE_PREFIX + sid, ts, detail[:500]))

    def _alerts(self, site: dict[str, Any], report: dict[str, Any], previous: dict[str, Any], recent: list[dict[str, Any]],
                drift: dict[str, Any], now: float) -> None:
        base = {"site": site["id"], "name": site["name"], "url": site["url"], "score": report["score"]}
        best = max((r["score"] for r in recent), default=previous["score"])
        threshold = drop_points(site)
        if best - report["score"] >= threshold and report["score"] < previous["score"]:
            text = f"SEO/GEO score {report['score']:g}, {best - report['score']:g} below the recent best ({best:g}); previous run {previous['score']:g}"
            self._event(site["id"], now, text)
            self._announce(EV_DROP, {**base, "previous": previous["score"], "best": best, "drop": round(best - report["score"], 2),
                                     "threshold": threshold})
        if drift["new_critical"]:
            titles = [f["title"] for f in drift["new_critical"]][:5]
            self._event(site["id"], now, f"{len(drift['new_critical'])} new critical SEO/GEO finding(s): " + "; ".join(titles))
            self._announce(EV_CRITICAL, {**base, "count": len(drift["new_critical"]), "findings": titles})

    # ----- the baseline
    def rebaseline(self, site: dict[str, Any]) -> dict[str, Any]:
        """The latest successful run becomes the reference."""
        sid = site["id"]
        latest = next(iter(self._rows(sid, 1, ok_only=True)), None)
        if latest is None:
            raise LookupError(f"{site['name']} has no successful audit yet.")
        self.db.execute("UPDATE seo_runs SET baseline = 0 WHERE site = ?", (sid,))
        self.db.execute("UPDATE seo_runs SET baseline = 1 WHERE id = ?", (latest["id"],))
        self._event(sid, self.clock(), f"baseline moved to the audit of {iso(latest['ts'])} (score {latest['score']:g})")
        return {"id": latest["id"], "ts": iso(latest["ts"]), "score": latest["score"]}

    # ----- views
    def _baseline(self, sid: str) -> Optional[dict[str, Any]]:
        rows = [self._row(r) for r in self.db.query("SELECT * FROM seo_runs WHERE site = ? AND baseline = 1 ORDER BY ts DESC LIMIT 1", (sid,))]
        return rows[0] if rows else None

    def status_one(self, site: dict[str, Any], now: Optional[float] = None) -> dict[str, Any]:
        now = self.clock() if now is None else now
        sid = site["id"]
        hours = interval_h(site)
        last = self.last_run(sid)
        ok_runs = self._rows(sid, 2, ok_only=True)
        current = ok_runs[0] if ok_runs else None
        baseline = self._baseline(sid)
        if hours is None and last is None:
            state = "off"
        elif self.running_site == sid:
            state = "running"
        elif last is None:
            state = "pending"
        elif not last["ok"]:
            state = "unavailable"
        else:
            state = "ok"
        out: dict[str, Any] = {
            "id": sid, "name": site["name"], "url": site["url"], "state": state, "interval_h": hours,
            "drop_points": drop_points(site) if hours else None,
            "last_run": iso(last["ts"]) if last else None, "last_run_ts": last["ts"] if last else None,
            "next_run": iso(max(now, self.next_due(site))) if hours and site["enabled"] else None,
            "runs": int(self.db.query("SELECT COUNT(*) AS n FROM seo_runs WHERE site = ?", (sid,))[0]["n"]),
            "error": last["error"] if last and not last["ok"] else None, "error_kind": last["error_kind"] if last and not last["ok"] else None,
            "score": current["score"] if current else None, "scored_at": iso(current["ts"]) if current else None,
        }
        if current:
            drift = current["drift"] or {}
            out.update(
                previous_score=ok_runs[1]["score"] if len(ok_runs) > 1 else None, delta_previous=drift.get("score_delta"),
                categories=[{"name": n, "score": s, "delta_previous": (drift.get("categories") or {}).get(n),
                             "delta_baseline": round(s - baseline["categories"][n], 2) if baseline and n in baseline["categories"] else None}
                            for n, s in sorted(current["categories"].items())],
                counts=current["counts"], critical=[_brief(f) for f in current["findings"] if f["severity"] == "critical"],
                high=[_brief(f) for f in current["findings"] if f["severity"] == "high"][:10],
                new_findings=drift.get("new") or [], resolved_findings=drift.get("resolved") or [], new_critical=drift.get("new_critical") or [],
                baseline_score=baseline["score"] if baseline else None, baseline_at=iso(baseline["ts"]) if baseline else None,
                delta_baseline=round(current["score"] - baseline["score"], 2) if baseline else None)
            if baseline:
                before = {f["key"] for f in baseline["findings"]}
                out["new_since_baseline"] = [_brief(f) for f in current["findings"] if f["key"] not in before][:20]
        return out

    def status_all(self, now: Optional[float] = None) -> list[dict[str, Any]]:
        return [self.status_one(s, now) for s in self.store.list()]

    def history(self, site: dict[str, Any], limit: int = 20) -> dict[str, Any]:
        rows = self._rows(site["id"], max(1, min(int(limit), 200)))
        return {"site": site["id"], "name": site["name"], "url": site["url"], "runs": [
            {"id": r["id"], "at": iso(r["ts"]), "ok": r["ok"], "score": r["score"], "baseline": r["baseline"],
             "delta_previous": (r["drift"] or {}).get("score_delta"), "findings": (r["counts"] or {}).get("total"),
             "critical": (r["counts"] or {}).get("critical"), "new": len((r["drift"] or {}).get("new") or []),
             "resolved": len((r["drift"] or {}).get("resolved") or []), "seconds": round((r["ms"] or 0) / 1000, 1),
             "error": r["error"] or None} for r in rows]}

    def summary(self) -> dict[str, Any]:
        sites = [s for s in self.store.list() if interval_h(s) is not None]
        return {"watching": len(sites), "running": self.running, "enabled": self.enabled, "auditing": self.running_site,
                "error": self.last_error, "events_sent": self.sent}
