"""Session search uses the family's text search: stopwords dropped, stems matched as prefixes, always valid FTS5."""

import sqlite3

import pytest

from funes_hoard.audio_memory.store import fts_query


def test_stopwords_are_dropped_and_words_match_by_stem():
    q = fts_query("la reunión de los presupuestos")
    assert all(f'"{word}"' not in q for word in ("la", "de", "los"))
    assert q == '"reunión"* AND "presupuesto"*'  # every content word is a prefix of its stem


def test_a_query_of_only_stopwords_still_searches_and_punctuation_gives_nothing():
    assert fts_query("de la") != ""
    assert fts_query("  *** ") == "" and fts_query("") == ""


@pytest.mark.parametrize("raw", ['funes-hoard', 'C++', '"unbalanced', 'AND', 'a OR', 'NEAR(', 'title:x', "contraseña'--"])
def test_hostile_text_is_always_a_valid_match_expression(raw):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(text, tokenize = 'unicode61 remove_diacritics 2')")
    conn.execute("INSERT INTO t VALUES ('hablamos de reuniones y presupuestos')")
    q = fts_query(raw)
    if q:
        conn.execute("SELECT * FROM t WHERE t MATCH ?", (q,)).fetchall()


def test_a_plural_finds_the_singular_and_accents_do_not_matter():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(text, tokenize = 'unicode61 remove_diacritics 2')")
    conn.execute("INSERT INTO t VALUES ('en la reunión hablamos del presupuesto')")
    for query in ("reuniones", "reunion", "presupuestos"):
        assert conn.execute("SELECT count(*) FROM t WHERE t MATCH ?", (fts_query(query),)).fetchone()[0] == 1, query


def test_exact_session_scope_is_applied_before_limit_and_preserves_global_search(tmp_path):
    from funes_hoard.audio_memory.db import Database
    from funes_hoard.audio_memory.merge import Labelled
    from funes_hoard.audio_memory.store import SessionStore

    db = Database(tmp_path / "audio.db")
    store = SessionStore(db, tmp_path / "sessions")
    try:
        a = store.create("Reunión homónima ñ", "meeting", True, False, "es", status="done")
        b = store.create("Reunión homónima ñ", "meeting", True, False, "es", status="done")
        for row in (a, b):
            store.add_segments(row["id"], [Labelled(0, 3, "yo", "Presupuesto de la reunión")], live=False)
        global_result = store.search("presupuestos", limit=10)
        assert {r["session"]["id"] for r in global_result["sessions"]} == {a["id"], b["id"]}
        scoped = store.search("presupuestos", limit=1, session_id=b["id"])
        assert scoped["total"] == 1
        assert [r["session"]["id"] for r in scoped["sessions"]] == [b["id"]]
        assert scoped["sessions"][0]["hits"][0]["start_s"] == 0
        assert store.search("presupuestos", session_id="missing-session")["sessions"] == []
        assert store.search("presupuestos", kind="note", session_id=b["id"])["total"] == 0
        assert store.search("presupuestos", session_id="")["total"] == 2
    finally:
        db.close()
