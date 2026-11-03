"""Collect the events a procedure draft is built from: Funes's own foreground windows and recent files, Argus's screenshots and Echo's clipboard.

Read-only. A source that is off or unreachable is reported in ``unavailable`` and never fails the call; clipboard clips Echo hides
(``[oculto]``) arrive without their text. Talos does not record clicks or keystrokes, so none are produced here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from funes_hoard.core.summary import clip_spans
from funes_hoard.queries import get_spans
from funes_hoard.sources import SourceCallError, SourceRegistry, call_source_tool
from funes_hoard.timeparse import iso_local

MAX_FRAMES = 200
MAX_CLIPS = 200


def _iso_to_ts(value: Any):
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except (TypeError, ValueError):
        return None


async def collect_events(db, registry: SourceRegistry, start_ts: float, end_ts: float, *, screen: bool = True, clipboard: bool = True) -> tuple[list[dict], list[str], dict]:
    events: list[dict] = []
    used: list[str] = ["funes"]
    unavailable: dict[str, str] = {}
    for span in clip_spans(get_spans(db, start_ts, end_ts), start_ts, end_ts):
        if span.kind == "active" and (span.app or span.title):
            events.append({"ts": span.start_ts, "type": "focus", "app": span.app, "title": span.title, "ref": f"funes:episode {span.id}"})
    for row in db.query("SELECT ts, path, app_hint FROM file_events WHERE ts >= ? AND ts <= ? ORDER BY ts", (start_ts, end_ts)):
        events.append({"ts": row["ts"], "type": "file", "text": row["path"], "ref": "funes:file", "app": ""})
    wanted = {"argus": screen, "echo": clipboard}
    for source in registry.list():
        if not wanted.get(source.id) or not source.enabled:
            continue
        try:
            if source.id == "argus":
                result = await call_source_tool(source, "screen_timeline", {"from": iso_local(start_ts), "to": iso_local(end_ts), "limit": MAX_FRAMES})
                for frame in result.get("frames", []):
                    ts = _iso_to_ts(frame.get("time"))
                    if ts is not None:
                        events.append({"ts": ts, "type": "screenshot", "app": frame.get("app") or "", "title": frame.get("window_title") or "", "ref": f"argus:moment {frame.get('id')}"})
            else:
                result = await call_source_tool(source, "clip_recent", {"n": MAX_CLIPS})
                for clip in result.get("clips", []):
                    ts = clip.get("last_seen_at")
                    if ts is None or not (start_ts <= float(ts) <= end_ts):
                        continue
                    text = clip.get("preview")
                    events.append({"ts": float(ts), "type": "clipboard", "source_app": clip.get("source_app") or "", "ref": f"echo:clip {clip.get('id')}",
                                   "text": None if text in (None, "[oculto]") else str(text)})
            used.append(source.id)
        except SourceCallError as exc:
            unavailable[source.id] = exc.reason
        except Exception as exc:  # noqa: BLE001 - one source failing must not hide the others
            unavailable[source.id] = type(exc).__name__
    return events, used, unavailable
