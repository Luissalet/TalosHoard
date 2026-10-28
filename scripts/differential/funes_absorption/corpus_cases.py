"""The recorded call sequence replayed against both sides: every Activity and Audio tool of the original Funes, with
fixed dates (the base data is dated 2026-09-21..24), both entry points and the error paths."""

D1, D2, D3 = "2026-09-22", "2026-09-23", "2026-09-24"
A, B = D1 + "T00:00:00", D3 + "T23:59:00"


ACTIVITY_TOOLS = ["activity_agents_day", "activity_now", "activity_pause", "activity_project_resume", "activity_projects", "activity_recent_files", "activity_search",
                  "activity_summary", "activity_timeline", "activity_where_was_i", "minutes_get", "recall", "recall_search", "scribe_import_file", "scribe_minutes",
                  "sources_status", "transcribe_cancel", "transcribe_file", "transcribe_status"]
AUDIO_TOOLS = ["scribe_status", "scribe_sessions", "scribe_transcript", "scribe_search", "scribe_start", "scribe_stop", "scribe_note", "scribe_tag", "scribe_export",
               "scribe_delete"]


# Optional arguments Talos added to a tool the original already had (additive, so old callers are unaffected).
ADDITIVE_ARGUMENTS = {"scribe_search": ["session_id"]}


