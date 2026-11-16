"""Transcriber selection. Never crashes on import: faster-whisper and Whistle are imported lazily."""

from __future__ import annotations

from pathlib import Path

from .base import Segment, Transcriber, Word
from .fake import FakeTranscriber

__all__ = ["FakeTranscriber", "Segment", "Transcriber", "Word", "select_transcriber", "whisper_available", "whistle_available",
           "ENGINES"]


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except Exception:
        return False


def whistle_available() -> bool:
    """True when the small CPU engine's package is installed (its model may still have to be downloaded)."""
    from .whistle import available

    return available()


#: What ``engine`` in the settings accepts: ``auto`` = faster-whisper, Whistle when it cannot load.
ENGINES = ("auto", "whisper", "whistle")


def select_transcriber(kind: str, models_dir: Path, size: str, device: str, compute_type: str,
                       engine: str = "auto") -> tuple[Transcriber, list[str]]:
    """The session transcriber. ``kind`` is the process-level override (``fake`` in tests); ``engine`` is the person's choice:
    ``whisper`` only faster-whisper, ``whistle`` only the small CPU engine, ``auto`` faster-whisper and Whistle when it cannot load."""
    notes: list[str] = []
    if kind == "fake":
        return FakeTranscriber(), notes
    if engine == "whistle":
        if whistle_available():
            from .whistle import WhistleTranscriber

            return WhistleTranscriber(), notes
        notes.append("Whistle is not installed; using faster-whisper (pip install cactus-compute)")
    if whisper_available():
        from .whisper import WhisperTranscriber

        return WhisperTranscriber(models_dir, size, device, compute_type), notes
    if engine != "whisper" and whistle_available():
        from .whistle import WhistleTranscriber

        notes.append("faster-whisper is not installed; transcribing with Whistle")
        return WhistleTranscriber(), notes
    notes.append("faster-whisper is not installed; using the fake transcriber (pip install faster-whisper)")
    return FakeTranscriber(), notes