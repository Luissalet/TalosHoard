"""Chapters of a meeting: the model's answer is made safe by code, stored, shown in the exports and written after a transcription."""
from __future__ import annotations

import json
import time
from datetime import datetime

import pytest

from funes_hoard.audio_memory.audio.fake import synth_speechlike
from funes_hoard.audio_memory.audio.wav import write_wav
from funes_hoard.audio_memory.chapters import (
    MAX_CHAPTERS,
    ChaptersService,
    clean_title,
    parse_clock,
    parse_items,
    prompt_lines,
    render_chapters_md,
    sanitize,
)
from funes_hoard.audio_memory.config import Config
from funes_hoard.audio_memory.db import Database
from funes_hoard.audio_memory.export import render
from funes_hoard.audio_memory.merge import Labelled
from funes_hoard.audio_memory.services import Services
from funes_hoard.audio_memory.settings import SettingsStore
from funes_hoard.audio_memory.store import SessionStore
from funes_hoard.hoard_link import BackendError, Resolution, Unavailable
from legacy_tests.funes_hoard.fakes import ScriptedLink

MEETING_AT = datetime(2026, 10, 2, 10, 0).timestamp()


# ------------------------------------------------------------ the clean-up --
@pytest.mark.parametrize("value, expected", [("03:08", 188.0), ("1:02:03", 3723.0), ("[05:00]", 300.0), (125, 125.0), (12.5, 12.5), ("90", 90.0),
                                              ("xx", None), ("", None), (None, None), (True, None), ("-3", None), ("1:2:3:4", None)])
def test_clock_values(value, expected):
    assert parse_clock(value) == expected


def test_parse_items_finds_the_json_wherever_it_sits():
    fenced = 'Claro!\n```json\n[{"start": "00:00", "title": "A"}, 7, {"start": "05:00", "title": "B"}]\n```'
    assert [i["title"] for i in parse_items(fenced)] == ["A", "B"]
    assert parse_items('Aquí: [{"start": 0, "title": "X"}] listo')[0]["title"] == "X"
    assert parse_items('{"chapters": [{"start": "0:00", "title": "Y"}]}')[0]["title"] == "Y"
    assert parse_items("no puedo ayudar") == [] and parse_items("[not json]") == []


def test_titles_lose_markup_numbering_and_extra_words():
    assert clean_title(' **"Pricing and plans"** ') == "Pricing and plans"
    assert clean_title("1. Apertura y orden del día") == "Apertura y orden del día"
    assert clean_title("uno dos tres cuatro cinco seis siete ocho") == "uno dos tres cuatro cinco seis"
    assert clean_title("   ") == "" and clean_title(None) == ""


def test_every_start_lands_on_a_real_line_sorted_without_duplicates_and_the_first_at_the_beginning():
    starts = [2, 65, 190, 400]
    answer = parse_items('```json\n[{"start": "03:08", "title": " **Pricing** "}, {"start": "00:00", "title": "Opening"}, '
                         '{"start": "03:10", "title": "Duplicate"}, {"start": "xx", "title": "Broken"}, {"start": "06:30", "title": ""}]\n```')
    assert sanitize(answer, starts) == [{"start_s": 2.0, "title": "Opening"}, {"start_s": 190.0, "title": "Pricing"}]


def test_the_opening_chapter_is_moved_to_the_first_line():
    chapters = sanitize([{"start": "02:00", "title": "Late start"}, {"start": "06:00", "title": "Second"}], [5, 125, 365])
    assert chapters[0] == {"start_s": 5.0, "title": "Late start"} and chapters[1]["start_s"] == 365.0


def test_chapters_closer_than_a_minute_are_dropped_and_fewer_than_two_means_none():
    starts = [0, 30, 50, 400]
    assert sanitize([{"start": 0, "title": "A"}, {"start": 30, "title": "B"}, {"start": 50, "title": "C"}, {"start": 400, "title": "D"}], starts) == [
        {"start_s": 0.0, "title": "A"}, {"start_s": 400.0, "title": "D"}]
    assert sanitize([{"start": 0, "title": "Only"}], starts) == []
    assert sanitize([{"start": 0, "title": "A"}, {"start": 20, "title": "B"}], [0, 20]) == []
    assert sanitize([{"start": 0, "title": "A"}], []) == []


def test_at_most_twelve_remain_and_the_closest_pairs_go_first():
    starts = [i * 100.0 for i in range(30)]
    items = [{"start": start, "title": f"Tema {i}"} for i, start in enumerate(starts)]
    kept = sanitize(items, starts)
    assert len(kept) == MAX_CHAPTERS and kept[0]["start_s"] == 0.0
    assert [c["start_s"] for c in kept] == sorted(c["start_s"] for c in kept)


