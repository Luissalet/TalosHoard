"""Screen/activity observation -> a reusable procedure DRAFT, by plain rules.

Input is a log of events Talos already captures (foreground app and window, clipboard clips, screenshots, recent files) or
any log a caller supplies in the same shape (also clicks and typed text when some other recorder has them). The log is
segmented into steps (app switches, form fills, copy/paste between apps, clicks, files), each step keeps the events and the
screenshot that are its evidence, the values typed or pasted become named inputs (secret-looking values are masked
everywhere in the output), copied-and-pasted values and files become outputs, and everything the log cannot say is listed
as an explicit unknown: the intent, states never observed, clicks without a target, gaps, a paste that was never seen.

The result is a draft for a person or an agent to verify. Nothing here executes anything on the captured computer: the module
only reads a list of events and returns data.

Event shape (all keys optional except a time and a type; aliases are accepted):
``{"ts": 1700000000.5 | "2026-10-02T10:00:01", "type": "focus|click|type|copy|paste|clipboard|screenshot|file|submit",
"app": "Excel", "title": "Budget.xlsx", "text": "typed or pasted value", "field": "Email", "target": "Save button", "x": 10, "y": 20,
"ref": "frame 88", "input_type": "password", "source_app": "Excel"}``
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from datetime import datetime
from typing import Any, Iterable

SCHEMA = "talos.procedure_draft/1"
GAP_S = 60.0  # silence between two events that is reported as "not observed"
SCREENSHOT_WINDOW_S = 10.0
TYPE_RUN_GAP_S = 12.0
PASTE_AFTER_COPY_S = 15 * 60.0
MASK = "[masked]"

TYPE_ALIASES = {
    "focus": "focus", "app_switch": "focus", "window": "focus", "foreground": "focus", "switch": "focus", "span": "focus", "activate": "focus",
    "click": "click", "tap": "click", "press": "click", "mouse": "click", "double_click": "click", "right_click": "click",
    "type": "type", "typing": "type", "input": "type", "text": "type", "key": "type", "keys": "type", "keystrokes": "type", "fill": "type", "enter": "type",
    "copy": "copy", "cut": "copy", "clipboard_copy": "copy",
    "paste": "paste", "clipboard_paste": "paste",
    "clipboard": "clipboard", "clip": "clipboard",
    "screenshot": "screenshot", "frame": "screenshot", "capture": "screenshot", "snap": "screenshot", "screen": "screenshot",
    "file": "file", "save": "file", "open_file": "file", "download": "file", "recent_file": "file",
    "submit": "submit", "send": "submit",
}

# ------------------------------------------------------------------------------------------------ texts (es / en)
T = {
    "es": {
        "title": "Procedimiento propuesto", "switch": "Cambiar a {app}", "fill": "Rellenar {n} campo(s) en {app}: {fields}", "type": "Escribir texto en {app}",
        "transfer": "Pegar en {app} lo copiado en {src} (paso {n})", "copy": "Copiar contenido en {app}", "paste": "Pegar contenido en {app}", "click": "Pulsar «{target}» en {app}",
        "click_unknown": "Hacer clic en {app} (elemento no identificado{pos})", "file": "Archivo {name}", "observe": "Ver {app}: «{title}»", "submit": "Enviar o confirmar en {app}",
        "intent": "No se ve el objetivo del procedimiento: solo qué se hizo, no para qué.",
        "single_run": "Solo se observó una ejecución: las ramas, condiciones y variaciones no se ven.",
        "no_input": "El registro no tiene clics ni pulsaciones: solo ventana en primer plano, portapapeles y capturas. Las acciones dentro de cada ventana son desconocidas.",
        "target": "Paso {n}: el clic no identifica el elemento pulsado (solo posición).",
        "no_shot": "Paso {n}: no hay captura de pantalla como evidencia.",
        "no_shots": "El registro no contiene ninguna captura de pantalla: ningún paso tiene evidencia visual.",
        "paste_missing": "Paso {n}: se copió contenido y no se vio dónde se pegó.",
        "copy_missing": "Paso {n}: se pegó contenido y no se vio de dónde se copió.",
        "gap": "Hueco de {s} s sin eventos antes del paso {n}: estado desconocido.",
        "final_state": "Paso {n}: el estado posterior al último paso (resultado, confirmación) no se observó.",
        "secret": "Paso {n}: un valor con aspecto de secreto se enmascaró ({reason}); el procedimiento no lo conoce.",
        "empty": "No hay eventos en el registro: no se puede proponer ningún paso.",
        "verify": "Borrador para que una persona o un agente lo verifique. Talos no ejecuta nada en el ordenador observado.",
        "out_copy": "Contenido copiado en el paso {a} y pegado en el paso {b}", "out_file": "Archivo {name}", "out_last": "Estado final visible: {app} «{title}»",
        "param_note": "Valor de ejemplo del registro; sustitúyelo por el valor real al repetir el procedimiento.",
    },
    "en": {
        "title": "Proposed procedure", "switch": "Switch to {app}", "fill": "Fill in {n} field(s) in {app}: {fields}", "type": "Type text in {app}",
        "transfer": "Paste into {app} what was copied in {src} (step {n})", "copy": "Copy content in {app}", "paste": "Paste content in {app}", "click": "Click \"{target}\" in {app}",
        "click_unknown": "Click in {app} (element not identified{pos})", "file": "File {name}", "observe": "Look at {app}: \"{title}\"", "submit": "Submit or confirm in {app}",
        "intent": "The goal of the procedure is not visible: only what was done, not why.",
        "single_run": "Only one run was observed: branches, conditions and variations are not visible.",
        "no_input": "The log has no clicks or keystrokes: only the foreground window, the clipboard and screenshots. Actions inside each window are unknown.",
        "target": "Step {n}: the click does not identify the element pressed (position only).",
        "no_shot": "Step {n}: no screenshot as evidence.",
        "no_shots": "The log contains no screenshot at all: no step has visual evidence.",
        "paste_missing": "Step {n}: content was copied and where it was pasted was not seen.",
        "copy_missing": "Step {n}: content was pasted and where it was copied from was not seen.",
        "gap": "Gap of {s} s with no events before step {n}: state unknown.",
        "final_state": "Step {n}: the state after the last step (result, confirmation) was not observed.",
        "secret": "Step {n}: a secret-looking value was masked ({reason}); the procedure does not know it.",
        "empty": "The log has no events: no step can be proposed.",
        "verify": "Draft for a person or an agent to verify. Talos executes nothing on the observed computer.",
        "out_copy": "Content copied in step {a} and pasted in step {b}", "out_file": "File {name}", "out_last": "Visible final state: {app} \"{title}\"",
        "param_note": "Example value from the log; replace it with the real value when repeating the procedure.",
    },
}

# ------------------------------------------------------------------------------------------------ secrets
_SECRET_LABEL = re.compile(r"(?:pass(?:word|wd|phrase)?|contrase|clave|secret|token|api[\s_-]?key|apikey|pin\b|otp|cvv|cvc|2fa|codigo de (?:verificacion|seguridad)|credential|private key|clave privada|seed|semilla|iban|tarjeta|card number|numero de tarjeta)", re.IGNORECASE)
_SECRET_PREFIX = re.compile(r"(?:\bsk-[A-Za-z0-9_-]{16,}|\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}|\bxox[abprs]-[A-Za-z0-9-]{10,}|\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_-]{30,}|"
                            r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~+/=-]{16,})")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,4})?\b")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_URLISH = re.compile(r"^(?:https?://|www\.)\S+$", re.IGNORECASE)
_PATHISH = re.compile(r"^(?:[A-Za-z]:[\\/]|/|\\\\|~/)")
_DATEISH = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}$")


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        n = int(ch)
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        alt = not alt
    return total % 10 == 0


def _entropy(text: str) -> float:
    if not text:
        return 0.0
    counts = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    return -sum(c / len(text) * math.log2(c / len(text)) for c in counts.values())


def secret_reason(value: str, label: str = "", input_type: str = "") -> str:
    """Why a value looks like a secret ("" when it does not). Deliberately eager: a false mask costs a re-type, a leak costs more."""
    text = str(value or "").strip()
    if not text:
        return ""
    if str(input_type).lower() in ("password", "secret", "hidden"):
        return "password field"
    if label and _SECRET_LABEL.search(_plain(label)):
        return f"field «{label}»"
    if _SECRET_PREFIX.search(text):
        return "known token format"
    digits = re.sub(r"[ -]", "", text)
    if digits.isdigit() and 13 <= len(digits) <= 19 and _luhn(digits):
        return "card number"
    if _IBAN.search(text.upper()) and sum(c.isdigit() for c in text) >= 10:
        return "bank account number"
    if " " not in text and not _EMAIL.match(text) and not _URLISH.match(text) and not _PATHISH.match(text) and not _DATEISH.match(text):
        classes = sum(bool(re.search(p, text)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
        if len(text) >= 20 and _entropy(text) >= 3.4 and re.search(r"\d", text) and re.search(r"[A-Za-z]", text):
            return "long random string"
        if 8 <= len(text) <= 64 and classes >= 3 and re.search(r"\d", text) and re.search(r"[A-Za-z]", text) and not text.isidentifier():
            return "password-like string"
    return ""


def mask_text(text: str) -> tuple[str, list[str]]:
    """Mask secret-looking tokens inside free text (titles, pasted paragraphs). Returns the text and the reasons found."""
    reasons: list[str] = []
    out = str(text or "")

    def sub_prefix(m):
        reasons.append("known token format")
        return MASK
    out = _SECRET_PREFIX.sub(sub_prefix, out)
    pieces = []
    for token in re.split(r"(\s+)", out):
        if token.strip() and token != MASK:
            reason = secret_reason(token.strip(".,;:()[]{}\"'"))
            if reason and reason != "password field":
                reasons.append(reason)
                token = MASK
        pieces.append(token)
    return "".join(pieces), reasons


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(text)) if unicodedata.category(c) != "Mn").lower()


# ------------------------------------------------------------------------------------------------ normalising
def _epoch(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def normalize_events(events: Iterable[dict]) -> tuple[list[dict], list[dict]]:
    """-> (events sorted by time with canonical keys, rejected events with the reason). Never raises for a malformed event."""
    good, bad = [], []
    for index, raw in enumerate(events or []):
        if not isinstance(raw, dict):
            bad.append({"index": index, "reason": "not an object"})
            continue
        ts = _epoch(raw.get("ts", raw.get("time", raw.get("t"))))
        kind = TYPE_ALIASES.get(_plain(str(raw.get("type") or raw.get("kind") or raw.get("event") or "")).replace("-", "_").replace(" ", "_"))
        if ts is None:
            bad.append({"index": index, "reason": "no usable time"})
            continue
        if kind is None:
            bad.append({"index": index, "reason": f"unknown type {raw.get('type') or raw.get('kind')!r}"})
            continue
        text = raw.get("text", raw.get("value"))
        good.append({
            "index": index, "ts": ts, "type": kind, "app": str(raw.get("app") or "").strip(), "title": str(raw.get("title") or raw.get("window_title") or "").strip(),
            "text": None if text is None else str(text), "field": str(raw.get("field") or raw.get("label") or "").strip(), "target": str(raw.get("target") or "").strip(),
            "x": raw.get("x") if isinstance(raw.get("x"), (int, float)) else None, "y": raw.get("y") if isinstance(raw.get("y"), (int, float)) else None,
            "ref": "" if raw.get("ref", raw.get("id")) is None else str(raw.get("ref", raw.get("id"))), "input_type": str(raw.get("input_type") or ""),
            "source_app": str(raw.get("source_app") or "").strip(), "source": str(raw.get("source") or ""),
        })
    good.sort(key=lambda e: (e["ts"], e["index"]))
    return good, bad


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def _kind_of(value: str) -> str:
    v = value.strip()
    if _EMAIL.match(v):
        return "email"
    if _URLISH.match(v):
        return "url"
    if _DATEISH.match(v) or re.match(r"^\d{4}-\d{2}-\d{2}", v):
        return "date"
    if re.match(r"^[+(]?\d[\d\s().-]{6,}$", v) and sum(c.isdigit() for c in v) >= 7:
        return "phone" if re.match(r"^[+(]", v) or len(re.sub(r"\D", "", v)) in (9, 10, 11) else "number"
    if re.match(r"^[-+]?\d+(?:[.,]\d+)?\s*(?:€|eur|\$|usd|%)?$", v, re.IGNORECASE):
        return "number"
    return "text"


def _slug(label: str, fallback: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", _plain(label)).strip("_")
    return s[:32] or fallback


# ------------------------------------------------------------------------------------------------ building the draft
class _Builder:
    def __init__(self, events: list[dict], locale: str):
        self.t = T.get(locale, T["es"])
        self.locale = locale if locale in T else "es"
        self.events = events
        self.steps: list[dict] = []
        self.inputs: list[dict] = []
        self.outputs: list[dict] = []
        self.unknowns: list[dict] = []
        self.masked = 0
        self.names: set[str] = set()
        self.shots = [e for e in events if e["type"] == "screenshot"]
        self.origin = events[0]["ts"] if events else 0.0
        self.pending: list[dict] = []

    # --- helpers
    def unknown(self, code: str, text: str, step: int | None = None):
        self.unknowns.append({"code": code, "step": step, "message": text})

    def rel(self, ts: float) -> float:
        return round(ts - self.origin, 2)

    def private(self, value: str | None, label: str = "", input_type: str = "") -> tuple[str, bool, str]:
        """-> (text safe to show, masked, reason)."""
        if value is None:
            return "", False, ""
        reason = secret_reason(value, label, input_type)
        if reason:
            self.masked += 1
            return MASK, True, reason
        safe, reasons = mask_text(value)
        if reasons:
            self.masked += 1
            return safe, True, reasons[0]
        return value, False, ""

    def evidence(self, e: dict, summary: str = "") -> dict:
        title, _ = mask_text(e["title"]) if e["title"] else ("", [])
        return {"event": e["index"], "ts": _iso(e["ts"]), "t": self.rel(e["ts"]), "type": e["type"], "app": e["app"] or None, "title": title or None,
                "ref": e["ref"] or None, "note": summary or None}

    def shot_for(self, start: float, end: float) -> dict | None:
        """The screenshot closest in time to the step (within SCREENSHOT_WINDOW_S of it); one taken before wins a tie."""
        best = None
        for s in self.shots:
            gap = 0.0 if start <= s["ts"] <= end else (start - s["ts"] if s["ts"] < start else s["ts"] - end)
            if gap <= SCREENSHOT_WINDOW_S and (best is None or gap < best[0]):
                best = (gap, s)
        return None if best is None else {"ref": best[1]["ref"] or None, "ts": _iso(best[1]["ts"]), "t": self.rel(best[1]["ts"]), "app": best[1]["app"] or None,
                                          "title": mask_text(best[1]["title"])[0] if best[1]["title"] else None}

    def add_step(self, kind: str, title: str, evts: list[dict], app: str, window: str, extra: dict | None = None) -> dict:
        n = len(self.steps) + 1
        start, end = evts[0]["ts"], evts[-1]["ts"]
        shot = self.shot_for(start, end)
        step = {"n": n, "id": f"s{n}", "kind": kind, "title": title, "app": app or None, "window": mask_text(window)[0] if window else None,
                "at": _iso(start), "t_start": self.rel(start), "t_end": self.rel(end), "evidence": [self.evidence(e) for e in evts],
                "screenshot": shot, "inputs": [], "outputs": [], "unknowns": [], **(extra or {})}
        if shot is None and self.shots:
            self.unknown("no_screenshot", self.t["no_shot"].format(n=n), n)
            step["unknowns"].append("no_screenshot")
        self.steps.append(step)
        return step

    def add_input(self, step: dict, value: str, label: str, source: str, input_type: str = "") -> dict:
        shown, masked, reason = self.private(value, label, input_type)
        base = _slug(label, "input") if label else "input"
        name, i = base, 1
        while name in self.names:
            i += 1
            name = f"{base}_{i}"
        self.names.add(name)
        entry = {"name": name, "step": step["n"], "label": label or None, "source": source, "kind": "secret" if masked and reason in ("password field", "known token format") else (_kind_of(value) if not masked else "masked"),
                 "example": shown, "masked": masked, "note": self.t["param_note"] if not masked else None}
        if masked:
            entry["masked_reason"] = reason
            self.unknown("secret_masked", self.t["secret"].format(n=step["n"], reason=reason), step["n"])
            step["unknowns"].append("secret_masked")
        self.inputs.append(entry)
        step["inputs"].append(name)
        return entry

    # --- segmentation
    def run(self):
        events = self.events
        app = title = ""
        i = 0
        pending_copies = self.pending = []  # {step, event, app, text, used}
        last_ts = None
        while i < len(events):
            e = events[i]
            if last_ts is not None and e["ts"] - last_ts > GAP_S:
                self.unknown("gap", self.t["gap"].format(s=round(e["ts"] - last_ts), n=len(self.steps) + 1), len(self.steps) + 1)
            last_ts = e["ts"]
            t = e["type"]
            if t == "focus":
                if e["app"] and e["app"] != app:
                    self.add_step("app_switch", self.t["switch"].format(app=e["app"]), [e], e["app"], e["title"])
                    app = e["app"]
                title = e["title"] or title
                i += 1
                continue
            ctx_app = e["app"] or app
            ctx_title = e["title"] or title
            if t == "type":
                run, k = [e], i
                for j in range(i + 1, len(events)):
                    n = events[j]
                    if n["type"] == "screenshot":
                        continue
                    if n["type"] != "type" or n["ts"] - run[-1]["ts"] > TYPE_RUN_GAP_S or (n["app"] or ctx_app) != ctx_app:
                        break
                    run.append(n)
                    k = j
                self._type_run(run, ctx_app, ctx_title)
                last_ts = run[-1]["ts"]
                i = k + 1
                continue
            if t == "click":
                label = e["target"]
                if label:
                    self.add_step("click", self.t["click"].format(target=mask_text(label)[0], app=ctx_app or "?"), [e], ctx_app, ctx_title, {"target": mask_text(label)[0]})
                else:
                    pos = f", {e['x']:.0f},{e['y']:.0f}" if e["x"] is not None and e["y"] is not None else ""
                    step = self.add_step("click", self.t["click_unknown"].format(app=ctx_app or "?", pos=pos), [e], ctx_app, ctx_title, {"target": None})
                    self.unknown("target_not_identified", self.t["target"].format(n=step["n"]), step["n"])
                    step["unknowns"].append("target_not_identified")
            elif t == "submit":
                self.add_step("submit", self.t["submit"].format(app=ctx_app or "?"), [e], ctx_app, ctx_title)
            elif t in ("copy", "clipboard"):
                src = e["source_app"] or ctx_app
                step = self.add_step("copy", self.t["copy"].format(app=src or "?"), [e], src, ctx_title)
                pending_copies.append({"step": step, "event": e, "app": src, "text": e["text"], "used": False})
            elif t == "paste":
                self._paste(e, ctx_app, ctx_title, pending_copies)
            elif t == "file":
                name = (e["text"] or e["ref"] or e["title"] or "?").replace("\\", "/").rsplit("/", 1)[-1]
                shown = mask_text(name)[0]
                step = self.add_step("file", self.t["file"].format(name=shown), [e], ctx_app, ctx_title, {"path": mask_text(e["text"] or e["ref"] or "")[0] or None})
                self.outputs.append({"step": step["n"], "kind": "file", "description": self.t["out_file"].format(name=shown), "value": step["path"]})
                step["outputs"].append("file")
            i += 1
        self._finish(pending_copies)

    def _type_run(self, run: list[dict], app: str, title: str):
        fields = []
        for e in run:
            label = e["field"]
            if label and label not in fields:
                fields.append(label)
        if fields:
            names = ", ".join(mask_text(f)[0] for f in fields)
            step = self.add_step("fill_form", self.t["fill"].format(n=len(fields), app=app or "?", fields=names), run, app, title)
            for f in fields:
                chunk = [e for e in run if e["field"] == f]
                value = "".join(e["text"] or "" for e in chunk)
                self._typed_value(step, value, f, chunk)
            loose = [e for e in run if not e["field"]]
            if loose:
                self._typed_value(step, "".join(e["text"] or "" for e in loose), "", loose)
        else:
            step = self.add_step("type_text", self.t["type"].format(app=app or "?"), run, app, title)
            self._typed_value(step, "".join(e["text"] or "" for e in run), "", run)

    def _typed_value(self, step: dict, value: str, label: str, chunk: list[dict]):
        """A typed value that equals an earlier clipboard copy is that copy pasted (the paste itself is not recorded by Talos): say so."""
        input_type = next((e["input_type"] for e in chunk if e["input_type"]), "")
        copy = next((c for c in reversed(self.pending) if not c["used"] and c["text"] is not None and len(value.strip()) >= 3 and c["text"].strip() == value.strip()
                     and 0 <= chunk[0]["ts"] - c["event"]["ts"] <= PASTE_AFTER_COPY_S), None)
        if copy is None:
            self.add_input(step, value, label, "typed", input_type)
            return
        copy["used"] = True
        copy["step"]["transferred_in_step"] = step["n"]
        step.setdefault("from_steps", []).append(copy["step"]["n"])
        self.add_input(step, value, label, f"copied from {copy['app'] or '?'} (same text; the paste itself was not recorded)", input_type)
        shown, masked, _ = self.private(value, label, input_type)
        self.outputs.append({"step": step["n"], "kind": "transferred_value", "description": self.t["out_copy"].format(a=copy["step"]["n"], b=step["n"]), "value": shown, "masked": masked})

    def _paste(self, e: dict, app: str, title: str, pending: list[dict]):
        match = None
        for c in reversed(pending):
            if c["used"]:
                continue
            if e["text"] is not None and c["text"] is not None and e["text"].strip() != c["text"].strip():
                continue
            if e["ts"] - c["event"]["ts"] > PASTE_AFTER_COPY_S:
                continue
            match = c
            break
        if match is None:
            step = self.add_step("paste", self.t["paste"].format(app=app or "?"), [e], app, title)
            if e["text"] is not None:
                self.add_input(step, e["text"], e["field"], "pasted", e["input_type"])
            self.unknown("copy_not_observed", self.t["copy_missing"].format(n=step["n"]), step["n"])
            step["unknowns"].append("copy_not_observed")
            return
        match["used"] = True
        src_step = match["step"]
        step = self.add_step("copy_paste", self.t["transfer"].format(src=match["app"] or "?", app=app or "?", n=src_step["n"]), [e], app, title,
                             {"from_step": src_step["n"], "from_app": match["app"] or None, "copy_evidence": self.evidence(match["event"])})
        value = e["text"] if e["text"] is not None else match["text"]
        if value is not None:
            self.add_input(step, value, e["field"], f"copied from {match['app'] or '?'}", e["input_type"])
        shown, masked, _ = self.private(value) if value is not None else ("", False, "")
        self.outputs.append({"step": step["n"], "kind": "transferred_value", "description": self.t["out_copy"].format(a=src_step["n"], b=step["n"]),
                             "value": shown, "masked": masked})
        step["outputs"].append("transferred_value")
        src_step["transferred_in_step"] = step["n"]

    def _finish(self, pending: list[dict]):
        events = self.events
        for c in pending:
            if not c["used"]:
                s = c["step"]
                self.unknown("paste_not_observed", self.t["paste_missing"].format(n=s["n"]), s["n"])
                s["unknowns"].append("paste_not_observed")
        if not self.steps:
            for e in self.shots:
                self.add_step("observe", self.t["observe"].format(app=e["app"] or "?", title=mask_text(e["title"])[0]), [e], e["app"], e["title"])
        if not self.shots and self.steps:
            self.unknown("no_screenshots", self.t["no_shots"], None)
        if not any(e["type"] in ("click", "type", "paste", "submit") for e in events):
            self.unknown("no_input_events", self.t["no_input"], None)
        if self.steps:
            last = self.steps[-1]
            last_ev = self.events[-1]
            shown_after = any(s["ts"] > last_ev["ts"] for s in self.shots)
            if not shown_after:
                self.unknown("final_state_not_observed", self.t["final_state"].format(n=last["n"]), last["n"])
                last["unknowns"].append("final_state_not_observed")
            if last["app"]:
                self.outputs.append({"step": last["n"], "kind": "final_view", "description": self.t["out_last"].format(app=last["app"], title=last["window"] or ""), "value": None})
        self.unknown("intent_not_visible", self.t["intent"], None)
        self.unknown("single_run", self.t["single_run"], None)


def build_draft(events: Iterable[dict], *, locale: str = "es", title: str | None = None, sources: list[str] | None = None) -> dict:
    """Segment an event log into a procedure draft. Pure: the same events always give the same draft."""
    locale = locale if locale in T else "es"
    t = T[locale]
    clean, rejected = normalize_events(events)
    if not clean:
        return {"schema": SCHEMA, "draft": True, "status": "empty", "executes_nothing": True, "title": title or t["title"], "locale": locale, "steps": [], "inputs": [], "outputs": [],
                "unknowns": [{"code": "no_events", "step": None, "message": t["empty"]}], "rejected_events": rejected, "masked_values": 0, "verify": t["verify"],
                "window": {"events": 0, "sources": sources or []}}
    builder = _Builder(clean, locale)
    builder.run()
    start, end = clean[0]["ts"], clean[-1]["ts"]
    counts: dict[str, int] = {}
    for e in clean:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    # a stable digest of the draft's shape lets callers tell whether two observations produced the same procedure
    shape = hashlib.sha1("|".join(f"{s['kind']}:{s['app']}" for s in builder.steps).encode("utf-8")).hexdigest()[:10]
    return {"schema": SCHEMA, "draft": True, "status": "draft_needs_verification", "executes_nothing": True, "title": title or t["title"], "locale": locale,
            "window": {"start": _iso(start), "end": _iso(end), "duration_s": round(end - start, 1), "events": len(clean), "by_type": counts, "sources": sources or ["supplied"]},
            "steps": builder.steps, "inputs": builder.inputs, "outputs": builder.outputs, "unknowns": builder.unknowns, "rejected_events": rejected,
            "masked_values": builder.masked, "shape": shape, "verify": t["verify"]}


def render_markdown(draft: dict) -> str:
    """Plain text/Markdown for the draft: steps with evidence, inputs (masked), outputs and unknowns."""
    es = draft.get("locale", "es") == "es"
    H = {"steps": "Pasos" if es else "Steps", "inputs": "Entradas" if es else "Inputs", "outputs": "Salidas" if es else "Outputs", "unknowns": "Lo que no se sabe" if es else "Unknowns",
         "evidence": "evidencia" if es else "evidence", "shot": "captura" if es else "screenshot", "noshot": "sin captura" if es else "no screenshot", "none": "Nada." if es else "None."}
    lines = [f"# {draft['title']}", "", f"> {draft['verify']}", ""]
    w = draft.get("window", {})
    if w.get("start"):
        lines += [f"- {w['start']} - {w['end']} ({w['duration_s']} s, {w['events']} " + ("eventos" if es else "events") + ")", ""]
    lines += [f"## {H['steps']}", ""]
    for s in draft["steps"]:
        shot = s.get("screenshot")
        lines.append(f"{s['n']}. **{s['title']}** (`{s['t_start']}s`)")
        lines.append(f"   - {H['evidence']}: " + ", ".join(f"{e['type']}@{e['t']}s" for e in s["evidence"]) + (f"; {H['shot']}: {shot['ref'] or shot['ts']}" if shot else f"; {H['noshot']}"))
        if s["inputs"]:
            lines.append("   - " + H["inputs"].lower() + ": " + ", ".join(s["inputs"]))
    if not draft["steps"]:
        lines.append(H["none"])
    lines += ["", f"## {H['inputs']}", ""]
    lines += [f"- `{i['name']}` ({i['source']}, {i['kind']}): {i['example'] or '-'}" for i in draft["inputs"]] or [H["none"]]
    lines += ["", f"## {H['outputs']}", ""]
    lines += [f"- {o['description']}" + (f": {o['value']}" if o.get("value") else "") for o in draft["outputs"]] or [H["none"]]
    lines += ["", f"## {H['unknowns']}", ""]
    lines += [f"- {u['message']}" for u in draft["unknowns"]] or [H["none"]]
    return "\n".join(lines).rstrip() + "\n"
