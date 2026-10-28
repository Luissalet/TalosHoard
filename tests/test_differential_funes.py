"""The helpers of the Funes absorption differential (scripts/differential/funes_absorption) that need no old Funes: the normaliser and the corpus."""
import importlib.util
import json
import sys
import time
from pathlib import Path

FOLDER = Path(__file__).resolve().parent.parent / "scripts" / "differential" / "funes_absorption"


def _load(name):
    sys.path.insert(0, str(FOLDER))
    try:
        spec = importlib.util.spec_from_file_location("funes_diff_" + name, FOLDER / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(FOLDER))


def test_corpus_covers_every_original_tool_and_both_entry_points():
    corpus = _load("corpus_cases")
    cases = corpus.cases()
    used = {c["tool"] for c in cases}
    assert set(corpus.ACTIVITY_TOOLS + corpus.AUDIO_TOOLS) <= used
    assert {c.get("via") for c in cases} == {None, "audio"}
    assert len(cases) >= 100
    assert cases[0]["list_tools"] == corpus.ACTIVITY_TOOLS + corpus.AUDIO_TOOLS


def test_normaliser_masks_only_what_may_differ():
    side = _load("side")
    norm = side.Norm("C:/Temp/funes-diff-x", {"meeting": "20260921-161320-aaaa"})
    norm.tool = "activity_project_resume"
    now = time.time()
    value = {"id": "20260921-161320-aaaa", "other": "20260930-101010-bbbb", "again": "20260930-101010-bbbb", "when": now, "iso": "2026-09-21T10:00:00+02:00",
             "path": "C:\\Temp\\funes-diff-x\\audio\\a.wav", "job": "0123456789ab", "since": "x", "reason": "unreachable", "keep": 42,
             "url": "http://127.0.0.1:5183/screen", "label": "today 09:41"}
    out = norm.value(value)
    assert out["id"] == "<meeting>" and out["other"] == "<sid0>" and out["again"] == "<sid0>"
    assert out["when"] == "<now>" and out["iso"] == "2026-09-21T10:00:00+02:00" and out["keep"] == 42
    assert out["path"] == "<tmp>" and out["job"] == "<job0>" and out["since"] == "<volatile>" and out["reason"] == "<down>"
    assert norm.value("Reunión\n" + time.strftime("%Y-%m-%d %H:%M") + "\n2026-09-21 16:13") == "Reunión\n<now>\n2026-09-21 16:13"
    assert out["url"] == "http://127.0.0.1:<port>" and out["label"] == "today <hh:mm>"
    # a wrong answer is still visible
    assert norm.value({"text": "Hola"}) != norm.value({"text": "Hola."})


def test_live_recordings_have_their_length_masked_and_nothing_else():
    side = _load("side")
    norm = side.Norm("C:/Temp/x", {})
    norm.elapsed.add("20261001-120000-cccc")
    out = norm.value({"id": "20261001-120000-cccc", "duration_s": 1.53, "title": "Directo", "kind": "note"})
    assert out["duration_s"] == "<elapsed>" and out["title"] == "Directo" and out["kind"] == "note"


def test_harness_files_declare_their_scope():
    for name in ("harness_talos", "harness_legacy"):
        text = (FOLDER / (name + ".py")).read_text(encoding="utf-8")
        assert "SCOPE" in text and "Not covered" in text
    assert json.loads(json.dumps({"ok": True}))["ok"]
