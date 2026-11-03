"""Meeting -> commitments / proposals / questions / decisions / requirements, and screen observation -> procedure draft.

Both are deterministic: the same transcript or event log always gives the same answer, no model is called and nothing is executed.
"""
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from funes_hoard.audio_memory.db import Database
from funes_hoard.audio_memory.merge import Labelled
from funes_hoard.audio_memory.requirements import (
    RequirementsService, analyze_segments, classify_clause, commitment_payload, fold, render_markdown,
)
from funes_hoard.audio_memory.store import SessionStore
from funes_hoard import procedure

MEETING_AT = datetime(2026, 10, 2, 10, 0).timestamp()  # a Friday
MEETING_DAY = date(2026, 10, 2)

# (start, end, speaker, text): one firm promise with a date, one "podriamos"/"could" proposal, one question to a person, one decision and
# two requirements per language, plus lines that must produce nothing at all (greeting, negated decision, tag question handled below).
ES = [
    (0, 6, "yo", "Buenos días a todos. Empezamos con la reforma de la cocina."),
    (6, 14, "yo", "Vale, yo me encargo de enviar el presupuesto revisado a Marta el martes."),
    (14, 20, "otros", "Podríamos mover la entrega al jueves si hace falta."),
    (20, 26, "yo", "Marta, ¿puedes confirmar el presupuesto de la reforma?"),
    (26, 32, "otros", "Hemos decidido usar la opción B para la cocina."),
    (32, 40, "yo", "La aplicación debe permitir exportar los informes en PDF."),
    (40, 46, "otros", "Tiene que funcionar sin conexión en la obra."),
    (46, 50, "yo", "Todavía no hemos decidido el color de los azulejos."),
    (66, 70, "otros", "Gracias, nos vemos luego."),
]
EN = [
    (0, 6, "otros", "Thanks everyone for joining."),
    (6, 12, "otros", "I'll send the signed contract to Pedro by Friday."),
    (12, 18, "yo", "We could also add a monthly summary."),
    (18, 22, "yo", "Pedro, can you review the draft?"),
    (22, 28, "otros", "We agreed to go with the second vendor."),
    (28, 34, "yo", "The system must support single sign-on."),
    (34, 40, "otros", "It needs to be available offline."),
    (44, 48, "yo", "We haven't decided on the logo yet."),
    (48, 52, "otros", "Who owns the legal review?"),
]


def segs(lines, first_id=1):
    return [{"id": first_id + i, "start_s": a, "end_s": b, "speaker": s, "text": t} for i, (a, b, s, t) in enumerate(lines)]


def kinds(items):
    return [(i["segment"]["id"], i["kind"]) for i in items]


# ------------------------------------------------------------------------------------------------ classification
def test_spanish_fixture_is_classified_exactly_with_cues():
    items = analyze_segments("s1", segs(ES), meeting_date=MEETING_DAY)
    assert kinds(items) == [(2, "commitment"), (3, "proposal"), (4, "question"), (5, "decision"), (6, "requirement"), (7, "requirement")]
    commit, proposal, question, decision, req1, req2 = items
    assert (commit["cue"], commit["cue_rule"], commit["firm"], commit["owner"], commit["counterpart"]) == ("yo me encargo", "es.commitment.me_encargo", True, "yo", "Marta")
    assert (commit["due_text"], commit["due"]) == ("el martes", "2026-10-06")
    assert (proposal["cue"], proposal["firm"], proposal["conditional"]) == ("Podríamos", False, False)
    assert proposal["why_not_firm"]
    assert (question["cue"], question["open"], question["addressee"]["kind"], question["addressee"]["name"]) == ("?", True, "person", "Marta")
    assert (decision["cue"], decision["cue_rule"]) == ("decidido", "es.decision.decidido")
    assert (req1["cue"], req2["cue"]) == ("debe", "Tiene que")
    assert all(0.3 <= i["confidence"] <= 0.97 for i in items)


