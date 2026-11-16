"""The small CPU engine (Whistle) as Funes's fallback: engine choice, per-job routing, settings and the tool surface."""

from __future__ import annotations

import numpy as np
import pytest

from funes_hoard.audio_memory.audio.wav import SAMPLE_RATE, write_wav
from funes_hoard.audio_memory.settings import Settings, SettingsPatch
from funes_hoard.audio_memory.stt_jobs import NoModel, SttJobs
from funes_hoard.audio_memory.transcribe import select_transcriber
from funes_hoard.audio_memory.transcribe.whistle import WhistleEngine, WhistleTranscriber
from funes_hoard.audio_memory.worker import TranscriptionWorker


class FakeWhistle:
    """What ``cactus.Whistle`` returns: text, language and words with times."""

    def __init__(self, text="Necesitamos revisar el presupuesto.", language="es", words=None):
        self.text, self.language = text, language
        self.words = words if words is not None else [
            {"word": "Necesitamos", "start": 0.16, "end": 0.7, "probability": 0.9},
            {"word": "revisar", "start": 0.88, "end": 1.2, "probability": 0.8},
            {"word": "el", "start": 1.28, "end": 1.3, "probability": 0.95},
            {"word": "presupuesto.", "start": 1.36, "end": 2.0, "probability": 0.85},
        ]
        self.calls = []

    def transcribe(self, audio, language=None, keywords=None, word_timestamps=False):
        self.calls.append({"language": language, "keywords": keywords, "word_timestamps": word_timestamps, "samples": len(audio)})
        return {"text": self.text, "language": self.language, "ttft_ms": 70.0, "decode_tps": 180.0,
                "words": self.words if word_timestamps else []}


def speech_wav(folder, name="corto.wav", seconds=2.0):
    """A WAV the silence gate accepts: a loud tone, not digital silence."""
    path = folder / name
    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    tone = (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16)
    write_wav(path, tone)
    return path


def test_the_engine_returns_the_family_transcript_shape(tmp_path):
    model = FakeWhistle()
    engine = WhistleEngine(model_factory=lambda: model)
    result = engine.transcribe(speech_wav(tmp_path), language="es", word_timestamps=True, vad=False)
    assert result.text == "Necesitamos revisar el presupuesto."
    assert result.language == "es" and result.model == "whistle" and result.device == "cpu"
    assert result.segments and result.segments[0]["start_s"] == 0.16
    assert result.segments[0]["words"][0]["word"] == "Necesitamos"
    assert result.stats["engine"] == "whistle"
    assert model.calls[0]["language"] == "es" and model.calls[0]["word_timestamps"] is True


def test_a_language_the_model_does_not_cover_is_detected_and_said_so(tmp_path):
    model = FakeWhistle(language="es")
    engine = WhistleEngine(model_factory=lambda: model)
    result = engine.transcribe(speech_wav(tmp_path), language="ja", vad=False)
    assert model.calls[0]["language"] is None
    assert "does not cover ja" in result.note


def test_silence_is_never_sent_to_the_model(tmp_path):
    model = FakeWhistle()
    engine = WhistleEngine(model_factory=lambda: model)
    path = tmp_path / "silencio.wav"
    write_wav(path, np.zeros(SAMPLE_RATE * 2, dtype=np.int16))
    result = engine.transcribe(path)
    assert result.text == "" and result.segments == []
    assert model.calls == []


def test_the_session_transcriber_returns_timed_segments(tmp_path):
    model = FakeWhistle()
    transcriber = WhistleTranscriber(WhistleEngine(model_factory=lambda: model))
    samples = np.zeros(SAMPLE_RATE * 2, dtype=np.int16)
    segments = transcriber.transcribe(samples, "es")
    assert len(segments) == 1
    assert segments[0].text == "Necesitamos revisar el presupuesto."
    assert segments[0].words[0].word == "Necesitamos"
    assert transcriber.info()["name"] == "whistle"


def test_the_engine_setting_picks_the_session_transcriber(monkeypatch):
    monkeypatch.setattr("funes_hoard.audio_memory.transcribe.whistle_available", lambda: True)
    transcriber, notes = select_transcriber("auto", None, "small", "auto", "auto", "whistle")
    assert isinstance(transcriber, WhistleTranscriber) and notes == []


def test_asking_for_whistle_without_the_package_falls_back_with_a_note(monkeypatch):
    monkeypatch.setattr("funes_hoard.audio_memory.transcribe.whistle_available", lambda: False)
    monkeypatch.setattr("funes_hoard.audio_memory.transcribe.whisper_available", lambda: True)
    transcriber, notes = select_transcriber("auto", None, "small", "auto", "auto", "whistle")
    assert transcriber.name == "faster-whisper"
    assert any("Whistle is not installed" in note for note in notes)


