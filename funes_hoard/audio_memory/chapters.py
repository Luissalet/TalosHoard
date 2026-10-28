"""Chapters of a meeting: a short list of «where each topic starts» to jump to, in the minutes and on the waveform.

The global language model (through Hoard Link, no tools, one plain chat call) reads the transcript and proposes
``[{"start": "mm:ss", "title": "..."}]``. What it proposed is then made safe by plain code, never trusted as it came:

* every start is moved to the start of the nearest transcript line (a chapter always points at words that exist);
* chapters are sorted, two on the same line become one, one closer than a minute to the previous one is dropped;
* the first chapter starts where the transcript starts;
* titles lose quotes/markdown, collapse to one line and keep at most six words;
* at most twelve remain (the closest pairs are thinned first) and fewer than two means «no chapters» rather than a made-up list.

Method (prompt rules, clean-up order, three-minute minimum) follows the chapter step of a meeting recorder published under the MIT
licence; see ``NOTICE-meeting-recorder.md``.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .db import Database
from .export import hms
from .settings import SettingsStore
from .store import SessionStore

log = logging.getLogger("scribe.chapters")

AUTO_KINDS = ("meeting", "interview")
MIN_DURATION_S = 180.0  # shorter recordings do not need chapters
MIN_CHAPTERS, MAX_CHAPTERS = 2, 12
MIN_GAP_S = 60.0
MAX_TITLE_WORDS = 6
MAX_TITLE_CHARS = 80
PROMPT_CHARS = 60000
LINE_CAPS = (220, 120, 70, 40)
MAX_TOKENS = 3000

SYSTEM_PROMPT = (
    "You get the transcript of a meeting, one line per turn, as `[mm:ss] speaker: text`. The speaker `yo` is the user (microphone), "
    "`otros` is everyone else (system audio) and `S1` is a single track. Divide it into chapters for someone who wants to jump "
    "straight to the part they need.\n"
    "Rules:\n"
    "- One chapter for every 5 to 10 minutes or so, following the topics: at least 2, at most 12.\n"
    "- The first chapter starts at the first line.\n"
    "- Every chapter starts at the time of an existing line, copied exactly.\n"
    "- Titles are 2 to 6 words, specific to what is discussed, in the language of the transcript, without numbering or quotes.\n"
    'Reply with only a JSON array and nothing else, like: [{"start": "00:00", "title": "Opening and agenda"}]'
)


class ChaptersError(RuntimeError):
    """The model answered something unusable or failed; the text says what, for the user."""


class _NoModel(RuntimeError):
    """No language model resolved; surfaces as status `no_model`."""


# ------------------------------------------------------------------- parsing --
def parse_clock(value: Any) -> float | None:
    """«mm:ss», «h:mm:ss» or a number of seconds, as seconds; None when it is not a time."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    text = str(value or "").strip().strip("[]() ")
    if not text:
        return None
    parts = text.split(":")
    if len(parts) > 3:
        return None
    try:
        numbers = [float(p) for p in parts]
    except ValueError:
        return None
    if any(n < 0 for n in numbers):
        return None
    total = 0.0
    for n in numbers:
        total = total * 60 + n
    return total


