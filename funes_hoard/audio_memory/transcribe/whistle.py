"""Whistle: the small CPU speech-to-text engine Funes keeps as a fallback.

Whistle is a ~17 MB model that decodes a short clip in a few hundred milliseconds on the CPU and covers English,
German, French, Spanish, Italian, Dutch and Polish. Funes uses it when faster-whisper cannot be loaded here, when a
caller asks for it by name, and (if the person turns it on in the settings) for clips shorter than a chosen length,
where the big model's load time dominates.

Two shapes, like the rest of the package:

* :class:`WhistleEngine` — the file-in / transcript-out engine the family's speech-to-text jobs use
  (``transcribe_file``): the same ``hoard_link.media.stt.Transcript`` faster-whisper produces, with a ``note`` that
  says which engine wrote it.
* :class:`WhistleTranscriber` — the session transcriber (``Transcriber``): timed ``Segment`` objects for the live
  chunks and the final pass, so a session can be recorded with this engine too.

The model is downloaded once by the package itself (``Cactus-Compute/whistle``) and cached; ``FUNES_WHISTLE_WEIGHTS``
(or ``CACTUS_WHISTLE_WEIGHTS``) points at a file already on disk. The package's anonymous usage counter is off unless
the person sets ``CACTUS_TELEMETRY`` themselves.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from funes_hoard.hoard_link.errors import Unavailable
from funes_hoard.hoard_link.media import stt
from funes_hoard.hoard_link.proc import Cancelled

from ..audio.wav import SAMPLE_RATE, read_wav, to_float32
from .base import Segment, Transcriber, Word

log = logging.getLogger("scribe.whistle")

#: Languages the model was trained on (the package reports the same list from the weights file).
LANGUAGES = ("en", "de", "fr", "es", "it", "nl", "pl")
#: Words per segment when the engine has to invent segment boundaries (Whistle returns words, not segments).
WORDS_PER_SEGMENT = 12
SEGMENT_MAX_S = 6.0
SENTENCE_END = (".", "?", "!", "…", "。", "؟")

os.environ.setdefault("CACTUS_TELEMETRY", "0")


def _env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def weights_path() -> Optional[Path]:
    """The weights file: ``FUNES_WHISTLE_WEIGHTS`` / ``CACTUS_WHISTLE_WEIGHTS``, else the package's own cache (None until it is
    downloaded)."""
    explicit = _env("FUNES_WHISTLE_WEIGHTS", "CACTUS_WHISTLE_WEIGHTS")
    if explicit:
        return Path(explicit).expanduser()
    try:
        from cactus.agent import fetch

        return Path(fetch.cache_dir(fetch.WHISTLE)) / fetch.base_weights(fetch.WHISTLE)
    except Exception:  # noqa: BLE001 - the package is optional and its layout is not ours
        return None


def available() -> bool:
    """True when the package is installed (the weights may still have to be downloaded)."""
    try:
        import cactus  # noqa: F401

        return True
    except Exception:
        return False


def model_present() -> bool:
    path = weights_path()
    return bool(path and path.is_file())


def languages() -> tuple[str, ...]:
    """The languages the installed weights carry, or the package's list when nothing is downloaded yet."""
    path = weights_path()
    if path and path.is_file():
        try:
            from cactus.agent.whistle import languages as _languages

            return tuple(_languages(str(path))) or LANGUAGES
        except Exception:  # noqa: BLE001 - a weights file we cannot read is not a reason to fail
            pass
    return LANGUAGES