def test_the_settings_carry_the_engine_and_the_short_clip_limit():
    settings = Settings()
    assert settings.engine == "auto" and settings.whistle_short_s == 0
    patched = Settings.model_validate(settings.model_copy(update=SettingsPatch(engine="whistle", whistle_short_s=30).model_dump(exclude_none=True)).model_dump())
    assert patched.engine == "whistle" and patched.whistle_short_s == 30
    with pytest.raises(ValueError):
        SettingsPatch(engine="other")


class FakeWhisperEngine:
    """A stand-in for the shared faster-whisper engine: records that it was asked."""

    def __init__(self):
        self.calls = 0

    def transcribe(self, path, **kwargs):
        from funes_hoard.hoard_link.media import stt

        self.calls += 1
        return stt.Transcript(language="es", duration_s=2.0, text="whisper", segments=[], model="faster-whisper", device="cpu")


def jobs(tmp_path, *, whisper_ready=True, whistle_ready=True, short_s=0):
    worker = TranscriptionWorker()
    worker.start()
    whisper = FakeWhisperEngine()
    whistle = WhistleEngine(model_factory=lambda: FakeWhistle())
    service = SttJobs(worker, lambda: whisper, lambda size: whisper, lambda: whisper_ready,
                      whistle=lambda: whistle, whistle_available=lambda: whistle_ready, short_s=lambda: short_s)
    return service, worker, whisper, whistle


def test_a_job_can_name_the_small_engine(tmp_path):
    service, worker, whisper, _ = jobs(tmp_path)
    try:
        job = service.submit(str(speech_wav(tmp_path)), wait_s=10, engine="whistle", vad=False)
        assert job["status"] == "done" and job["engine"] == "whistle"
        assert job["text"].startswith("Necesitamos") and job["model"] == "whistle"
        assert whisper.calls == 0
    finally:
        worker.stop()


def test_auto_sends_short_clips_to_whistle_when_the_limit_is_set(tmp_path):
    service, worker, whisper, _ = jobs(tmp_path, short_s=30)
    try:
        job = service.submit(str(speech_wav(tmp_path, seconds=2.0)), wait_s=10, vad=False)
        assert job["status"] == "done" and job["engine"] == "whistle"
        assert whisper.calls == 0
    finally:
        worker.stop()


def test_auto_keeps_long_audio_on_faster_whisper(tmp_path):
    service, worker, whisper, _ = jobs(tmp_path, short_s=1)
    try:
        job = service.submit(str(speech_wav(tmp_path, seconds=3.0)), wait_s=10)
        assert job["status"] == "done" and job["engine"] == "whisper"
        assert whisper.calls == 1
    finally:
        worker.stop()


def test_auto_falls_back_to_whistle_when_faster_whisper_cannot_load(tmp_path):
    service, worker, whisper, _ = jobs(tmp_path, whisper_ready=False)
    try:
        job = service.submit(str(speech_wav(tmp_path)), wait_s=10, vad=False)
        assert job["status"] == "done" and job["engine"] == "whistle"
        assert whisper.calls == 0
    finally:
        worker.stop()


def test_asking_for_an_engine_that_is_not_there_is_reported_before_queueing(tmp_path):
    service, worker, _, _ = jobs(tmp_path, whistle_ready=False)
    try:
        with pytest.raises(NoModel) as error:
            service.submit(str(speech_wav(tmp_path)), engine="whistle")
        assert "cactus-compute" in str(error.value)
        with pytest.raises(ValueError):
            service.submit(str(speech_wav(tmp_path)), engine="otro")
    finally:
        worker.stop()


def test_the_engines_listing_says_what_can_transcribe_and_what_auto_does(tmp_path):
    service, worker, _, _ = jobs(tmp_path, short_s=45)
    try:
        listing = service.engines()
        names = {engine["name"]: engine for engine in listing["engines"]}
        assert names["whisper"]["available"] is True and names["whistle"]["available"] is True
        assert "es" in names["whistle"]["languages"]
        assert listing["auto"] == {"short_s": 45, "whistle_first": True, "fallback": "whisper"}
    finally:
        worker.stop()


def test_the_tool_catalogue_publishes_the_engine_choice():
    from funes_hoard.audio_memory import agent_tools

    tools = {tool.name: tool for tool in agent_tools.TOOLS}
    assert "transcribe_engines" in tools
    fields = tools["transcribe_file"].input_model.model_fields
    assert fields["engine"].default == "auto"
    assert "whistle" in str(fields["engine"].annotation)