def cases():
    c = []
    c.append({"tool": "tools", "list_tools": ACTIVITY_TOOLS + AUDIO_TOOLS, "additive": ADDITIVE_ARGUMENTS})
    def add(tool, args=None, via=None, save=None, sleep=None, loose=False, coarse=False):
        spec = {"tool": tool, "args": args or {}}
        if via: spec["via"] = via
        if save: spec["save"] = save
        if sleep: spec["sleep"] = sleep
        if loose: spec["loose"] = True
        if coarse: spec["coarse"] = True
        c.append(spec)
    # --- activity (read) ---
    add("sources_status")
    for args in ({"day": D1}, {"day": D2, "group_by": "app"}, {"day": D3, "group_by": "project"}, {"start": A, "end": B, "group_by": "category"},
                 {"start": B, "end": A}, {"day": "not-a-date"}, {"group_by": "nonsense", "day": D1}):
        add("activity_summary", args)
    for args in ({"start": A, "end": B, "min_minutes": 5, "limit": 20}, {"start": A, "end": B, "limit": 5, "offset": 5}, {"around": D2 + "T11:00:00"},
                 {"start": D2 + "T09:00:00", "end": D2 + "T10:00:00", "min_minutes": 0}, {"limit": 0}):
        add("activity_timeline", args)
    for args in ({"query": "Atlas", "since": D1, "until": "2026-09-25"}, {"query": "zzzz-nothing", "since": D1}, {"query": "code", "since": D1, "limit": 3}, {"query": ""}, {}):
        add("activity_search", args)
    add("activity_projects", {"since": "2026-09-21"}); add("activity_projects", {"since": "2026-09-21", "limit": 1})
    add("activity_project_resume", {"project": "Atlas", "days": 30}); add("activity_project_resume", {"project": "does-not-exist"}); add("activity_project_resume", {})
    add("activity_recent_files", {"since": "2026-09-21"}); add("activity_recent_files", {"since": "2026-09-21", "limit": 2})
    for args in ({"before": D2 + "T12:00:00", "contexts": 3}, {"before": D3 + "T09:30:00", "all_categories": True}, {"before": "garbage"}):
        add("activity_where_was_i", args)
    add("activity_agents_day", {"day": D2}); add("activity_agents_day", {"day": D2, "kind": "turn", "limit": 2, "offset": 0})
    add("recall", {"at": D2 + "T10:30:00", "window_minutes": 30}); add("recall", {"at": D2 + "T10:30:00", "sources": ["activity"]})
    add("recall", {"at": "2026-09-21T10:00:00", "window_minutes": 600, "include_dropped": True})
    add("recall_search", {"query": "producto", "since": "2026-09-20", "until": "2026-09-30"}); add("recall_search", {"query": "Atlas", "since": "2026-09-20", "sources": ["activity"]})
    add("recall_search", {"query": "exportación", "since": "2026-09-20", "until": "2026-09-30", "limit_per_source": 1})
    # --- audio (read) ---
    add("scribe_status", via="audio")
    for args in ({}, {"kind": "interview"}, {"kind": "meeting"}, {"kind": "note"}, {"tag": "producto"}, {"q": "lanzamiento"}, {"q": "nothing-matches-this"}, {"from": "2026-09-22", "to": "2026-09-23"}, {"limit": 1}, {"kind": "bad-kind"}):
        add("scribe_sessions", args, via="audio")
    for sid in ("@meeting", "@call", "@note"):
        add("scribe_transcript", {"session_id": sid}, via="audio")
    add("scribe_transcript", {"session_id": "@meeting", "from_s": 100, "to_s": 200}, via="audio")
    add("scribe_transcript", {"session_id": "@meeting", "max_chars": 500}, via="audio")
    add("scribe_transcript", {"session_id": "no-such-session"}, via="audio"); add("scribe_transcript", {}, via="audio")
    for args in ({"q": "exportación"}, {"q": "delivery", "kind": "interview"}, {"q": "contrato"}, {"q": "fecha", "from": "2026-09-21", "to": "2026-09-22"}, {"q": "nada-de-esto"}, {"q": "a", "limit": 2}):
        add("scribe_search", args, via="audio")
    for fmt in ("md", "txt", "srt", "vtt", "bad-format"):
        add("scribe_export", {"session_id": "@meeting", "format": fmt}, via="audio")
    add("scribe_export", {"session_id": "@call"}, via="audio"); add("scribe_export", {"session_id": "no-such"}, via="audio")
    add("scribe_minutes", {"session_id": "@meeting"}, via="audio"); add("scribe_minutes", {"session_id": "@meeting"})
    add("scribe_minutes", {"session_id": "@call"}, via="audio"); add("scribe_minutes", {"session_id": "no-such"}, via="audio")
    add("minutes_get", {"minutes_id": "@meeting"}, via="audio"); add("minutes_get", {"minutes_id": "@meeting"}); add("minutes_get", {"minutes_id": "@call", "generate": False}, via="audio")
    add("minutes_get", {"minutes_id": "nope"}, loose=True)
    # --- audio (write) ---
    add("scribe_tag", {"session_id": "@call", "add": ["cliente", "urgente"]}, via="audio")
    add("scribe_tag", {"session_id": "@call", "remove": ["urgente"]}, via="audio"); add("scribe_tag", {"session_id": "@note", "add": ["Uno", "uno", " dos "]}, via="audio")
    add("scribe_tag", {"session_id": "no-such", "add": ["x"]}, via="audio"); add("scribe_tag", {"session_id": "@call"}, via="audio")
    add("scribe_sessions", {"tag": "cliente"}, via="audio"); add("scribe_sessions", {}, via="audio")
    add("scribe_note", {"session_id": "@note", "notes": "Segunda nota: pedir presupuesto."}, via="audio")
    add("scribe_note", {"session_id": "@meeting", "notes": "Revisar al final."}, via="audio"); add("scribe_note", {"session_id": "no-such", "notes": "x"}, via="audio")
    add("scribe_note", {"session_id": "@note", "notes": ""}, via="audio")
    add("scribe_export", {"session_id": "@note", "format": "md"}, via="audio"); add("scribe_transcript", {"session_id": "@note"}, via="audio")
    add("scribe_search", {"q": "presupuesto"}, via="audio")
    # imports with a fake transcriber (deterministic from the file)
    add("scribe_import_file", {"path": "<fix>/speech.wav", "title": "Importado de prueba", "kind": "note", "language": "es", "wait_s": 60}, via="audio", save={"imported": "session.id"})
    add("scribe_import_file", {"path": "<fix>/tone.wav", "title": "Solo un tono", "wait_s": 60}, via="audio"); add("scribe_import_file", {"path": "<fix>/missing.wav"}, via="audio"); add("scribe_import_file", {"path": "<fix>/tone.wav", "kind": "bad"}, via="audio")
    add("scribe_sessions", {}, via="audio"); add("scribe_transcript", {"session_id": "@imported"}, via="audio"); add("scribe_export", {"session_id": "@imported", "format": "srt"}, via="audio")
    add("scribe_import_file", {"path": "<fix>/speech.wav", "title": "Segunda importación", "wait_s": 60}, save={"imported2": "session.id"})
    add("transcribe_file", {"path": "<fix>/speech.wav", "language": "es", "wait_s": 60}, via="audio"); add("transcribe_file", {"path": "<fix>/speech.wav", "word_timestamps": True, "vad": False, "wait_s": 60})
    add("transcribe_file", {"path": "<fix>/missing.wav"}, via="audio"); add("transcribe_file", {}, loose=True)
    add("transcribe_status", {"job_id": "no-such-job"}, via="audio"); add("transcribe_cancel", {"job_id": "no-such-job"}, via="audio"); add("transcribe_status", {"job_id": "no-such-job"}, loose=True)
    add("scribe_start", {"title": "Directo de prueba", "kind": "note", "mic": True, "system": False, "language": "es"}, via="audio", save={"live": "session.id"}, sleep=1.5)
    add("scribe_status", via="audio"); add("scribe_stop", {"session_id": "@live"}, via="audio", sleep=1.5); add("scribe_stop", {"session_id": "@live"}, via="audio")
    add("scribe_stop", {"session_id": "no-such"}, via="audio"); add("scribe_start", {"kind": "bad"}, via="audio")
    # a meeting recorded on both tracks (microphone and system audio) with the fake backend, read back once the final pass is done
    add("scribe_start", {"title": "Reunión grabada", "kind": "meeting", "mic": True, "system": True, "language": "es"}, via="audio", save={"both": "session.id"}, sleep=4)
    add("scribe_stop", {"session_id": "@both"}, via="audio", sleep=6)
    add("scribe_transcript", {"session_id": "@both"}, via="audio", coarse=True); add("scribe_export", {"session_id": "@both", "format": "txt"}, via="audio", coarse=True)
    add("scribe_delete", {"session_id": "@both"}, via="audio")
    add("scribe_delete", {"session_id": "@imported"}, via="audio"); add("scribe_delete", {"session_id": "@imported"}, via="audio"); add("scribe_delete", {"session_id": "@imported2"}, via="audio")
    add("scribe_delete", {}, via="audio")
    add("scribe_sessions", {}, via="audio"); add("recall_search", {"query": "presupuesto", "since": "2026-09-20", "until": "2026-09-30"})
    # --- activity (write) last, they change the collector ---
    add("activity_pause", {"minutes": 1}); add("activity_pause", {"minutes": 0}); add("activity_pause", {"minutes": 99999}); add("activity_pause", {})
    add("activity_now"); add("activity_summary", {"day": D2})
    # --- not tools ---
    add("no_such_tool", {}, loose=True); add("no_such_tool", {}, via="audio", loose=True)
    return c