def _ensure_weights() -> Path:
    """The weights file, downloading it once when it is missing.

    ``HF_HUB_OFFLINE=1`` (set by some environments) makes the download fail even when the model was never fetched; in that
    case it is retried once with the flag cleared, because offline mode cannot serve a file that is not on disk.
    """
    path = weights_path()
    if path and path.is_file():
        return path
    if not available():
        raise Unavailable("Whistle speech to text", ["the optional package 'cactus-compute' is not installed (pip install cactus-compute)"])
    from cactus.agent import fetch

    try:
        return Path(fetch.fetch_weights(fetch.WHISTLE))
    except Exception as error:  # noqa: BLE001 - retried below without the offline flag
        if os.environ.get("HF_HUB_OFFLINE") not in ("1", "true", "True"):
            raise
        log.info("whistle: the model is not on disk and HF_HUB_OFFLINE is set; fetching it once (%s)", error)
        previous = os.environ.pop("HF_HUB_OFFLINE")
        try:
            return Path(fetch.fetch_weights(fetch.WHISTLE))
        finally:
            os.environ["HF_HUB_OFFLINE"] = previous


def load_samples(path: "str | Path") -> np.ndarray:
    """16 kHz mono float32 samples of a file: a WAV is read directly, anything else is converted first (ffmpeg or PyAV)."""
    source = Path(path)
    if source.suffix.lower() == ".wav":
        samples, _ = read_wav(source)
        return to_float32(samples)
    import tempfile

    from ..importer import convert_to_wav

    with tempfile.TemporaryDirectory(prefix="funes-whistle-") as folder:
        target = Path(folder) / "audio.wav"
        convert_to_wav(source, target)
        samples, _ = read_wav(target)
        return to_float32(samples)


def _segments(words: list[dict[str, Any]], duration_s: float) -> list[dict[str, Any]]:
    """Whistle returns words with times; group them into short segments that end on a sentence or after a few seconds."""
    if not words:
        return []
    segments: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for word in words:
        current.append(word)
        text = str(word.get("word") or "")
        long_enough = len(current) >= WORDS_PER_SEGMENT
        timed_out = float(word.get("end") or 0.0) - float(current[0].get("start") or 0.0) >= SEGMENT_MAX_S
        if text.endswith(SENTENCE_END) or long_enough or timed_out:
            segments.append(_segment(current))
            current = []
    if current:
        segments.append(_segment(current))
    return segments


def _segment(words: list[dict[str, Any]]) -> dict[str, Any]:
    start = float(words[0].get("start") or 0.0)
    end = float(words[-1].get("end") or start)
    probabilities = [float(w.get("probability") or 0.0) for w in words]
    return {
        "start_s": round(start, 2),
        "end_s": round(max(end, start), 2),
        "text": " ".join(str(w.get("word") or "").strip() for w in words).strip(),
        "words": [{"start_s": round(float(w.get("start") or 0.0), 2), "end_s": round(float(w.get("end") or 0.0), 2),
                   "word": str(w.get("word") or ""), "p": round(float(w.get("probability") or 0.0), 3)} for w in words],
        "confidence": round(sum(probabilities) / len(probabilities), 3) if probabilities else 0.0,
    }