def test_english_fixture_is_classified_exactly_with_cues():
    items = analyze_segments("s1", segs(EN), meeting_date=MEETING_DAY)
    assert kinds(items) == [(2, "commitment"), (3, "proposal"), (4, "question"), (5, "decision"), (6, "requirement"), (7, "requirement"), (9, "question")]
    commit, proposal, q_person, decision, req1, req2, q_anyone = items
    assert (commit["cue"], commit["owner"], commit["counterpart"], commit["due"]) == ("I'll send", "otros", "Pedro", "2026-10-09")
    assert (proposal["cue"], proposal["firm"]) == ("We could", False)
    assert (q_person["addressee"]["kind"], q_person["addressee"]["name"]) == ("person", "Pedro")
    assert (q_anyone["addressee"]["kind"], q_anyone["addressee"]["name"]) == ("anyone", None)
    assert decision["cue"] == "We agreed"
    assert (req1["cue"], req2["cue"]) == ("must", "It needs to")


def test_mixed_language_meeting_uses_both_rule_sets():
    items = analyze_segments("s1", segs(ES + EN), meeting_date=MEETING_DAY)
    assert len(items) == 6 + 7
    assert {i["lang"] for i in items} == {"es", "en"}


def test_only_the_asked_language_and_kinds_are_applied():
    spanish_only = analyze_segments("s1", segs(ES + EN), meeting_date=MEETING_DAY, lang="es")
    assert all(i["lang"] == "es" or i["kind"] == "question" for i in spanish_only)
    assert kinds(analyze_segments("s1", segs(ES), meeting_date=MEETING_DAY, kinds=["decision", "requirement"])) == [(5, "decision"), (6, "requirement"), (7, "requirement")]
    assert analyze_segments("s1", segs(ES), meeting_date=MEETING_DAY, min_confidence=0.95) == []


@pytest.mark.parametrize("sentence", [
    "Podríamos enviarlo el lunes.", "Quizá lo enviemos el lunes.", "A lo mejor lo hago yo el viernes.", "Intentaré mandarlo el jueves.",
    "Tal vez me encargo yo del informe.", "Si me pasas el contrato, lo reviso el lunes.", "Propongo que lo envíe Marta el martes.", "Habría que enviarlo el lunes.",
    "We could send it on Monday.", "Maybe we send it on Monday.", "Perhaps I'll do it by Friday.", "I'll try to send it by Friday.", "If you give me access, I'll send it on Monday.",
    "What if we send it on Monday?", "I suggest we ship it on Friday.", "I'll probably send it tomorrow.", "How about sending it on Monday",
])
def test_hedged_or_conditional_words_never_become_a_firm_commitment(sentence):
    verdict = classify_clause(sentence, "auto", "yo")
    assert verdict is not None and verdict["kind"] != "commitment", (sentence, verdict)
    assert verdict["kind"] in ("proposal", "question")


@pytest.mark.parametrize("sentence, expected", [
    ("Me comprometo a enviarlo el viernes.", "es.commitment.prometo"), ("Lo haré yo.", "es.commitment.lo_hare"), ("Voy a preparar el informe.", "es.commitment.voy_a"),
    ("Te lo mando mañana.", "es.commitment.te_envio"), ("Enviaré el informe el lunes.", "es.commitment.futuro_acento"),
    ("I promise to send it on Friday.", "en.commitment.promise"), ("I will deliver the report on Monday.", "en.commitment.ill"), ("Let me prepare the summary.", "en.commitment.let_me"),
])
def test_firm_first_person_promises(sentence, expected):
    verdict = classify_clause(sentence, "auto", "yo")
    assert verdict["kind"] == "commitment" and verdict["rule"] == expected, verdict


def test_a_named_person_who_will_do_something_is_a_commitment_of_that_person():
    es = analyze_segments("s", segs([(0, 5, "otros", "Pedro enviará el informe de costes el viernes.")]), meeting_date=MEETING_DAY)
    en = analyze_segments("s", segs([(0, 5, "yo", "Marta will send the draft on Monday.")]), meeting_date=MEETING_DAY)
    assert [(i["kind"], i["owner"]) for i in es + en] == [("commitment", "Pedro"), ("commitment", "Marta")]