def test_long_transcripts_are_shortened_to_fit_the_prompt():
    segments = [{"start_s": float(i * 10), "speaker": "otros", "text": "palabra " * 120} for i in range(2000)]
    text = prompt_lines(segments)
    assert len(text) <= 60000 and text.startswith("[00:00] otros:")


def test_markdown_lists_the_chapters():
    out = render_chapters_md([{"start_s": 0, "title": "Apertura"}, {"start_s": 3725, "title": "Cierre"}])
    assert out == "## Capítulos\n\n- `00:00` Apertura\n- `01:02:05` Cierre\n"


# ----------------------------------------------------------------- service --
@pytest.fixture()
def env(tmp_path):
    db = Database(tmp_path / "scribe.db")
    sessions = SessionStore(db, tmp_path / "sessions")
    settings = SettingsStore(db)
    yield type("Env", (), {"db": db, "sessions": sessions, "settings": settings, "tmp": tmp_path})
    db.close()


def meeting(env, minutes=8, kind="meeting", status="done"):
    """A meeting of the given length: one line every 15 seconds, alternating sides."""
    lines = [(i * 15.0, i * 15.0 + 12.0, "yo" if i % 2 == 0 else "otros", f"Línea {i} de la reunión sobre el tema {i // 8}.") for i in range(minutes * 4)]
    session = env.sessions.create("Reunión de producto", kind, True, True, "es", status=status, started_at=MEETING_AT)
    env.sessions.add_segments(session["id"], [Labelled(a, b, s, t) for a, b, s, t in lines], live=False)
    return session["id"]


def service(env, link):
    return ChaptersService(env.db, env.sessions, env.settings, (lambda: link) if link is not None else None, now=lambda: 1_700_000_000.0)


GOOD = json.dumps([{"start": "00:00", "title": "Apertura y agenda"}, {"start": "02:01", "title": "Estado del producto"},
                   {"start": "04:00", "title": "Plan de lanzamiento"}, {"start": "06:02", "title": "Cierre y tareas"}])


def test_chapters_are_written_stored_and_not_asked_again(env):
    sid = meeting(env)
    link = ScriptedLink([GOOD])
    svc = service(env, link)
    first = svc.generate(sid)
    assert first["status"] == "ready" and first["cached"] is False and first["model"] == "test-model"
    assert [c["title"] for c in first["chapters"]] == ["Apertura y agenda", "Estado del producto", "Plan de lanzamiento", "Cierre y tareas"]
    assert all(c["start_s"] % 15 == 0 for c in first["chapters"]), "every start is the start of a transcript line"
    # One plain chat call, no tools, the transcript as lines.
    call = link.calls[0]
    assert "tools" not in call and "tool_choice" not in call and "response_format" not in call
    assert call["messages"][0]["role"] == "system" and "[00:00] yo: Línea 0" in call["messages"][1]["content"]
    again = svc.generate(sid)
    assert again["cached"] is True and len(link.calls) == 1
    link.replies.append(json.dumps([{"start": 0, "title": "Solo uno"}, {"start": 300, "title": "Otro más"}]))
    assert [c["title"] for c in svc.generate(sid, regenerate=True)["chapters"]] == ["Solo uno", "Otro más"]
    assert svc.view(sid)["chapters"][0]["title"] == "Solo uno"
    svc.discard(sid)
    assert svc.get(sid) is None


def test_deleting_the_session_deletes_its_chapters(env):
    sid = meeting(env)
    service(env, ScriptedLink([GOOD])).generate(sid)
    env.sessions.delete(sid)
    assert service(env, None).get(sid) is None


def test_outcomes_are_explicit(env):
    assert service(env, ScriptedLink()).generate(meeting(env, status="processing"))["status"] == "not_ready"
    silent = env.sessions.create("Vacía", "meeting", True, True, "es", status="done")["id"]
    assert service(env, ScriptedLink()).generate(silent)["status"] == "no_speech"
    short = service(env, ScriptedLink()).generate(meeting(env, minutes=2))
    assert short["status"] == "too_short" and "3 minutos" not in short["detail"] and "minutes" in short["detail"]
    with pytest.raises(LookupError):
        service(env, ScriptedLink()).generate("nope")
    sid = meeting(env)
    nothing = ScriptedLink(resolution=Resolution(capability="llm", provider=None, url=None, model=None, api=None, state="unavailable", reason="nothing loaded", details={}))
    assert service(env, nothing).generate(sid)["status"] == "no_model" and service(env, None).generate(sid)["status"] == "no_model"
    assert service(env, ScriptedLink([Unavailable("llm", ["gone"])])).generate(sid)["status"] == "no_model"
    assert service(env, ScriptedLink([BackendError("llamacpp", 500, "boom")])).generate(sid)["status"] == "error"
    broken = service(env, ScriptedLink(["lo siento, no puedo", "tampoco"]))
    result = broken.generate(sid)
    assert result["status"] == "error" and "usable chapters" in result["detail"]
    assert broken.view(sid)["last"]["status"] == "error" and broken.get(sid) is None
    assert service(env, nothing).availability()["available"] is False