class WhistleEngine:
    """The file-in / transcript-out engine. ``model_factory`` is injectable so tests never load the real model."""

    name = "whistle"

    def __init__(self, weights: "str | Path | None" = None, model_factory: Optional[Callable[..., Any]] = None):
        self._weights = Path(weights).expanduser() if weights else None
        self._factory = model_factory
        self._model: Any = None
        self._lock = threading.Lock()
        self.state = "idle"  # idle | loading | ready | error
        self.error = ""
        self.last_ms = 0

    # ---------- state ----------
    def ensure_loaded(self) -> Any:
        with self._lock:
            if self._model is not None:
                return self._model
            self.state = "loading"
            try:
                if self._factory is not None:
                    self._model = self._factory()
                else:
                    import cactus

                    self._model = cactus.Whistle(str(self._weights or _ensure_weights()))
                self.state, self.error = "ready", ""
            except Exception as error:  # noqa: BLE001 - reported through info(), never raised on import
                self.state, self.error = "error", str(error)[:500]
                raise
            return self._model

    def close(self) -> None:
        with self._lock:
            self._model = None
            self.state = "idle"

    def info(self) -> dict:
        path = self._weights or weights_path()
        return {
            "name": self.name,
            "model": "whistle",
            "device": "cpu",
            "compute_type": "int8",
            "state": self.state,
            "loaded": self._model is not None,
            "download": "ready" if (path and path.is_file()) else "missing",
            "models_dir": str(path.parent) if path else "",
            "weights": str(path) if path else "",
            "languages": list(languages()),
            "last_ms": self.last_ms,
            "error": self.error,
            "gpu_lease": "disabled",
        }

    # ---------- work ----------
    def transcribe(self, path: "str | Path", *, language: Optional[str] = None, word_timestamps: bool = True, vad: bool = True,
                   initial_prompt: str = "", progress: Optional[Callable[[float], None]] = None,
                   cancel: Optional[threading.Event] = None) -> stt.Transcript:
        """Transcribe a file. ``language`` is one of :data:`LANGUAGES` or None to detect it; ``initial_prompt`` biases the decoder
        with names and jargon (Whistle's keyword list)."""
        started = time.time()
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        samples = load_samples(path)
        duration = round(len(samples) / SAMPLE_RATE, 2)
        if progress is not None:
            progress(0.2)
        note = ""
        if vad:
            from .filter import speech_stats

            if not speech_stats(samples).has_speech:
                if progress is not None:
                    progress(1.0)
                return stt.Transcript(language=language or "", duration_s=duration, text="", segments=[], model=self.name,
                                      device="cpu", note="No speech was detected in the file.", stats={"engine": self.name})
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        model = self.ensure_loaded()
        wanted = (language or "").strip().lower()
        if wanted and wanted not in languages():
            note = f"Whistle does not cover {wanted}; the language was detected instead."
            wanted = ""
        result = model.transcribe(samples, language=wanted or None, keywords=initial_prompt or None, word_timestamps=word_timestamps)
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        words = list(result.get("words") or []) if word_timestamps else []
        segments = _segments(words, duration) if words else []
        text = str(result.get("text") or "").strip()
        if not segments and text:
            segments = [{"start_s": 0.0, "end_s": duration, "text": text, "words": [], "confidence": 0.0}]
        self.last_ms = int((time.time() - started) * 1000)
        if progress is not None:
            progress(1.0)
        return stt.Transcript(
            language=str(result.get("language") or wanted or ""), duration_s=duration, text=text, segments=segments,
            model=self.name, device="cpu", note=note,
            stats={"engine": self.name, "ttft_ms": result.get("ttft_ms"), "decode_tps": result.get("decode_tps"),
                   "elapsed_ms": self.last_ms},
        )


class WhistleTranscriber(Transcriber):
    """The session transcriber: the same engine, returning Funes's ``Segment`` objects for the live chunks and the final pass."""

    name = "whistle"

    def __init__(self, engine: Optional[WhistleEngine] = None):
        self.engine = engine or WhistleEngine()

    def ensure_loaded(self) -> None:
        self.engine.ensure_loaded()

    def transcribe(self, samples: np.ndarray, language: Optional[str] = None) -> list[Segment]:
        model = self.engine.ensure_loaded()
        wanted = (language or "").strip().lower()
        if wanted and wanted not in languages():
            wanted = ""
        result = model.transcribe(to_float32(samples), language=wanted or None, word_timestamps=True)
        words = list(result.get("words") or [])
        duration = round(len(samples) / SAMPLE_RATE, 2)
        segments = _segments(words, duration) if words else []
        if not segments and str(result.get("text") or "").strip():
            segments = [{"start_s": 0.0, "end_s": duration, "text": str(result["text"]).strip(), "words": [], "confidence": 0.0}]
        return [
            Segment(float(item["start_s"]), float(item["end_s"]), str(item["text"]), float(item.get("confidence") or 0.0),
                    [Word(float(w["start_s"]), float(w["end_s"]), str(w["word"]), float(w.get("p") or 0.0)) for w in item.get("words") or []])
            for item in segments
        ]

    def info(self) -> dict:
        return self.engine.info()