@pytest.mark.parametrize("sentence", [
    "Todavía no hemos decidido el presupuesto.", "We haven't decided on the logo yet.", "Hay que decidir el color.", "We still need to decide who goes.",
    "If we decided that, it would be worse.", "¿Hemos decidido ya el color?",
])
def test_negated_pending_or_asked_decisions_are_not_decisions(sentence):
    verdict = classify_clause(sentence, "auto", "yo")
    assert verdict is None or verdict["kind"] != "decision", verdict


def test_tag_questions_do_not_turn_a_statement_into_a_question():
    verdict = classify_clause("Lo envío el viernes, ¿vale?", "auto", "yo")
    assert verdict["kind"] == "commitment"
    assert classify_clause("I'll do it Monday, okay?", "auto", "yo")["kind"] == "commitment"


def test_questions_say_who_must_answer():
    def who(text, speaker="yo"):
        return classify_clause(text, "auto", speaker)["addressee"]
    assert who("¿Puedes enviarlo hoy?")["kind"] == "speaker" and who("¿Puedes enviarlo hoy?")["name"] == "otros"
    assert who("Could you send it today?", "otros")["name"] == "yo"
    assert who("¿Quién se encarga del contrato?")["kind"] == "anyone"
    assert who("¿Podemos cerrar esto hoy?")["kind"] == "group"
    assert who("¿Qué opina Lucía de la fecha?")["name"] == "Lucía"
    assert who("¿Cuándo llega el material?")["kind"] == "unassigned"
    assert classify_clause("Puedes enviarlo hoy", "auto", "yo")["kind"] == "question"  # speech recognition often drops the mark


def test_classification_is_deterministic_and_item_ids_are_stable():
    a = analyze_segments("s1", segs(ES), meeting_date=MEETING_DAY)
    b = analyze_segments("s1", segs(ES, first_id=500), meeting_date=MEETING_DAY)  # other row ids, same words and times
    assert [i["id"] for i in a] == [i["id"] for i in b] and a != []
    assert analyze_segments("other", segs(ES), meeting_date=MEETING_DAY)[0]["id"] != a[0]["id"]


def test_fold_keeps_offsets():
    assert len(fold("Cañón ÁÉÍÓÚ’")) == len("Cañón ÁÉÍÓÚ’") and fold("Mañana") == "manana"


# ------------------------------------------------------------------------------------------------ the service: links, playback, exports
@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / "audio.db")
    sessions = SessionStore(db, tmp_path / "sessions")
    session = sessions.create("Reunión de la reforma", "meeting", True, True, "es", started_at=MEETING_AT)
    sessions.add_segments(session["id"], [Labelled(a, b, s, t) for a, b, s, t in ES + EN], live=False)
    svc = SimpleNamespace(sessions=sessions, requirements=RequirementsService(db, sessions))
    yield SimpleNamespace(svc=svc, session=session, db=db)
    db.close()


def test_every_item_links_to_the_exact_segment_for_playback(env):
    result = env.svc.requirements.analyze(env.session["id"])
    stored = {(s["start_s"], s["end_s"]): s for s in env.svc.sessions.segments(env.session["id"])}
    assert result["items"] and result["meeting_date"] == "2026-10-02"
    for item in result["items"]:
        seg = stored[(item["segment"]["start_s"], item["segment"]["end_s"])]
        assert item["segment"]["id"] == seg["id"] and item["segment"]["text"] == seg["text"] and item["speaker"] == seg["speaker"]
        assert item["text"] in seg["text"]
        play = item["playback"]
        assert (play["session_id"], play["start_s"], play["end_s"], play["transcript"]) == (env.session["id"], seg["start_s"], seg["end_s"], seg["text"])
        assert play["transcript_call"] == {"tool": "scribe_transcript", "arguments": {"session_id": env.session["id"], "from_s": seg["start_s"], "to_s": seg["end_s"]}}
    assert result["summary"]["by_kind"] == {"commitment": 2, "proposal": 2, "question": 3, "decision": 2, "requirement": 4}


