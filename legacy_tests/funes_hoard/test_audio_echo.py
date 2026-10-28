"""Echo between the microphone and the system track: the overlap rule, the word rule and the final pass that applies them."""
from __future__ import annotations

import numpy as np
import pytest

from funes_hoard.audio_memory.audio.fake import synth_speechlike
from funes_hoard.audio_memory.audio.wav import SAMPLE_RATE, write_wav
from funes_hoard.audio_memory.config import Config
from funes_hoard.audio_memory.echo import OVERLAP_MIN, drop_echo, find_echo, repeats_other_side, words_of
from funes_hoard.audio_memory.services import Services
from funes_hoard.audio_memory.transcribe.base import Segment, Transcriber

SECONDS = 16.0
SYSTEM_BURSTS = [(1.0, 4.0), (8.0, 11.0)]
OWN_BURSTS = [(5.0, 7.0), (12.0, 14.0)]


def tracks(echo_gain=0.25, own_gain=1.0, system_gain=1.0, delay_s=0.04, own=OWN_BURSTS):
    """A call through speakers: the microphone has the user's own bursts plus the system bursts back, quieter and 40 ms late."""
    system = synth_speechlike(SECONDS, pattern=SYSTEM_BURSTS, seed=2).astype(np.float32)
    mine = synth_speechlike(SECONDS, pattern=own, seed=1).astype(np.float32)
    lag = int(delay_s * SAMPLE_RATE)
    mic = own_gain * mine + echo_gain * np.concatenate([np.zeros(lag, dtype=np.float32), system[:-lag]])
    return np.clip(mic, -32768, 32767).astype(np.int16), np.clip(system * system_gain, -32768, 32767).astype(np.int16)


def test_words_ignore_case_and_punctuation():
    assert words_of("  ¡Hola, Mundo! ") == ["hola", "mundo"]


def test_a_quiet_copy_over_system_audio_is_echo_and_the_users_own_speech_is_not():
    mic, system = tracks()
    verdicts = find_echo([(1.0, 4.0, "ehh vale"), (5.0, 7.0, "esto lo digo yo"), (8.0, 11.0, "mm sí")],
                         [(1.0, 4.0, "Buenos días a todos"), (8.0, 11.0, "Seguimos con el presupuesto")], mic, system)
    assert verdicts == ["overlap", None, "overlap"]


def test_talking_over_the_other_side_at_normal_volume_keeps_the_line():
    mine = [(1.0, 4.0), (5.0, 7.0), (8.0, 11.0)]  # the user speaks while the system sounds, as loud as the rest of the time
    mic, system = tracks(own=mine)
    verdicts = find_echo([(1.0, 4.0, "te interrumpo un momento")], [(1.0, 4.0, "Buenos días a todos")], mic, system)
    assert verdicts == [None]


def test_a_hot_loopback_does_not_make_the_users_voice_look_like_echo():
    mic, system = tracks(echo_gain=0.0, system_gain=3.0)
    verdicts = find_echo([(5.0, 7.0, "hola de nuevo")], [(1.0, 4.0, "Buenos días a todos")], mic, system)
    assert verdicts == [None]


def test_the_threshold_is_sixty_percent():
    assert OVERLAP_MIN == 0.6
    mic, system = tracks()
    other = [(1.0, 4.0, "otra cosa distinta")]
    # With these synthetic tracks the echo share of a microphone line is 0.67 over 2-6 s (3 s of echo, 1.5 s of the user's own speech)
    # and 0.598 over 1-7 s: the rule is «at least 60 %», so the first is echo and the second is kept.
    assert find_echo([(2.0, 6.0, "mm")], other, mic, system) == ["overlap"]
    assert find_echo([(1.0, 7.0, "mm")], other, mic, system) == [None]


def test_without_audio_only_the_word_rule_applies():
    verdicts = find_echo([(1.0, 4.0, "ehh vale")], [(1.0, 4.0, "Buenos días a todos")])
    assert verdicts == [None]


def test_the_other_sides_words_coming_back_are_echo_only_when_they_are_close_in_time():
    other = [(0.0, 3.0, "The review is still pending after four days.")]
    mine = [(0.3, 2.5, "review is still pending after four"), (30.0, 33.0, "The review is still pending, I see."),
            (2.0, 3.0, "Sounds good."), (0.2, 1.0, "Totally different words")]
    assert find_echo(mine[:2], other) == ["text", None]
    assert find_echo([mine[3]], other) == [None]
    assert find_echo([mine[2]], other + [(1.5, 2.5, "Sounds good.")]) == ["text"]


