"""The helpers of the module-absorption differential (scripts/differential/module_absorption) that need no old repository: the corpora and the normaliser."""
import importlib.util
import sys
import time
from pathlib import Path

FOLDER = Path(__file__).resolve().parent.parent / "scripts" / "differential" / "module_absorption"
MODULES = {"argus": 80, "echo": 100, "cassandra": 120, "disk": 100}


def _load(name):
    sys.path.insert(0, str(FOLDER))
    try:
        spec = importlib.util.spec_from_file_location("module_diff_" + name, FOLDER / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(FOLDER))


def test_every_corpus_calls_every_tool_of_the_original_and_starts_with_the_tool_list():
    for name, minimum in MODULES.items():
        mod = _load("mod_" + name)
        cases = mod.cases()
        used = {c["tool"] for c in cases}
        assert set(mod.TOOLS) <= used, (name, sorted(set(mod.TOOLS) - used))
        assert len(cases) >= minimum, name
        assert cases[0]["list_tools"] == mod.TOOLS and cases[0]["tool"] == "tools"
        assert any(c["tool"] == "no_such_tool" for c in cases), name
        assert mod.TALOS_ID and mod.OLD_PKG and callable(mod.mutate) and callable(mod.build_base) and callable(mod.build_fixtures)


def test_additive_arguments_are_declared_only_where_talos_added_them():
    assert _load("mod_echo").ADDITIVE_ARGUMENTS == {"clip_recent": ["app"]}
    assert _load("mod_cassandra").ADDITIVE_ARGUMENTS == {"sites_watch": ["seo_interval_h", "seo_drop_points"]}
    assert _load("mod_argus").ADDITIVE_ARGUMENTS == {} and _load("mod_disk").ADDITIVE_ARGUMENTS == {}


def test_disk_corpus_never_uses_the_trash_or_a_protected_folder_as_a_delete_target():
    for case in _load("mod_disk").cases():
        if case["tool"] == "disk_delete":
            args = case["args"]
            paths = args.get("paths", [])
            assert all(str(p).startswith("<fix>") for p in paths)   # only inside the per-run copy of the fixtures
            if paths:
                assert args.get("mode") in ("permanent", "otro")   # the default mode is the trash: never used


def test_normaliser_masks_only_what_may_differ():
    side = _load("side")
    mod = _load("mod_echo")
    norm = side.Norm("C:/Temp/absorb-x", mod)
    now = time.time()
    value = {"when": now, "iso": "2026-09-21T10:00:00", "path": "C:\\Temp\\absorb-x\\data\\a.db", "url": "http://127.0.0.1:5188/x", "keep": 42,
             "started_at": 17.5, "text": "marcador"}
    out = norm.value(value)
    assert out["when"] == "<now>" and out["iso"] == "2026-09-21T10:00:00" and out["keep"] == 42
    assert out["path"] == "<tmp>" and out["url"] == "http://127.0.0.1:<port>/x" and out["started_at"] == "<volatile>"
    assert norm.value({"text": "Hola"}) != norm.value({"text": "Hola."})   # a wrong answer is still visible
    assert norm.shape({"a": [1, 2], "b": "x"}) == {"a": [type(1).__name__], "b": "str"}


def test_scratch_folders_of_the_three_sides_have_names_of_the_same_length():
    text = (FOLDER / "side.py").read_text(encoding="utf-8")
    assert '{"oracle": "orac", "main": "main", "native": "nati"}' in text


def test_harness_files_declare_their_scope():
    for name in ("harness_main", "harness_native"):
        text = (FOLDER / (name + ".py")).read_text(encoding="utf-8")
        assert "SCOPE" in text and "Not covered" in text
