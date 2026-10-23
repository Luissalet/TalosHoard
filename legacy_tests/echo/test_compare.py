from echo.agent_tools import call_tool
from echo.comparison import ENDINGS


def capture(services, text, title):
    return services.clips.capture_text(text, source_app="fixture", source_title=title, now=services.now())["id"]


def test_literal_rows_reconstruct_both_texts_and_preserve_direction(services):
    a = "inicio\nquitar\nancla\nviejo \r\notra\nfin"
    b = "inicio\nancla\nnuevo\t\notra\ninsertada\nfin\n"
    left, right = capture(services, a, "A"), capture(services, b, "B")
    args = {"left_id": left, "right_id": right, "max_chars_per_clip": 20000}
    result = call_tool(services, "clip_compare", args)
    terminators = {label: ending for ending, label in ENDINGS.items()} | {"none": ""}
    def restore(rows, excluded):
        return "".join(row["text"] + terminators[row["ending"]] for row in rows if row["tag"] != excluded)
    assert restore(result["rows"], "insert") == a
    assert restore(result["rows"], "delete") == b
    assert result["summary"] == {"equal": 3, "removed": 3, "added": 3, "replacement_blocks": 2}
    assert any(row["text"] == "viejo " and row["ending"] == "CRLF" and row["tag"] == "delete" for row in result["rows"])
    assert any(row["text"] == "nuevo\t" and row["tag"] == "insert" for row in result["rows"])
    assert any(row["text"] == "fin" and row["ending"] == "none" and row["tag"] == "delete" for row in result["rows"])
    reverse = call_tool(services, "clip_compare", {**args, "left_id": right, "right_id": left})
    assert restore(reverse["rows"], "insert") == b
    assert restore(reverse["rows"], "delete") == a
    assert result["text_scope"] == "full_saved_text" and not result["identical_read_text"]


def test_api_agent_contract_partial_text_and_response_cap_are_separate(client):
    svc = client.services
    left = capture(svc, "uno \r\nfin", "A")
    right = capture(svc, "uno\t\nfin\n", "B")
    args = {"left_id": left, "right_id": right, "max_chars_per_clip": 20000}
    response = client.post("/api/clips/compare", json=args)
    agent = client.post("/api/agent/call", json={"name": "clip_compare", "arguments": args},
                        headers={"Authorization": "Bearer " + svc.token})
    assert response.status_code == agent.status_code == 200
    assert response.json() == agent.json() == call_tool(svc, "clip_compare", args)
    # The two full saved texts differ beyond the existing reader's 20k prefix.
    prefix = "a \r\n" * 5000
    first, second = capture(svc, prefix + "A", "partial A"), capture(svc, prefix + "B", "partial B")
    def snapshot():
        with svc.db.lock:
            return {table: [tuple(row) for row in svc.db.conn.execute("SELECT * FROM " + table)]
                    for table in ("clips", "clip_selections", "settings")}
    before = snapshot()
    args = {"left_id": first, "right_id": second, "max_chars_per_clip": 20000}
    native = client.post("/api/clips/compare", json=args).json()
    capped = call_tool(svc, "clip_compare", args)
    assert native["text_scope"] == capped["text_scope"] == "extracts"
    assert native["identical_read_text"] is True and native["left"]["truncated"] and native["right"]["truncated"]
    assert native["left"]["chars"] == 20001 and native["left"]["chars_read"] == 20000
    assert native["total_rows"] == capped["total_rows"] == 5000
    assert len(native["rows"]) == 5000 and len(capped["rows"]) < 5000
    assert "truncated" not in native and isinstance(capped["truncated"], dict)
    assert capped["rows"] == native["rows"][:len(capped["rows"])]
    assert snapshot() == before and not svc.status()["watching"] and not svc.config.ocr_enabled
