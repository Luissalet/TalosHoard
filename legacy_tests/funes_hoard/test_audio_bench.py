"""The transcription bench: the script format, the scoring, the echo effect and the jobs/tools around it."""
from __future__ import annotations

import time

import pytest

from funes_hoard.audio_memory import bench
from funes_hoard.audio_memory.agent_tools import call_tool
from funes_hoard.audio_memory.config import Config
from funes_hoard.audio_memory.importer import ffmpeg_path, pyav_available
from funes_hoard.audio_memory.merge import Labelled
from funes_hoard.audio_memory.services import Services
from funes_hoard.audio_memory.transcribe.base import Segment, Transcriber, Word

needs_decoder = pytest.mark.skipif(not (ffmpeg_path() or pyav_available()), reason="no ffmpeg or PyAV to decode the .ogg recordings")


def test_the_cases_and_their_scripts():
    assert bench.case_names() == ["call", "call-speakers", "music", "silence"]
    counts = {name: len(bench.load_case(name).truth) for name in bench.case_names()}
    assert counts == {"call": 26, "call-speakers": 26, "music": 8, "silence": 0}
    case = bench.load_case("call-speakers")
    assert set(case.tracks) == {"mic", "computer"} and all(p.is_file() for p in case.tracks.values())
    assert {t.side for t in case.truth} == {"mic", "computer"}
    with pytest.raises(LookupError):
        bench.load_case("nope")


def perfect(truth):
    return [Labelled(t.start, t.end, "yo" if t.side == "mic" else "otros", t.text) for t in truth]


def test_a_perfect_transcript_scores_one():
    truth = bench.load_case("call").truth
    result = bench.score(truth, perfect(truth))
    assert result["found"] == 1.0 and result["side"] == 1.0 and result["leaked"] == 0 and result["invented"] == 0 and result["extra"] == 0.0
    assert result["lines"] == len(truth)


def test_words_on_the_wrong_side_lower_the_side_score_only():
    truth = bench.load_case("call").truth
    swapped = [Labelled(t.start, t.end, "otros" if t.side == "mic" else "yo", t.text) for t in truth]
    result = bench.score(truth, swapped)
    # Windows of neighbouring lines overlap, so a common word can still match a neighbour's line on the «right» side by chance: a few percent.
    assert result["found"] >= 0.98 and result["side"] <= 0.1


def test_the_other_side_repeated_on_the_microphone_is_leaked_and_not_invented():
    truth = bench.load_case("call").truth
    computer = next(t for t in truth if t.side == "computer" and len(t.text.split()) > 8)
    lines = perfect(truth) + [Labelled(computer.start + 0.04, computer.end + 0.04, "yo", computer.text)]
    result = bench.score(truth, lines)
    assert result["leaked"] == 1 and result["invented"] == 0 and result["found"] == 1.0


def test_hallucinated_lines_and_missing_speech_are_counted():
    truth = bench.load_case("music").truth
    made_up = perfect(truth) + [Labelled(3.0, 5.0, "otros", "gracias por ver el vídeo suscríbete al canal")]
    assert bench.score(truth, made_up)["invented"] == 1
    nothing = bench.score(truth, [])
    assert nothing["found"] == 0.0 and nothing["side"] is None and nothing["lines"] == 0
    assert bench.score([], [])["found"] is None


def test_words_with_timestamps_are_placed_by_their_own_time():
    truth = [bench.TruthLine("A", "computer", 10.0, 12.0, "hola mundo")]
    right = Labelled(0.0, 30.0, "otros", "hola mundo", words=[{"start": 10.1, "end": 10.5, "word": " Hola,"}, {"start": 11.0, "end": 11.5, "word": "mundo."}])
    wrong_time = Labelled(0.0, 30.0, "otros", "hola mundo", words=[{"start": 25.0, "end": 25.5, "word": "hola"}, {"start": 26.0, "end": 26.5, "word": "mundo"}])
    assert bench.score(truth, [right])["found"] == 1.0
    assert bench.score(truth, [wrong_time])["found"] == 0.0


def test_thresholds_are_informative():
    assert bench.meets("nope", {}) is None
    spec = {"call": {"min": {"found": 0.9}, "max": {"leaked": 0}}}
    assert bench.meets("call", {"found": 0.95, "leaked": 0}, spec) == {"ok": True, "failures": []}
    verdict = bench.meets("call", {"found": 0.5, "leaked": 2}, spec)
    assert verdict["ok"] is False and len(verdict["failures"]) == 2


class FromScript(Transcriber):
    """Answers the microphone call, then the system call, with a script's lines (the bench transcribes `mic` first)."""

    name = "from-script"

    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def transcribe(self, samples, language=None):
        self.calls += 1
        return self.replies.pop(0)

    def info(self):
        return {"name": self.name}