def test_requirements_link_to_engagement_references_and_nothing_else_does(env):
    sid = env.session["id"]
    items = env.svc.requirements.analyze(sid)["items"]
    requirement = next(i for i in items if i["kind"] == "requirement")
    decision = next(i for i in items if i["kind"] == "decision")
    proposal = next(i for i in items if i["kind"] == "proposal")
    assert env.svc.requirements.link(sid, requirement["id"], "DEL-12", "deliverable", "ENG-7")["linked"]
    assert env.svc.requirements.link(sid, requirement["id"], "DEL-12", "deliverable", "ENG-7")["linked"]  # idempotent
    env.svc.requirements.link(sid, decision["id"], "DEC-3", "decision")
    with pytest.raises(ValueError, match="Only requirement and decision"):
        env.svc.requirements.link(sid, proposal["id"], "X-1")
    with pytest.raises(LookupError):
        env.svc.requirements.link(sid, "rq-nope", "X-1")
    with pytest.raises(ValueError):
        env.svc.requirements.link(sid, requirement["id"], "  ")
    linked = env.svc.requirements.analyze(sid)["items"]
    assert [r["ref"] for r in next(i for i in linked if i["id"] == requirement["id"])["refs"]] == ["DEL-12"]
    only = env.svc.requirements.analyze(sid, engagement_ref="ENG-7")["items"]
    assert [i["id"] for i in only] == [requirement["id"]]
    assert [i["id"] for i in env.svc.requirements.analyze(sid, engagement_ref="DEC-3")["items"]] == [decision["id"]]
    assert env.svc.requirements.link(sid, requirement["id"], "DEL-12", remove=True)["removed"]
    assert env.svc.requirements.analyze(sid, engagement_ref="ENG-7")["items"] == []


def test_links_survive_but_report_orphans_when_the_transcript_changes(env):
    sid = env.session["id"]
    item = next(i for i in env.svc.requirements.analyze(sid)["items"] if i["kind"] == "requirement")
    env.svc.requirements.link(sid, item["id"], "DEL-1")
    env.svc.sessions.replace_segments(sid, [Labelled(0, 5, "yo", "Hola")])
    result = env.svc.requirements.analyze(sid)
    assert result["items"] == [] and [o["ref"] for o in result["orphan_links"]] == ["DEL-1"]


def test_markdown_and_json_exports(env):
    sid = env.session["id"]
    item = next(i for i in env.svc.requirements.analyze(sid)["items"] if i["kind"] == "requirement")
    env.svc.requirements.link(sid, item["id"], "DEL-12", "deliverable", "ENG-7")
    md = env.svc.requirements.export(sid, "md")
    for heading in ("## Compromisos firmes (2)", "## Decisiones (2)", "## Requisitos (4)", "## Preguntas abiertas (3)", "## Propuestas (no son compromisos) (2)"):
        assert heading in md
    assert "`00:06` (yo) Vale, yo me encargo" in md and "indicio: «yo me encargo»" in md and "vinculado a: `DEL-12` (deliverable)" in md
    english = env.svc.requirements.export(sid, "md", locale="en")
    assert "## Firm commitments (2)" in english and "## Proposals (not commitments) (2)" in english and "cue: «Podríamos»" in english
    data = env.svc.requirements.export(sid, "json")
    assert data["summary"]["total"] == 13 and data["items"][0]["playback"]["session_id"] == sid
    assert render_markdown(env.svc.sessions.get(sid), [], "es").count("Nada detectado.") == 5


def test_tools_return_the_three_shapes(env):
    from funes_hoard.audio_memory import agent_tools  # imported here: importing it early loads the audio services before tests that assert they are not loaded
    sid = env.session["id"]
    call = lambda args: agent_tools.call_tool(env.svc, "scribe_requirements", {"session_id": sid, **args})
    assert call({})["summary"]["total"] == 13
    assert "# Requisitos y pendientes de la reunión" in call({"format": "md"})["text"]
    assert [i["kind"] for i in call({"kinds": ["decision"]})["items"]] == ["decision", "decision"]
    importable = call({"format": "commitments"})
    assert [c["text"] for c in importable["commitments"]] == ["Vale, yo me encargo de enviar el presupuesto revisado a Marta el martes.", "I'll send the signed contract to Pedro by Friday."]
    assert {r["kind"] for r in importable["rejected"]} == {"proposal", "question", "decision", "requirement"}
    assert all(r["reason"] for r in importable["rejected"])
    names = {t["name"] for t in agent_tools.tool_catalog()}
    assert {"scribe_requirements", "scribe_requirement_link"} <= names
    with pytest.raises(LookupError):
        agent_tools.call_tool(env.svc, "scribe_requirements", {"session_id": "missing"})


