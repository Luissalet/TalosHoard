"""Transcription bench: recordings that are hard on purpose, scored against what was really said.

Each case in ``bench_fixtures/`` is a call recorded as the app records it (a microphone track and a system track) plus
``truth.json``, the script with who said every line, on which side, when and the words. The bench runs the *configured*
engine through the app's own path (silence gate → model → hallucination filter → echo clean-up → track merge) and reports,
per case:

* ``found``   share of the script's words that are in the transcript near the right moment;
* ``side``    of those, share attributed to the right side of the call (``yo`` microphone / ``otros`` system);
* ``leaked``  microphone lines that are really the other side coming back through the speakers;
* ``invented`` lines whose words are not in the script around them (hallucinations on music or silence);
* ``extra``   share of the transcript's words that match nothing in the script;
* ``lines``   lines in the transcript (the silence case must have none);
* ``seconds`` how long the transcription took.

Every case is also scored without the echo clean-up from the same model output, so its effect is measured, not assumed.

Cases: ``call`` (headset, people interrupt each other and say «yeah» in between), ``call-speakers`` (the same call through speakers:
the other side leaks into the microphone 40 ms late), ``music`` (the other side talks over background music) and ``silence``
(room noise only). Recordings and script format come from a meeting recorder published under the MIT licence; the recordings are
CC0. See ``NOTICE-meeting-recorder.md``.
"""

from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .audio import TRACK_MIC, TRACK_SYSTEM
from .audio.wav import SAMPLE_RATE, read_wav
from .echo import drop_echo
from .importer import convert_to_wav
from .merge import Labelled, coalesce, merge_tracks
from .transcribe.base import Transcriber
from .transcribe.filter import FilterStats, guarded_transcribe
from .worker import PRIORITY_FINAL, TranscriptionWorker

log = logging.getLogger("scribe.bench")

FIXTURES_DIR = Path(__file__).resolve().parent / "bench_fixtures"
THRESHOLDS_FILE = FIXTURES_DIR / "thresholds.json"
WINDOW_S = 1.5  # a transcribed word counts for a script line when it falls this close to the line
KEEP_RESULTS = 20


# ------------------------------------------------------------------- cases --
@dataclass
class TruthLine:
    speaker: str
    side: str  # mic | computer
    start: float
    end: float
    text: str


@dataclass
class Case:
    name: str
    about: str
    tracks: dict[str, Path]  # mic / computer
    truth: list[TruthLine]


def case_names() -> list[str]:
    if not FIXTURES_DIR.is_dir():
        return []
    return sorted(p.name for p in FIXTURES_DIR.iterdir() if (p / "meta.json").is_file())


def load_case(name: str) -> Case:
    folder = FIXTURES_DIR / name
    if not (folder / "meta.json").is_file():
        raise LookupError(f"Unknown bench case: {name}. Known: {', '.join(case_names()) or 'none'}")
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    truth = json.loads((folder / "truth.json").read_text(encoding="utf-8"))
    lines = [TruthLine(t["speaker"], t["side"], float(t["start"]), float(t["end"]), t["text"]) for t in truth.get("truth", [])]
    tracks = {side: (folder / rel).resolve() for side, rel in meta["tracks"].items()}
    return Case(name, meta.get("about", truth.get("about", "")), tracks, lines)


def load_track(path: Path) -> np.ndarray:
    """Any audio file the importer can read, as 16 kHz mono int16."""
    with tempfile.TemporaryDirectory(prefix="scribe-bench-") as temp:
        target = Path(temp) / "track.wav"
        convert_to_wav(path, target)
        samples, _ = read_wav(target)
    return samples


# ----------------------------------------------------------------- scoring --
def norm_word(raw: str) -> str:
    return "".join(ch for ch in raw.lower() if ch.isalnum())


def _tokens(lines: list[Labelled]) -> list[dict]:
    """Every transcribed word with its time and side; words without timestamps are spread evenly over their line."""
    out: list[dict] = []
    for index, line in enumerate(lines):
        timed = [(w.get("start"), w.get("word", "")) for w in (line.words or []) if norm_word(w.get("word", "")) and w.get("start") is not None]
        if timed:
            for start, word in timed:
                out.append({"t": float(start), "w": norm_word(word), "who": line.speaker, "line": index})
            continue
        words = [norm_word(w) for w in line.text.split() if norm_word(w)]
        span = max(line.end_s - line.start_s, 0.01)
        for i, word in enumerate(words):
            out.append({"t": line.start_s + span * (i + 0.5) / max(len(words), 1), "w": word, "who": line.speaker, "line": index})
    return out