def test_one_retry_when_the_answer_has_no_usable_chapters(env):
    sid = meeting(env)
    link = ScriptedLink(["Claro, aquí tienes los capítulos:", GOOD])
    assert service(env, link).generate(sid)["status"] == "ready"
    assert len(link.calls) == 2 and "only the JSON array" in link.calls[1]["messages"][-1]["content"]


def test_a_model_that_answers_off_the_clock_is_snapped_to_real_lines(env):
    sid = meeting(env)
    odd = json.dumps({"chapters": [{"start": "0:01", "title": '"Primero"'}, {"start": "125", "title": "Segundo tema largo de verdad hoy sí"},
                                   {"start": "04:07", "title": "Tercero"}]})
    result = service(env, ScriptedLink([odd])).generate(sid)
    assert [(c["start_s"], c["title"]) for c in result["chapters"]] == [(0.0, "Primero"), (120.0, "Segundo tema largo de verdad hoy"), (240.0, "Tercero")]


def test_after_a_transcription_meetings_get_chapters_in_the_background_when_the_setting_is_on(env):
    sid = meeting(env)
    link = ScriptedLink([GOOD])
    svc = service(env, link)
    env.settings.update({"auto_chapters": False})
    svc.after_transcription(sid)
    time.sleep(0.2)
    assert svc.get(sid) is None and not link.calls
    env.settings.update({"auto_chapters": True})
    svc.after_transcription(meeting(env, kind="note"))
    time.sleep(0.2)
    assert not link.calls, "voice notes are not divided into chapters"
    svc.after_transcription(sid)
    deadline = time.time() + 10
    while time.time() < deadline and svc.get(sid) is None:
        time.sleep(0.05)
    assert svc.get(sid)["chapters"][0]["title"] == "Apertura y agenda"
    svc.close()


def test_the_exports_carry_the_chapters(env):
    sid = meeting(env)
    svc = service(env, ScriptedLink([GOOD]))
    chapters = svc.generate(sid)["chapters"]
    session, segments = env.sessions.get(sid), env.sessions.segments(sid)
    md = render("md", session, segments, None, chapters)
    assert "## Capítulos" in md and "`02:00` Estado del producto" in md and md.index("## Capítulos") < md.index("## Transcripción")
    assert "Capítulos:\n[00:00] Apertura y agenda" in render("txt", session, segments, None, chapters)
    assert "Capítulos" not in render("md", session, segments) and "Capítulos" not in render("srt", session, segments, None, chapters)


# ---------------------------------------------- through the app and the tools --
@pytest.fixture()
def app_svc(tmp_path, monkeypatch):
    monkeypatch.setenv("HOARD_HUB_URL", "http://127.0.0.1:1")
    replies = {"chapters": GOOD}

    def answer(messages):
        return replies["chapters"] if "chapters" in messages[0]["content"] else {"summary": ["Resumen."], "decisions": [], "action_items": [], "open_questions": [], "participants": []}

    link = ScriptedLink(default=answer)
    service_ = Services(Config(data_dir=tmp_path / "audio", audio_backend="none", transcriber="fake"), link_provider=lambda: link, emit=lambda *a, **k: None)
    service_.start()
    yield type("App", (), {"svc": service_, "link": link})
    service_.stop()


def test_a_finished_transcription_writes_the_chapters_by_itself_and_the_tool_reads_them(app_svc):
    svc = app_svc.svc
    session = svc.sessions.create("Reunión larga", "meeting", True, False, "es", status="processing")
    write_wav(svc.sessions.session_dir(session["id"]) / "mic.wav", synth_speechlike(420.0))
    svc.pipeline.run_final(session["id"])
    deadline = time.time() + 20
    while time.time() < deadline and svc.chapters.get(session["id"]) is None:
        time.sleep(0.05)
    stored = svc.chapters.get(session["id"])
    assert stored is not None and stored["chapters"][0]["start_s"] == svc.sessions.segments(session["id"])[0]["start_s"]
    from funes_hoard.audio_memory.agent_tools import call_tool

    result = call_tool(svc, "scribe_chapters", {"session_id": session["id"]})
    assert result["status"] == "ready" and result["cached"] is True and result["chapters"][0]["t"] == "00:00"
    exported = call_tool(svc, "scribe_export", {"session_id": session["id"], "format": "md"})["text"]
    assert "## Capítulos" in exported
    assert call_tool(svc, "scribe_chapters", {"session_id": session["id"], "regenerate": True})["cached"] is False