def test_commitment_payload_is_the_exchange_shape(env):
    sid = env.session["id"]
    payload = env.svc.requirements.importable_commitments(sid)["commitments"][0]
    assert payload["schema"] == "talos.commitment/1" and payload["firm"] is True and payload["kind"] == "commitment"
    assert payload["source"]["ref"] == f"talos:{sid}#{payload['item_id']}"
    assert (payload["source"]["start_s"], payload["source"]["end_s"], payload["source"]["session_id"]) == (6, 14, sid)
    assert payload["due"] == "2026-10-06" and payload["owner"] == "yo" and payload["counterpart"] == "Marta"
    whole = env.svc.requirements.importable_commitments(sid)
    assert datetime.fromisoformat(payload["source"]["at"]).timestamp() == MEETING_AT + 6
    assert datetime.fromisoformat(whole["meeting"]["at"]).timestamp() == MEETING_AT and whole["meeting"]["session_id"] == sid and whole["schema"] == "talos.commitments/1"
    proposal = next(i for i in env.svc.requirements.analyze(sid)["items"] if i["kind"] == "proposal")
    assert commitment_payload(proposal)["firm"] is True  # the payload builder trusts its caller; importable_commitments never passes proposals


# ------------------------------------------------------------------------------------------------ procedure draft
T0 = 1_790_000_000.0  # any instant; only offsets matter
SECRET = "Hunter2!x9"


def log():
    return [
        {"ts": T0, "type": "focus", "app": "Excel", "title": "Pedidos.xlsx"},
        {"ts": T0 + 2, "type": "screenshot", "ref": "argus:moment 10", "app": "Excel", "title": "Pedidos.xlsx"},
        {"ts": T0 + 5, "type": "click", "app": "Excel", "target": "Celda B2"},
        {"ts": T0 + 8, "type": "copy", "app": "Excel", "text": "ACME S.L."},
        {"ts": T0 + 12, "type": "focus", "app": "Chrome", "title": "Alta de cliente - ERP"},
        {"ts": T0 + 13, "type": "screenshot", "ref": "argus:moment 11", "app": "Chrome"},
        {"ts": T0 + 15, "type": "type", "field": "Email", "text": "compras@acme.example"},
        {"ts": T0 + 18, "type": "type", "field": "Contraseña", "text": SECRET},
        {"ts": T0 + 25, "type": "paste", "app": "Chrome", "field": "Razón social", "text": "ACME S.L."},
        {"ts": T0 + 30, "type": "click", "app": "Chrome", "x": 300, "y": 410},
        {"ts": T0 + 31, "type": "screenshot", "ref": "argus:moment 12", "app": "Chrome"},
        {"ts": T0 + 200, "type": "clipboard", "source_app": "Chrome", "text": "Pedido 4471 creado"},
    ]


def test_procedure_steps_have_evidence_and_the_right_shape():
    draft = procedure.build_draft(log(), locale="en")
    assert draft["schema"] == "talos.procedure_draft/1" and draft["draft"] is True and draft["executes_nothing"] is True
    assert [s["kind"] for s in draft["steps"]] == ["app_switch", "click", "copy", "app_switch", "fill_form", "copy_paste", "click", "copy"]
    assert [s["app"] for s in draft["steps"]] == ["Excel", "Excel", "Excel", "Chrome", "Chrome", "Chrome", "Chrome", "Chrome"]
    assert [s["n"] for s in draft["steps"]] == list(range(1, 9))
    assert [s["t_start"] for s in draft["steps"]] == sorted(s["t_start"] for s in draft["steps"])
    click = draft["steps"][1]
    assert click["target"] == "Celda B2" and click["screenshot"]["ref"] == "argus:moment 10" and click["evidence"][0]["type"] == "click"
    switch = draft["steps"][3]
    assert switch["screenshot"]["ref"] == "argus:moment 11" and switch["window"] == "Alta de cliente - ERP"
    fill = draft["steps"][4]
    assert fill["inputs"] == ["email", "contrasena"] and [e["type"] for e in fill["evidence"]] == ["type", "type"]
    transfer = draft["steps"][5]
    assert (transfer["from_step"], transfer["from_app"]) == (3, "Excel") and transfer["copy_evidence"]["type"] == "copy" and draft["steps"][2]["transferred_in_step"] == 6
    assert "Excel" in transfer["title"]
    assert draft["window"]["by_type"] == {"focus": 2, "screenshot": 3, "click": 2, "copy": 1, "type": 2, "paste": 1, "clipboard": 1}