def _truth_words(line: TruthLine) -> list[str]:
    return [w for w in (norm_word(x) for x in line.text.split()) if w]


def score(truth: list[TruthLine], lines: list[Labelled]) -> dict:
    """found / side / leaked / invented / extra / lines for one transcript. See the module docstring."""
    tokens = _tokens(lines)
    used = [False] * len(tokens)
    total = hits = right = 0
    for line in sorted(truth, key=lambda t: t.start):
        words = _truth_words(line)
        want = "yo" if line.side == "mic" else "otros"
        total += len(words)
        for word in words:
            best = None
            for i, tok in enumerate(tokens):
                if used[i] or tok["w"] != word or not (line.start - WINDOW_S <= tok["t"] <= line.end + WINDOW_S):
                    continue
                if tok["who"] == want:
                    best = i
                    break
                if best is None:
                    best = i
            if best is not None:
                used[best] = True
                hits += 1
                right += 1 if tokens[best]["who"] == want else 0

    def support(tok: dict, side: str | None) -> bool:
        return any((side is None or t.side == side) and t.start - WINDOW_S <= tok["t"] <= t.end + WINDOW_S and tok["w"] in _truth_words(t)
                   for t in truth)

    leaked = invented = 0
    for index, line in enumerate(lines):
        mine = [t for t in tokens if t["line"] == index]
        if not mine:
            continue
        if line.speaker == "yo":
            echoed = sum(1 for t in mine if support(t, "computer") and not support(t, "mic"))
            if echoed * 2 >= len(mine):
                leaked += 1
        if sum(1 for t in mine if not support(t, None)) * 2 > len(mine):
            invented += 1
    return {
        "found": round(hits / total, 3) if total else None,
        "side": round(right / hits, 3) if hits else None,
        "leaked": leaked,
        "invented": invented,
        "extra": round(sum(1 for u in used if not u) / len(tokens), 3) if tokens else 0.0,
        "lines": len(lines),
    }