def test_short_phrases_need_the_same_words_in_a_row():
    assert repeats_other_side("Sounds good", ["ok, sounds good to me"])
    assert not repeats_other_side("Good sounds", ["ok, sounds good to me"])
    assert not repeats_other_side("", ["anything"])


def test_drop_echo_returns_the_kept_segments_and_what_was_removed():
    mic, system = tracks()
    mine = [Segment(1.0, 4.0, "ehh vale"), Segment(5.0, 7.0, "esto lo digo yo")]
    theirs = [Segment(1.0, 4.0, "Buenos días a todos")]
    kept, stats = drop_echo(mine, theirs, mic, system)
    assert [s.text for s in kept] == ["esto lo digo yo"]
    assert stats.as_dict()["removed"] == 1 and stats.removed_overlap == 1 and stats.checked == 2 and stats.texts == ["ehh vale"]


class Scripted(Transcriber):
    """Answers each call with the next list of segments (the final pass transcribes the microphone first, then the system track)."""

    name = "scripted"

    def __init__(self, replies):
        self.replies = list(replies)

    def transcribe(self, samples, language=None):
        return self.replies.pop(0)


def seg(start, end, text):
    return Segment(start, end, text, 0.9, no_speech_prob=0.05, avg_logprob=-0.3, compression_ratio=1.2)


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("HOARD_HUB_URL", "http://127.0.0.1:1")
    service = Services(Config(data_dir=tmp_path / "audio", audio_backend="none", transcriber="fake"), link_provider=None, emit=lambda *a, **k: None)
    service.start()
    yield service
    service.stop()


def record(svc, mic, system):
    session = svc.sessions.create("Llamada con altavoces", "meeting", True, True, "es", status="processing")
    folder = svc.sessions.session_dir(session["id"])
    write_wav(folder / "mic.wav", mic)
    write_wav(folder / "system.wav", system)
    return session["id"]


def test_the_final_pass_drops_the_echo_and_says_so(svc):
    mic, system = tracks()
    sid = record(svc, mic, system)
    svc.pipeline.transcriber = Scripted([
        [seg(1.0, 4.0, "ehh vale"), seg(5.0, 7.0, "esto lo digo yo")],  # microphone
        [seg(1.0, 4.0, "Buenos días a todos"), seg(8.0, 11.0, "Seguimos con el presupuesto")],  # system
    ])
    svc.pipeline.run_final(sid)
    lines = [(s["speaker"], s["text"]) for s in svc.sessions.segments(sid)]
    assert ("yo", "esto lo digo yo") in lines and ("yo", "ehh vale") not in lines
    assert [t for who, t in lines if who == "otros"] == ["Buenos días a todos", "Seguimos con el presupuesto"]
    echo = svc.sessions.get(sid)["stats"]["final"]["echo"]
    assert echo["removed"] == 1 and echo["removed_overlap"] == 1 and echo["checked"] == 2


def test_the_setting_turns_the_echo_pass_off(svc):
    svc.settings.update({"echo_cleanup": False})
    mic, system = tracks()
    sid = record(svc, mic, system)
    svc.pipeline.transcriber = Scripted([[seg(1.0, 4.0, "ehh vale")], [seg(1.0, 4.0, "Buenos días a todos")]])
    svc.pipeline.run_final(sid)
    assert ("yo", "ehh vale") in [(s["speaker"], s["text"]) for s in svc.sessions.segments(sid)]
    assert svc.sessions.get(sid)["stats"]["final"]["echo"]["removed"] == 0


def test_a_single_track_session_has_nothing_to_compare(svc):
    session = svc.sessions.create("Nota", "note", True, False, "es", status="processing")
    write_wav(svc.sessions.session_dir(session["id"]) / "mic.wav", synth_speechlike(6.0, pattern=[(1.0, 4.0)], seed=1))
    svc.pipeline.transcriber = Scripted([[seg(1.0, 4.0, "una nota de voz")]])
    svc.pipeline.run_final(session["id"])
    assert [s["text"] for s in svc.sessions.segments(session["id"])] == ["una nota de voz"]
    assert svc.sessions.get(session["id"])["stats"]["final"]["echo"]["checked"] == 0