def test_procedure_inputs_outputs_and_secret_masking():
    draft = procedure.build_draft(log(), locale="es")
    inputs = {i["name"]: i for i in draft["inputs"]}
    assert inputs["email"]["example"] == "compras@acme.example" and inputs["email"]["kind"] == "email" and not inputs["email"]["masked"]
    assert inputs["contrasena"]["masked"] is True and inputs["contrasena"]["example"] == "[masked]" and inputs["contrasena"]["masked_reason"].startswith("field")
    assert inputs["razon_social"]["source"] == "copied from Excel" and inputs["razon_social"]["example"] == "ACME S.L."
    assert draft["masked_values"] >= 1
    # the secret is nowhere in the output, in any form
    import json
    assert SECRET not in json.dumps(draft, ensure_ascii=False) and SECRET not in procedure.render_markdown(draft)
    kinds_out = [o["kind"] for o in draft["outputs"]]
    assert "transferred_value" in kinds_out and "final_view" in kinds_out
    transferred = next(o for o in draft["outputs"] if o["kind"] == "transferred_value")
    assert transferred["value"] == "ACME S.L." and transferred["step"] == 6


def test_procedure_lists_what_it_cannot_know():
    draft = procedure.build_draft(log(), locale="en")
    codes = [(u["code"], u["step"]) for u in draft["unknowns"]]
    assert ("intent_not_visible", None) in codes and ("single_run", None) in codes
    assert ("target_not_identified", 7) in codes  # the click with only a position
    assert ("secret_masked", 5) in codes
    assert ("paste_not_observed", 8) in codes  # the last clip was never pasted anywhere
    assert ("final_state_not_observed", 8) in codes
    assert any(c == "gap" for c, _ in codes)  # 170 s with nothing before the last clip
    assert ("no_screenshot", 8) in codes
    assert ("no_input_events", None) not in codes
    assert all(u["message"] for u in draft["unknowns"])
    assert draft["verify"].startswith("Draft for a person")


def test_a_log_without_clicks_or_keys_says_so_and_still_detects_a_copy_then_typed_value():
    events = [
        {"ts": T0, "type": "focus", "app": "Excel", "title": "Pedidos.xlsx"},
        {"ts": T0 + 8, "type": "clipboard", "source_app": "Excel", "text": "ACME S.L."},
        {"ts": T0 + 12, "type": "focus", "app": "Chrome", "title": "ERP"},
        {"ts": T0 + 15, "type": "type", "field": "Cliente", "text": "ACME S.L."},
    ]
    draft = procedure.build_draft(events)
    assert draft["steps"][2]["kind"] == "app_switch" and draft["steps"][3]["from_steps"] == [2]
    assert draft["inputs"][0]["source"].startswith("copied from Excel")
    codes = [u["code"] for u in draft["unknowns"]]
    assert "no_screenshots" in codes and "no_screenshot" not in codes
    screen_only = procedure.build_draft(events[:3])
    assert "no_input_events" in [u["code"] for u in screen_only["unknowns"]]