def load_thresholds() -> dict:
    try:
        return json.loads(THRESHOLDS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def meets(case: str, result: dict, thresholds: dict | None = None) -> dict | None:
    """Compare a case's score with the thresholds measured for the default engine; None when the case has none."""
    spec = (thresholds if thresholds is not None else load_thresholds()).get(case)
    if not spec:
        return None
    failures = []
    for key, floor in (spec.get("min") or {}).items():
        value = result.get(key)
        if value is None or value < floor:
            failures.append(f"{key} {value} < {floor}")
    for key, ceiling in (spec.get("max") or {}).items():
        value = result.get(key)
        if value is not None and value > ceiling:
            failures.append(f"{key} {value} > {ceiling}")
    return {"ok": not failures, "failures": failures}


# ------------------------------------------------------------------ running --
def transcribe_case(case: Case, transcriber: Transcriber, language: str = "auto", sensitivity: int = 2) -> dict:
    """The model's output per track (after the silence gate and the hallucination filter) plus the audio, ready to be merged."""
    stats = FilterStats()
    audio = {side: load_track(path) for side, path in case.tracks.items()}
    mapping = {"mic": TRACK_MIC, "computer": TRACK_SYSTEM}
    per_track = {mapping[side]: guarded_transcribe(transcriber, samples, language, sensitivity, stats) for side, samples in audio.items()}
    return {"per_track": per_track, "audio": {mapping[s]: a for s, a in audio.items()}, "stats": stats,
            "duration_s": round(max((len(a) for a in audio.values()), default=0) / SAMPLE_RATE, 1)}


def merge_case(per_track: dict, audio: dict, echo: bool) -> tuple[list[Labelled], int]:
    """Echo clean-up (optional), merge by time and coalesce, exactly as the final pass does."""
    per_track = dict(per_track)
    removed = 0
    if echo and TRACK_MIC in per_track and TRACK_SYSTEM in per_track:
        per_track[TRACK_MIC], dropped = drop_echo(per_track[TRACK_MIC], per_track[TRACK_SYSTEM], audio.get(TRACK_MIC), audio.get(TRACK_SYSTEM))
        removed = dropped.removed
    return coalesce(merge_tracks(per_track)), removed


def run_case(name: str, transcriber: Transcriber, language: str = "auto", sensitivity: int = 2) -> dict:
    case = load_case(name)
    started = time.time()
    out = transcribe_case(case, transcriber, language, sensitivity)
    seconds = round(time.time() - started, 1)
    lines, removed = merge_case(out["per_track"], out["audio"], echo=True)
    plain, _ = merge_case(out["per_track"], out["audio"], echo=False)
    result = {"case": name, "about": case.about, "duration_s": out["duration_s"], "seconds": seconds, "echo_removed": removed,
              **score(case.truth, lines), "without_echo_cleanup": score(case.truth, plain)}
    result["meets"] = meets(name, result)
    return result


def run_bench(transcriber: Transcriber, cases: list[str] | None = None, language: str = "auto", sensitivity: int = 2,
              progress: Callable[[str, int, int], None] | None = None) -> dict:
    names = cases or case_names()
    unknown = [n for n in names if n not in case_names()]
    if unknown:
        raise LookupError(f"Unknown bench case: {', '.join(unknown)}. Known: {', '.join(case_names())}")
    started = time.time()
    results = []
    for number, name in enumerate(names, start=1):
        if progress:
            progress(name, number - 1, len(names))
        results.append(run_case(name, transcriber, language, sensitivity))
    return {"engine": transcriber.info(), "language": language, "started_at": started, "finished_at": time.time(),
            "cases": results, "all_meet": all((r["meets"] or {"ok": True})["ok"] for r in results)}


# --------------------------------------------------------------------- jobs --
class BenchJobs:
    """Runs a bench on the transcription worker (one model, one job at a time) and keeps the latest results in ``<data>/bench-results.json``."""

    def __init__(self, worker: TranscriptionWorker, transcriber: Callable[[], Transcriber], settings_sensitivity: Callable[[], int], data_dir: Path):
        self.worker, self._transcriber, self._sensitivity = worker, transcriber, settings_sensitivity
        self.path = Path(data_dir) / "bench-results.json"
        self._jobs: dict[str, dict] = {}
        self._done: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def start(self, cases: list[str] | None = None, language: str = "auto") -> dict:
        names = cases or case_names()
        known = case_names()
        unknown = [n for n in names if n not in known]
        if unknown:
            raise ValueError(f"Unknown bench case: {', '.join(unknown)}. Known: {', '.join(known)}")
        job_id = uuid.uuid4().hex[:12]
        job = {"job_id": job_id, "status": "queued", "cases": names, "done": 0, "current": "", "result": None, "error": "", "queued_at": time.time()}
        event = threading.Event()
        with self._lock:
            self._jobs[job_id] = job
            self._done[job_id] = event

        def work() -> None:
            job["status"] = "running"

            def progress(name: str, done: int, total: int) -> None:
                job["current"], job["done"] = name, done

            try:
                result = run_bench(self._transcriber(), names, language, self._sensitivity(), progress)
                job.update(status="done", result=result, done=len(names), current="")
                self._remember(result)
            except Exception as error:  # noqa: BLE001 - reported to the caller, never kills the worker
                log.exception("bench failed")
                job.update(status="error", error=f"{type(error).__name__}: {error}"[:500])
            finally:
                event.set()

        self.worker.submit(f"bench {job_id}", work, PRIORITY_FINAL)
        return self.snapshot(job_id)

    def snapshot(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise LookupError(f"Unknown bench job: {job_id}")
        return dict(job)

    def status(self, job_id: str, wait_s: float = 0.0) -> dict:
        event = self._done.get(job_id)
        if event is not None and wait_s > 0:
            event.wait(wait_s)
        return self.snapshot(job_id)

    def _remember(self, result: dict) -> None:
        history = self.history()
        history.append(result)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(history[-KEEP_RESULTS:], ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        except OSError:
            log.warning("could not save the bench results", exc_info=True)

    def history(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def last(self) -> dict | None:
        history = self.history()
        return history[-1] if history else None

    def running(self) -> dict | None:
        with self._lock:
            for job in self._jobs.values():
                if job["status"] in ("queued", "running"):
                    return dict(job)
        return None
