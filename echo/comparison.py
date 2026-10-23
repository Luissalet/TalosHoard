"""Literal line differences over the text supplied by the native clip reader."""
from difflib import SequenceMatcher

ENDINGS = {"\r\n": "CRLF", "\n": "LF", "\r": "CR", "\v": "VT", "\f": "FF",
           "\x1c": "FS", "\x1d": "GS", "\x1e": "RS", "\x85": "NEL", "\u2028": "LS", "\u2029": "PS"}


def compare_clips(left: dict, right: dict, max_chars: int) -> dict:
    a, b = left["text"].splitlines(keepends=True), right["text"].splitlines(keepends=True)
    rows = []
    summary = {"equal": 0, "removed": 0, "added": 0, "replacement_blocks": 0}

    def append(tag, line, a_number=None, b_number=None):
        ending = next((end for end in ENDINGS if line.endswith(end)), "")
        rows.append({"tag": tag, "a": a_number, "b": b_number,
                     "text": line[:-len(ending)] if ending else line,
                     "ending": ENDINGS.get(ending, "none")})

    for tag, i, j, k, l in SequenceMatcher(a=a, b=b).get_opcodes():
        if tag == "equal":
            summary["equal"] += j-i
            for offset, line in enumerate(a[i:j]):
                append("equal", line, i+offset+1, k+offset+1)
        else:
            if tag == "replace":
                summary["replacement_blocks"] += 1
            summary["removed"] += j-i
            summary["added"] += l-k
            for offset, line in enumerate(a[i:j]):
                append("delete", line, i+offset+1)
            for offset, line in enumerate(b[k:l]):
                append("insert", line, b_number=k+offset+1)

    def metadata(clip):
        return {**{key: value for key, value in clip.items() if key != "text"}, "chars_read": len(clip["text"]),
                "has_text": bool(clip["text"])}

    return {"left": metadata(left), "right": metadata(right), "max_chars_per_clip": max_chars,
            "text_scope": "extracts" if left["truncated"] or right["truncated"] else "full_saved_text",
            "identical_read_text": left["text"] == right["text"], "summary": summary,
            "total_rows": len(rows), "rows": rows}