@pytest.mark.parametrize("value, label, expected", [
    ("ghp_abcdefghijklmnopqrstuvwxyz0123456789", "", "known token format"), ("sk-abcdefghijklmnopqrstuvwx12345", "", "known token format"),
    ("4111 1111 1111 1111", "", "card number"), ("anything", "Password", "field «Password»"), ("anything", "", ""), ("x", "", ""),
    ("Hunter2!x9", "", "password-like string"), ("compras@acme.example", "", ""), ("https://acme.example/pedido/4471", "", ""), ("2026-10-02", "", ""),
    ("ACME S.L.", "", ""), ("C:\\Users\\luis\\Pedidos.xlsx", "", ""), ("Marta", "", ""),
])
def test_secret_detection(value, label, expected):
    assert procedure.secret_reason(value, label) == expected


def test_secrets_inside_free_text_and_titles_are_masked_too():
    masked, reasons = procedure.mask_text("curl -H 'Authorization: Bearer abcdefghijklmnop12345' https://api.example")
    assert "abcdefghijklmnop12345" not in masked and reasons
    draft = procedure.build_draft([
        {"ts": T0, "type": "focus", "app": "Terminal", "title": "export TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123456789"},
        {"ts": T0 + 1, "type": "type", "text": "echo ghp_abcdefghijklmnopqrstuvwxyz0123456789 | gh auth login --with-token"},
    ])
    import json
    assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in json.dumps(draft)


def test_bad_events_are_reported_not_fatal_and_an_empty_log_is_explained():
    draft = procedure.build_draft([{"type": "click"}, {"ts": 5, "type": "dance"}, "x", {"ts": T0, "type": "focus", "app": "A"}])
    assert [r["reason"] for r in draft["rejected_events"]] == ["no usable time", "unknown type 'dance'", "not an object"]
    assert len(draft["steps"]) == 1
    empty = procedure.build_draft([])
    assert empty["status"] == "empty" and empty["steps"] == [] and empty["unknowns"][0]["code"] == "no_events"


def test_the_draft_is_deterministic_and_executes_nothing():
    assert procedure.build_draft(log()) == procedure.build_draft(log())
    a, b = procedure.build_draft(log()), procedure.build_draft(list(reversed(log())))  # input order is irrelevant: events are sorted by time
    assert [(s["kind"], s["title"], s["t_start"], s["inputs"]) for s in a["steps"]] == [(s["kind"], s["title"], s["t_start"], s["inputs"]) for s in b["steps"]]
    assert a["inputs"] == b["inputs"] and a["unknowns"] == b["unknowns"] and a["shape"] == b["shape"]
    source = open(procedure.__file__, encoding="utf-8").read()
    for forbidden in ("subprocess", "os.system", "pyautogui", "import ctypes", "webbrowser"):
        assert forbidden not in source


# ------------------------------------------------------------------------------------------------ through the running app
@pytest.fixture
def quiet_engines(monkeypatch, tmp_path):
    values = {"ECHO_BACKEND": "fake", "ARGUS_CAPTURE": "fake", "ARGUS_WINDOW": "fake", "ARGUS_VISUAL": "none", "SCRIBE_AUDIO": "fake", "SCRIBE_TRANSCRIBER": "fake",
              "CASSANDRA_AUTOSTART": "0", "CASSANDRA_GPU": "0", "CASSANDRA_BUS": "0", "CASSANDRA_EXTERNALS": "0", "CASSANDRA_HUB_REGISTRY": "0", "CASSANDRA_DEFAULT_LOGS": "0",
              "CASSANDRA_ROOTS": str(tmp_path), "HOARD_HUB_URL": "http://127.0.0.1:1", "HOARD_FAUSTUS_URL": "http://127.0.0.1:1"}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    from funes_hoard import api
    from funes_hoard.collectors.fake import FakeProbe
    from funes_hoard.core.spans import Sample
    monkeypatch.setattr(api, "_pick_probe", lambda demo: FakeProbe([Sample(1700000000, "Fixture", "fixture.exe", "Synthetic", 1, 0, False)]))
    monkeypatch.setattr(api, "windows_recent_dir", lambda: None)