def seg(t):
    return Segment(t.start, t.end, t.text, 0.9, [Word(t.start, t.end, w) for w in t.text.split()][:0], no_speech_prob=0.05, avg_logprob=-0.3, compression_ratio=1.2)


@needs_decoder
def test_the_echo_cleanup_is_measured_from_the_same_model_output():
    case = bench.load_case("call-speakers")
    mine = [seg(t) for t in case.truth if t.side == "mic"]
    theirs = [seg(t) for t in case.truth if t.side == "computer"]
    echo = [Segment(t.start + 0.04, t.end + 0.04, t.text, 0.9, no_speech_prob=0.05, avg_logprob=-0.3, compression_ratio=1.2) for t in case.truth if t.side == "computer"]
    engine = FromScript([sorted(mine + echo, key=lambda s: s.start), theirs])
    result = bench.run_case("call-speakers", engine)
    assert result["leaked"] == 0 and result["echo_removed"] >= len(echo) - 1
    assert result["without_echo_cleanup"]["leaked"] > 0
    assert result["found"] >= 0.9 and result["meets"] is None or isinstance(result["meets"], dict)


@needs_decoder
def test_silence_never_reaches_the_engine():
    engine = FromScript([])
    result = bench.run_case("silence", engine)
    assert engine.calls == 0 and result["lines"] == 0 and result["found"] is None


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("HOARD_HUB_URL", "http://127.0.0.1:1")
    service = Services(Config(data_dir=tmp_path / "audio", audio_backend="none", transcriber="fake"), link_provider=None, emit=lambda *a, **k: None)
    service.start()
    yield service
    service.stop()


@needs_decoder
def test_the_tools_start_a_job_wait_for_it_and_keep_the_last_result(svc):
    started = call_tool(svc, "scribe_bench", {"cases": ["silence"]})
    assert started["status"] in ("queued", "running", "done") and started["cases"] == ["silence"]
    done = call_tool(svc, "scribe_bench_status", {"job_id": started["job_id"], "wait_s": 30})
    assert done["status"] == "done" and done["result"]["cases"][0]["case"] == "silence" and done["result"]["engine"]["name"] == "fake"
    last = call_tool(svc, "scribe_bench_status", {})
    assert last["running"] is None and last["last"]["cases"][0]["case"] == "silence"
    assert (svc.config.data_dir / "bench-results.json").is_file()
    with pytest.raises(ValueError, match="Unknown bench case"):
        call_tool(svc, "scribe_bench", {"cases": ["nope"]})


def test_the_echo_check_tool_lists_then_removes(svc):
    from funes_hoard.audio_memory.audio.fake import synth_speechlike
    from funes_hoard.audio_memory.audio.wav import write_wav

    session = svc.sessions.create("Llamada", "meeting", True, True, "es")
    sid = session["id"]
    svc.sessions.update(sid, status="done")
    folder = svc.sessions.session_dir(sid)
    write_wav(folder / "mic.wav", synth_speechlike(10.0, pattern=[(5.0, 7.0)], seed=1))
    write_wav(folder / "system.wav", synth_speechlike(10.0, pattern=[(1.0, 4.0)], seed=2))
    svc.sessions.add_segments(sid, [Labelled(1.0, 4.0, "otros", "Buenos días a todos"), Labelled(1.1, 3.9, "yo", "buenos días a todos"),
                                    Labelled(5.0, 7.0, "yo", "esto lo digo yo")], live=False)
    listed = call_tool(svc, "scribe_echo_check", {"session_id": sid})
    assert [e["text"] for e in listed["echo"]] == ["buenos días a todos"] and listed["echo"][0]["reason"] == "text"
    assert listed["removed"] == 0 and listed["applied"] is False and len(svc.sessions.segments(sid)) == 3
    applied = call_tool(svc, "scribe_echo_check", {"session_id": sid, "apply": True})
    assert applied["removed"] == 1 and [s["text"] for s in svc.sessions.segments(sid)] == ["Buenos días a todos", "esto lo digo yo"]
    assert svc.sessions.search("buenos")["total"] == 1, "the search index lost the removed line too"
    assert call_tool(svc, "scribe_echo_check", {"session_id": sid})["echo"] == []
    one_sided = svc.sessions.create("Nota", "note", True, False, "es")["id"]
    svc.sessions.add_segments(one_sided, [Labelled(0, 2, "S1", "una nota")], live=False)
    assert "needs both sides" in call_tool(svc, "scribe_echo_check", {"session_id": one_sided})["note"]
