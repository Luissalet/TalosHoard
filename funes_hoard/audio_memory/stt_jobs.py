"""The family's speech-to-text jobs (`transcribe_file`, `transcribe_status`, `transcribe_cancel`).

Stateless on purpose: no session, no row in Funes's database and no copy of the file. A job lives in memory, is kept for an hour
after it finishes (and only the newest fifty finished ones), and runs on the lane the importer uses (one transcription at a time,
one model in memory) through the shared `hoard_link.media.stt.Transcriber`.

Two engines, chosen per job with ``engine``:

* ``whisper`` — faster-whisper, the accurate one (the sessions' own instance, so there is one model in memory).
* ``whistle`` — the small CPU engine (:mod:`funes_hoard.audio_memory.transcribe.whistle`): ~17 MB, seven languages, a few
  hundred milliseconds per short clip, no GPU.
* ``auto`` (default) — the person's settings decide: clips up to ``whistle_short_s`` seconds go to Whistle first, everything
  else to faster-whisper, and Whistle takes over when faster-whisper cannot be loaded here.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from funes_hoard.hoard_link.media import stt
from funes_hoard.hoard_link.proc import Cancelled
from funes_hoard.hoard_link.waiting import DONE_STATES, clamp_wait

from .importer import ALLOWED_EXT, MAX_UPLOAD_BYTES
from .worker import PRIORITY_FINAL, TranscriptionWorker

log = logging.getLogger("scribe.stt")

KEEP_FINISHED_S = 3600.0
KEEP_FINISHED_MAX = 50
LANGUAGE_RE = re.compile(r"^(auto|[A-Za-z]{2,3}(-[A-Za-z]{2,4})?)$")
ENGINES = ("auto", "whisper", "whistle")


class NoModel(RuntimeError):
    """No speech engine can be loaded here: nothing was queued."""


@dataclass
class SttJob:
    id: str
    path: str
    language: str
    model: str | None
    word_timestamps: bool
    initial_prompt: str
    vad: bool
    engine: str = "auto"
    status: str = "queued"  # queued | running | done | error | cancelled
    progress: float = 0.0
    result: dict[str, Any] | None = None
    error: str = ""
    finished_at: float = 0.0
    cancel: threading.Event = field(default_factory=threading.Event)
    finished: threading.Event = field(default_factory=threading.Event)


def check_audio_path(path: str) -> Path:
    """The checks `scribe_import_file` makes: absolute, exists, regular file, allowed extension, 1 byte to 2 GiB."""
    source = Path(path).expanduser()
    if not source.is_absolute():
        raise ValueError("path must be absolute (for example C:\\Users\\me\\Videos\\clase.mp4).")
    if not source.exists():
        raise ValueError(f"No such file: {source}")
    if not source.is_file():
        raise ValueError(f"Not a file: {source}")
    if source.suffix.lower() not in ALLOWED_EXT:
        raise ValueError(f"Unsupported file type {source.suffix.lower() or '(none)'}; allowed: {', '.join(sorted(ALLOWED_EXT))}.")
    size = source.stat().st_size
    if size == 0:
        raise ValueError("The file is empty.")
    if size > MAX_UPLOAD_BYTES:
        raise ValueError(f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB, the import limit.")
    return source


def audio_seconds(path: "str | Path") -> Optional[float]:
    """Length of a file without decoding it: the WAV header, else ffprobe. None when it cannot be known cheaply."""
    source = Path(path)
    if source.suffix.lower() == ".wav":
        try:
            with wave.open(str(source), "rb") as handle:
                rate = handle.getframerate() or 1
                return round(handle.getnframes() / rate, 2)
        except (wave.Error, OSError):
            return None
    try:
        from funes_hoard.hoard_link.media.ffmpeg import FFmpeg

        return round(float(FFmpeg().duration(source)), 2)
    except Exception:  # noqa: BLE001 - no ffprobe, an odd container: the caller treats it as unknown
        return None


class SttJobs:
    """``engine()`` returns the shared transcriber of the sessions (one model in memory); ``engine_for(size)`` a separate one for a
    request that names another Whisper size (closed after the job). ``available()`` says whether faster-whisper can be loaded at all.

    ``whistle()`` returns the small CPU engine (one instance, loaded on first use), ``whistle_available()`` says whether its package
    is installed and ``short_s()`` how many seconds of audio go to it first (0 = never). All three are optional: without them the
    jobs behave exactly as before.
    """

    def __init__(self, worker: TranscriptionWorker, engine: Callable[[], stt.Transcriber],
                 engine_for: Callable[[str], stt.Transcriber], available: Callable[[], bool], clock: Callable[[], float] = time.time,
                 *, whistle: Optional[Callable[[], Any]] = None, whistle_available: Optional[Callable[[], bool]] = None,
                 short_s: Optional[Callable[[], int]] = None):
        self.worker, self._engine, self._engine_for, self._available, self.clock = worker, engine, engine_for, available, clock
        self._whistle, self._whistle_available, self._short_s = whistle, whistle_available, short_s
        self._jobs: dict[str, SttJob] = {}
        self._lock = threading.Lock()

    # ---------- the three tools ----------
    def submit(self, path: str, language: str = "auto", model: str | None = None, word_timestamps: bool = True, initial_prompt: str = "",
               vad: bool = True, wait_s: float = 0.0, engine: str = "auto") -> dict[str, Any]:
        source = check_audio_path(path)
        if not LANGUAGE_RE.match(language or "auto"):
            raise ValueError("language must be 'auto' or a language code such as 'es' or 'en'.")
        engine = (engine or "auto").strip().lower()
        if engine not in ENGINES:
            raise ValueError(f"engine must be one of {', '.join(ENGINES)}.")
        if not self._can_run(engine):
            raise NoModel(self._no_model_message(engine))
        job = SttJob(uuid.uuid4().hex[:12], str(source), language or "auto", model or None, word_timestamps, initial_prompt, vad, engine)
        with self._lock:
            self._prune()
            self._jobs[job.id] = job
        self.worker.submit(f"transcribe {job.id}", lambda: self._run(job), PRIORITY_FINAL)
        return self.status(job.id, wait_s)

    def status(self, job_id: str, wait_s: float = 0.0) -> dict[str, Any]:
        with self._lock:
            self._prune()
            job = self._jobs.get(job_id)
            if job is None:
                raise LookupError(f"no such job: {job_id}")
            should_wait = job.status not in DONE_STATES
        wait = clamp_wait(wait_s)
        if wait and should_wait:
            job.finished.wait(wait)
        view = self._view(job_id)
        if view is None:
            raise LookupError(f"no such job: {job_id}")
        return view

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise LookupError(f"no such job: {job_id}")
            if job.status in DONE_STATES:
                return {"job_id": job.id, "status": job.status}
            job.cancel.set()
            if job.status == "queued":
                self._finish(job, "cancelled")
        return {"job_id": job.id, "status": "cancelled"}

    # ---------- engines ----------
    def engines(self) -> dict[str, Any]:
        """What can transcribe here: both engines, their languages and the rule ``auto`` follows."""
        whistle_ready = bool(self._whistle_available and self._whistle_available())
        whisper_ready = bool(self._available())
        short = int(self._short_s()) if self._short_s else 0
        languages: list[str] = []
        if whistle_ready:
            try:
                from .transcribe.whistle import languages as whistle_languages

                languages = list(whistle_languages())
            except Exception:  # noqa: BLE001 - a listing must never fail
                languages = []
        return {
            "engines": [
                {"name": "whisper", "available": whisper_ready, "device": "auto", "languages": "any",
                 "note": "faster-whisper: the accurate engine, GPU when there is one."},
                {"name": "whistle", "available": whistle_ready, "device": "cpu", "languages": languages,
                 "note": "Small CPU engine (~17 MB): short clips in a few hundred milliseconds."},
            ],
            "default": "auto",
            "auto": {"short_s": short, "whistle_first": bool(short and whistle_ready),
                     "fallback": "whistle" if not whisper_ready and whistle_ready else "whisper"},
        }

    def _can_run(self, engine: str) -> bool:
        if engine == "whistle":
            return bool(self._whistle_available and self._whistle_available())
        if engine == "whisper":
            return bool(self._available())
        return bool(self._available() or (self._whistle_available and self._whistle_available()))

    def _no_model_message(self, engine: str) -> str:
        if engine == "whistle":
            return "Whistle is not installed: pip install cactus-compute, or ask for engine='whisper'."
        if engine == "whisper":
            return "faster-whisper is not available here: pip install faster-whisper, or ask for engine='whistle'."
        return "No speech engine is available: install faster-whisper (pip install faster-whisper) or Whistle (pip install cactus-compute)."

    def _pick(self, job: SttJob) -> tuple[Any, bool, str]:
        """The engine for this job: (object, owned by the job, name). ``owned`` engines are closed afterwards."""
        whistle_ready = bool(self._whistle_available and self._whistle_available())
        if job.engine == "whistle":
            return self._whistle(), False, "whistle"
        if job.engine == "whisper":
            return (self._engine_for(job.model) if job.model else self._engine()), bool(job.model), "whisper"
        short = int(self._short_s()) if self._short_s else 0
        if short and whistle_ready:
            seconds = audio_seconds(job.path)
            if seconds is not None and seconds <= short:
                return self._whistle(), False, "whistle"
        if self._available():
            return (self._engine_for(job.model) if job.model else self._engine()), bool(job.model), "whisper"
        return self._whistle(), False, "whistle"

    # ---------- internals ----------
    def _view(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            view: dict[str, Any] = {"job_id": job.id, "status": job.status, "progress": round(job.progress, 3), "engine": job.engine}
            if job.status == "done" and job.result is not None:
                view.update(job.result)
                view["progress"] = 1.0
            if job.error:
                view["error"] = job.error
            return view

    def _finish(self, job: SttJob, status: str, *, result: dict[str, Any] | None = None, error: str = "") -> None:
        job.status, job.result, job.error, job.finished_at = status, result, error, self.clock()
        job.finished.set()

    def _prune(self) -> None:
        now = self.clock()
        finished = sorted((j for j in self._jobs.values() if j.status in DONE_STATES), key=lambda j: j.finished_at)
        for job in finished:
            if now - job.finished_at > KEEP_FINISHED_S:
                del self._jobs[job.id]
        finished = [j for j in finished if j.id in self._jobs]
        for job in finished[: max(0, len(finished) - KEEP_FINISHED_MAX)]:
            del self._jobs[job.id]

    def _run(self, job: SttJob) -> None:
        with self._lock:
            if job.status != "queued":  # cancelled while it waited
                return
            job.status = "running"

        def progress(fraction: float) -> None:
            job.progress = max(job.progress, min(0.99, float(fraction)))

        engine: Any = None
        owned = False
        try:
            engine, owned, name = self._pick(job)
            result = engine.transcribe(job.path, language=None if job.language == "auto" else job.language, word_timestamps=job.word_timestamps,
                                       vad=job.vad, initial_prompt=job.initial_prompt, progress=progress, cancel=job.cancel)
            payload = result.as_dict()
            payload["engine"] = name
            with self._lock:
                self._finish(job, "done", result=payload)
        except Cancelled:
            with self._lock:
                self._finish(job, "cancelled")
        except Exception as error:  # noqa: BLE001 - a failed job is reported, never raised into the worker
            log.exception("transcription job %s failed", job.id)
            with self._lock:
                self._finish(job, "error", error=str(error)[:500])
        finally:
            if owned and engine is not None:
                engine.close()