def test_rest_and_agent_surfaces_in_the_running_app(tmp_path, quiet_engines):
    from fastapi.testclient import TestClient
    from talos_hoard.app import create_app

    app = create_app(tmp_path, port=5220)
    auth = {"Authorization": "Bearer " + app.state.token}
    with TestClient(app, base_url="http://127.0.0.1:5220") as c:
        names = {t["name"] for t in c.get("/api/agent/tools").json()["tools"]}
        assert {"scribe_requirements", "scribe_requirement_link", "activity_procedure_draft"} <= names
        assert c.put("/api/modules/audio", json={"enabled": True}).status_code == 200
        services = app.state.modules["audio"].app.state.services
        session = services.sessions.create("Reunión de la reforma", "meeting", True, True, "es", started_at=MEETING_AT)
        services.sessions.add_segments(session["id"], [Labelled(a, b, s, t) for a, b, s, t in ES], live=False)
        sid = session["id"]
        body = c.get(f"/audio/api/sessions/{sid}/requirements").json()
        assert body["summary"]["by_kind"]["commitment"] == 1
        md = c.get(f"/audio/api/sessions/{sid}/requirements?format=md&locale=en")
        assert md.status_code == 200 and "## Firm commitments (1)" in md.text
        item = next(i for i in body["items"] if i["kind"] == "requirement")
        link = c.post(f"/audio/api/sessions/{sid}/requirements/links", json={"item_id": item["id"], "ref": "DEL-9", "engagement": "ENG-1"})
        assert link.status_code == 200 and link.json()["linked"]
        proposal = next(i for i in body["items"] if i["kind"] == "proposal")
        assert c.post(f"/audio/api/sessions/{sid}/requirements/links", json={"item_id": proposal["id"], "ref": "X"}).status_code == 400
        assert c.get(f"/audio/api/sessions/{sid}/requirements?engagement_ref=ENG-1").json()["summary"]["total"] == 1
        assert c.get("/audio/api/sessions/nope/requirements").status_code == 404
        call = c.post("/api/agent/call", headers=auth, json={"name": "scribe_requirements", "arguments": {"session_id": sid, "format": "commitments"}})
        assert call.status_code == 200 and call.json()["commitments"][0]["source"]["ref"].startswith("talos:" + sid)
        unlink = c.post("/api/agent/call", headers=auth, json={"name": "scribe_requirement_link", "arguments": {"session_id": sid, "item_id": item["id"], "ref": "DEL-9", "remove": True}})
        assert unlink.json()["removed"] is True

        assert c.put("/api/modules/activity", json={"enabled": True}).status_code == 200
        draft = c.post("/api/agent/call", headers=auth, json={"name": "activity_procedure_draft", "arguments": {"events": log(), "locale": "en"}})
        assert draft.status_code == 200, draft.text
        assert draft.json()["executes_nothing"] is True and len(draft.json()["steps"]) == 8 and SECRET not in draft.text
        text = c.post("/api/agent/call", headers=auth, json={"name": "activity_procedure_draft", "arguments": {"events": log(), "format": "md"}}).json()
        assert "# Procedimiento propuesto" in text["text"]
        recorded = c.post("/api/agent/call", headers=auth, json={"name": "activity_procedure_draft", "arguments": {"start": "-10m"}})
        assert recorded.status_code == 200, recorded.text
        assert recorded.json()["window"]["sources"][0] == "funes" and "unavailable_sources" in recorded.json()
        assert c.post("/api/agent/call", headers=auth, json={"name": "activity_procedure_draft", "arguments": {"start": "-9h"}}).status_code == 400
        # the page and its UI route (no token: guarded by host and origin like every UI route)
        page = c.get("/static/analysis.html")
        assert page.status_code == 200 and 'id="tab-procedure"' in page.text and "analysis.js" in page.text
        assert c.get("/static/analysis.js").status_code == 200 and "textContent" in c.get("/static/analysis.js").text
        assert 'href="/static/analysis.html"' in c.get("/").text
        ui = c.post("/activity/api/procedure/draft", json={"events": log(), "locale": "en"}, headers={"X-Hoard-Request": "1"})
        assert ui.status_code == 200 and ui.json()["executes_nothing"] is True and SECRET not in ui.text
        sessions = c.get("/audio/api/sessions?limit=100").json()["sessions"]
        assert [x["id"] for x in sessions] == [sid]