def parse_items(answer: str) -> list[dict]:
    """The chapter objects in a model answer, wherever the JSON sits (code fences and chatter around it are ignored)."""
    text = (answer or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    candidates = [text]
    if "[" in text and "]" in text:
        candidates.append(text[text.find("["): text.rfind("]") + 1])
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{"): text.rfind("}") + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict):
            for key in ("chapters", "capitulos", "capítulos", "items"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    return []


def clean_title(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"^\s*(?:cap[ií]tulo\s*)?\d+\s*[.):\-–]\s*", "", text, flags=re.IGNORECASE)  # «1. Apertura»
    text = text.strip(" \"'“”«»*#_`")
    words = text.split(" ")
    if len(words) > MAX_TITLE_WORDS:
        text = " ".join(words[:MAX_TITLE_WORDS]).rstrip(" ,;:–-")
    return text[:MAX_TITLE_CHARS].strip()


def sanitize(items: list[dict], starts: list[float]) -> list[dict]:
    """Chapters safe to show: ``[{"start_s", "title"}]`` on real line starts, sorted, spaced, the first at the beginning."""
    if not starts:
        return []
    starts = sorted(set(float(s) for s in starts))
    snapped: list[dict] = []
    for item in items:
        asked = parse_clock(item.get("start", item.get("t", item.get("time"))))
        title = clean_title(item.get("title", item.get("name")))
        if asked is None or not title:
            continue
        nearest = min(starts, key=lambda s: (abs(s - asked), s))
        snapped.append({"start_s": round(nearest, 2), "title": title})
    snapped.sort(key=lambda c: c["start_s"])
    kept: list[dict] = []
    for chapter in snapped:
        if kept and chapter["start_s"] == kept[-1]["start_s"]:
            continue  # one chapter per line: the first one asked for wins
        if kept and chapter["start_s"] - kept[-1]["start_s"] < MIN_GAP_S:
            continue
        kept.append(chapter)
    if not kept:
        return []
    kept[0]["start_s"] = round(starts[0], 2)
    while len(kept) > MAX_CHAPTERS:  # thin the closest pair first, never the opening one
        gaps = [(kept[i]["start_s"] - kept[i - 1]["start_s"], i) for i in range(1, len(kept))]
        kept.pop(min(gaps)[1])
    return kept if len(kept) >= MIN_CHAPTERS else []


def prompt_lines(segments: list[dict]) -> str:
    """The transcript as prompt text, shortened line by line (then by skipping lines) until it fits in PROMPT_CHARS."""
    lines = [(s["start_s"], s["speaker"], re.sub(r"\s+", " ", s["text"]).strip()) for s in segments if s["text"].strip()]
    for cap in LINE_CAPS:
        text = "\n".join(f"[{hms(t)}] {who}: {body[:cap]}" for t, who, body in lines)
        if len(text) <= PROMPT_CHARS:
            return text
    step = -(-len(text) // PROMPT_CHARS)
    return "\n".join(f"[{hms(t)}] {who}: {body[:LINE_CAPS[-1]]}" for t, who, body in lines[::step])


def render_chapters_md(chapters: list[dict], heading: int = 2) -> str:
    lines = [f"{'#' * heading} Capítulos", ""] + [f"- `{hms(c['start_s'])}` {c['title']}" for c in chapters]
    return "\n".join(lines).rstrip() + "\n"


# ------------------------------------------------------------------- storage --
class ChaptersStore:
    def __init__(self, db: Database):
        self.db = db

    def get(self, session_id: str) -> dict | None:
        with self.db.lock:
            row = self.db.conn.execute("SELECT * FROM chapters WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return {"session_id": row["session_id"], "chapters": json.loads(row["items"] or "[]"), "model": row["model"],
                "created_at": row["created_at"], "stats": json.loads(row["stats"] or "{}")}

    def save(self, session_id: str, chapters: list[dict], model: str, created_at: float, stats: dict) -> None:
        with self.db.lock:
            self.db.conn.execute(
                "INSERT INTO chapters(session_id, items, model, created_at, stats) VALUES (?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET "
                "items = excluded.items, model = excluded.model, created_at = excluded.created_at, stats = excluded.stats",
                (session_id, json.dumps(chapters, ensure_ascii=False), model, created_at, json.dumps(stats)))

    def delete(self, session_id: str) -> bool:
        with self.db.lock:
            return self.db.conn.execute("DELETE FROM chapters WHERE session_id = ?", (session_id,)).rowcount > 0


# ------------------------------------------------------------------- service --
class ChaptersService:
    """Generate, store and serve chapters. ``link_provider`` returns the host's Hoard Link (or None)."""

    def __init__(self, db: Database, sessions: SessionStore, settings: SettingsStore, link_provider: Callable[[], Any] | None = None,
                 now: Callable[[], float] = time.time):
        self.store = ChaptersStore(db)
        self.sessions, self.settings, self.link_provider, self.now = sessions, settings, link_provider, now
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self._active: set[str] = set()
        self._queued: set[str] = set()
        self._last: dict[str, dict] = {}
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scribe-chapters")

    def _link(self):
        try:
            return self.link_provider() if self.link_provider else None
        except Exception:  # noqa: BLE001
            return None

    def availability(self) -> dict:
        link = self._link()
        if link is None:
            return {"available": False, "detail": "No Hoard Link is configured in this app."}
        try:
            res = link.sync.resolve("llm")
        except Exception as error:  # noqa: BLE001
            return {"available": False, "detail": f"{type(error).__name__}: {str(error)[:160]}"}
        if getattr(res, "resolved", False):
            return {"available": True, "model": getattr(res, "model", None), "detail": str(getattr(res, "reason", ""))[:200]}
        return {"available": False, "detail": str(getattr(res, "reason", "no language model resolved"))[:200]}

    def is_generating(self, session_id: str) -> bool:
        with self._guard:
            return session_id in self._active or session_id in self._queued

    def get(self, session_id: str) -> dict | None:
        return self.store.get(session_id)

    def view(self, session_id: str) -> dict:
        """What the UI and the tools show: the chapters (or null), whether they are being written, and whether a model exists."""
        stored = self.store.get(session_id)
        state = {"chapters": stored["chapters"] if stored else None, "model": stored["model"] if stored else "",
                 "created_at": stored["created_at"] if stored else None, "generating": self.is_generating(session_id),
                 "last": self._last.get(session_id)}
        if stored is None:
            state["llm"] = self.availability()
        return state

    def discard(self, session_id: str) -> None:
        self.store.delete(session_id)

    def _lock_for(self, session_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(session_id, threading.Lock())

    # ----- generation -----
    def generate(self, session_id: str, regenerate: bool = False, automatic: bool = False) -> dict:
        """Chapters of a transcribed session. Returns ``{status, ...}``; never raises for «no model»."""
        outcome = self._generate(session_id, regenerate, automatic)
        if outcome.get("status") in ("ready", "too_short"):
            self._last.pop(session_id, None)
        else:
            self._last[session_id] = {"status": outcome.get("status"), "detail": outcome.get("detail", "")}
        return outcome

    def _generate(self, session_id: str, regenerate: bool, automatic: bool) -> dict:
        session = self.sessions.get(session_id)
        if session is None:
            raise LookupError(f"Unknown session: {session_id}")
        if session["status"] != "done":
            return {"status": "not_ready", "session_status": session["status"], "detail": "The session is not transcribed yet; try again when its status is done."}
        with self._lock_for(session_id):
            existing = self.store.get(session_id)
            if existing is not None and not regenerate:
                return {"status": "ready", "cached": True, **self._shape(existing)}
            segments = [s for s in self.sessions.segments(session_id) if s["text"].strip()]
            if not segments:
                return {"status": "no_speech", "detail": "The session has no transcribed speech, so there is nothing to divide into chapters."}
            span = segments[-1]["end_s"] - segments[0]["start_s"]
            if span < MIN_DURATION_S:
                return {"status": "too_short", "detail": f"Chapters are made for recordings of at least {int(MIN_DURATION_S // 60)} minutes; this one has {hms(span)}."}
            link = self._link()
            if link is None:
                return {"status": "no_model", "detail": "No Hoard Link is configured in this app."}
            with self._guard:
                self._active.add(session_id)
            try:
                chapters, model, stats = self._write(segments, link)
            except _NoModel as error:
                return {"status": "no_model", "detail": str(error)}
            except ChaptersError as error:
                return {"status": "error", "detail": str(error)}
            finally:
                with self._guard:
                    self._active.discard(session_id)
            created = self.now()
            self.store.save(session_id, chapters, model, created, stats)
        return {"status": "ready", "cached": False, **self._shape(self.store.get(session_id))}

    @staticmethod
    def _shape(stored: dict) -> dict:
        return {"chapters": stored["chapters"], "model": stored["model"], "created_at": stored["created_at"]}

    def _chat(self, link, messages: list[dict]) -> tuple[str, str]:
        """One plain chat call: no tools, no response format."""
        from funes_hoard.hoard_link import BackendError, Unavailable

        try:
            result = link.sync.chat(messages, max_tokens=MAX_TOKENS, temperature=0.1, effort="low")
        except Unavailable as error:
            raise _NoModel("; ".join(error.reasons) or "no language model is available") from error
        except BackendError as error:
            raise ChaptersError(f"The language model call failed: {error}") from error
        except Exception as error:  # noqa: BLE001
            raise ChaptersError(f"The language model call failed ({type(error).__name__}): {str(error)[:160]}") from error
        text = getattr(result, "text", "") or ""
        if not text.strip():
            raise ChaptersError(f"The language model ({getattr(result, 'model', None) or 'unknown'}) returned no text. Try again.")
        return text, str(getattr(result, "model", "") or "")

    def _write(self, segments: list[dict], link) -> tuple[list[dict], str, dict]:
        starts = [float(s["start_s"]) for s in segments]
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": "TRANSCRIPT:\n" + prompt_lines(segments)}]
        text, model = self._chat(link, messages)
        items = parse_items(text)
        attempts = 1
        if not sanitize(items, starts):  # small models forget «JSON only»: one retry with the instruction repeated
            messages += [{"role": "assistant", "content": text[:2000]},
                         {"role": "user", "content": "That was not a usable JSON array of chapters. Answer again with only the JSON array."}]
            text, model = self._chat(link, messages)
            items = parse_items(text)
            attempts = 2
        chapters = sanitize(items, starts)
        if not chapters:
            raise ChaptersError("The language model did not give usable chapters, twice. Try again or use another model.")
        return chapters, model, {"asked": len(items), "kept": len(chapters), "attempts": attempts, "lines": len(segments)}

    def schedule(self, session_id: str, regenerate: bool = False, automatic: bool = False) -> bool:
        """Run generation in the background (one at a time); False when it is already queued or running."""
        with self._guard:
            if session_id in self._queued:
                return False
            self._queued.add(session_id)

        def job() -> None:
            try:
                self.generate(session_id, regenerate=regenerate, automatic=automatic)
            except Exception:  # noqa: BLE001 - a failing job must not kill the pool thread
                log.exception("chapters for %s failed", session_id)
            finally:
                with self._guard:
                    self._queued.discard(session_id)

        try:
            self._pool.submit(job)
        except RuntimeError:  # the pool is closed: the app is shutting down
            with self._guard:
                self._queued.discard(session_id)
            return False
        return True

    def after_transcription(self, session_id: str) -> None:
        """Pipeline hook: a session finished transcribing; write chapters in the background if the user wants them."""
        session = self.sessions.get(session_id)
        if session is None or session["kind"] not in AUTO_KINDS or session["status"] != "done":
            return
        if not self.settings.get().auto_chapters:
            return
        self.schedule(session_id, automatic=True)

    def close(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=True)
