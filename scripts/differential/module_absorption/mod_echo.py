"""Portapapeles (Echo): the original app against Talos's `clipboard` module.

The base data is built by the ORIGINAL code: clips of every kind (text, url, email, path, code, number, image), hidden ones (token,
password), duplicates, a pinned and tagged clip, a soft-deleted clip and three recent clips; then the call sequence replays on both sides
with the fake clipboard backend (nothing touches the real clipboard).
"""
import io
import time
from pathlib import Path

TALOS_ID = "clipboard"
OLD_PKG = "echo"
ENV = {"ECHO_BACKEND": "fake", "ECHO_RETENTION_DAYS": "36500", "ECHO_EXCLUDE_APPS": "keepass", "PYTHONUTF8": "1"}
VOLATILE_KEYS = {"started_at", "janitor_last_run"}
# Optional arguments Talos added on purpose to tools the original already had.
ADDITIVE_ARGUMENTS: dict = {"clip_recent": ["app"]}


def at(day, hhmm):
    import datetime as dt
    return dt.datetime.fromisoformat(f"{day}T{hhmm}:00").timestamp()


def build_fixtures(out: Path):
    (out / "placeholder.txt").write_text("nothing to import in this app\n", encoding="utf-8")


LONG = "\n".join(f"Línea {n:03d}: " + "contenido del portapapeles " * 4 for n in range(1, 61))
CODE = "def total(lines):\n    return sum(l.amount for l in lines)\n\nprint(total([]));\n"


def build_base(out: Path, fixtures: Path):
    from PIL import Image
    from echo.config import Config
    from echo.services import Services
    from echo.backends.fake import FakeBackend
    cfg = Config(data_dir=out, backend="fake", autostart=False, retention_days=36500, data_dir_configured=True)
    svc = Services(cfg, backend=FakeBackend())
    try:
        c = svc.clips
        d1, d2 = "2026-09-20", "2026-09-22"
        c.capture_text("Reunión con el equipo de producto el jueves a las 10:00", source_app="teams", source_title="Chat de producto", now=at(d1, "09:00"))   # 1
        c.capture_text("https://example.com/docs/facturacion", source_app="chrome", source_title="Documentación - Docs", now=at(d1, "09:10"))             # 2
        c.capture_text("lucia.mario@example.com", source_app="outlook", source_title="Bandeja de entrada", now=at(d1, "09:20"))                           # 3
        c.capture_text("C:\\Proyectos\\Atlas\\informe.xlsx", source_app="explorer", source_title="Atlas", now=at(d1, "09:30"))                           # 4
        c.capture_text(CODE, source_app="code", source_title="report.py - Atlas", now=at(d1, "10:00"))                                                   # 5
        c.capture_text("12.480,50 €", source_app="excel", source_title="Facturas.xlsx", now=at(d1, "10:30"))                                            # 6
        c.capture_text("sk-test-1234567890abcdef", source_app="chrome", source_title="Panel de claves", now=at(d1, "11:00"))                            # 7 hidden token
        c.capture_text(LONG, source_app="word", source_title="Informe largo.docx", now=at(d1, "11:30"))                                                  # 8
        c.capture_text("https://example.com/pricing", source_app="chrome", source_title="Precios - Example", now=at(d2, "08:00"))                        # 9
        c.capture_text("Reunión con el equipo de producto el viernes a las 11:00", source_app="teams", source_title="Chat de producto", now=at(d2, "08:30"))  # 10
        buf = io.BytesIO()
        Image.new("RGB", (200, 100), (30, 90, 160)).save(buf, "PNG")
        c.capture_image(buf.getvalue(), width=200, height=100, source_app="snip", source_title="Recorte", now=at(d2, "09:00"))                          # 11
        c.capture_text("Tr0ub4dor&3xyz!QQ", source_app="notas", source_title="Notas", now=at(d2, "09:30"))                                               # 12 hidden password
        c.capture_text("Reunión con el equipo de producto el jueves a las 10:00", source_app="notas", source_title="Notas", now=at(d2, "10:00"))        # bumps 1
        c.capture_text("texto para borrar", source_app="notas", source_title="Notas", now=at(d2, "10:10"))                                              # 13
        c.soft_delete(13, at(d2, "10:20"))
        now = time.time()
        c.capture_text("marcador reciente alfa", source_app="notas", source_title="Notas", now=now - 300)                                                # 14
        c.capture_text("https://example.com/reciente", source_app="chrome", source_title="Reciente", now=now - 1800)                                    # 15
        c.capture_text("marcador reciente beta con varias palabras", source_app="code", source_title="Notas", now=now - 7200)                            # 16
        c.update(2, {"pinned": True, "label": "Docs facturación", "tags": ["docs", "Factura", "docs"]})
        c.update(5, {"pinned": True})
    finally:
        svc.stop()


TOOLS = ["clip_recent", "clip_search", "clip_get", "clip_bundle", "clip_set", "clip_copy", "clip_pin", "clip_delete", "clip_status", "clip_capture"]


def cases():
    c = [{"tool": "tools", "list_tools": TOOLS, "additive": ADDITIVE_ARGUMENTS}]

    def add(tool, args=None, **kw):
        c.append({"tool": tool, "args": args or {}, **kw})
    add("clip_status")
    # --- recent ---
    for args in ({}, {"n": 3}, {"n": 1}, {"n": 200}, {"n": 0}, {"n": 201}, {"kind": "url"}, {"kind": "email"}, {"kind": "path"}, {"kind": "code"}, {"kind": "number"},
                 {"kind": "image"}, {"kind": "text", "n": 4}, {"kind": "video"}, {"since": "1h"}, {"since": "30m"}, {"since": "hace 3 horas"}, {"since": "hoy"},
                 {"since": "última hora"}, {"since": "ayer"}, {"since": "2026-09-22"}, {"since": "no-es-un-tiempo"}, {"since": 1790000000}, {"since": "1h", "kind": "url"}):
        add("clip_recent", args)
    # --- search ---
    for args in ({"q": "reunión"}, {"q": "reunion producto"}, {"q": "facturacion"}, {"q": "docs"}, {"q": "Factura"}, {"q": "example"}, {"q": "marcador reciente"},
                 {"q": "marcador", "since": "1h"}, {"q": "reunión", "app": "teams"}, {"q": "reunión", "app": "notas"}, {"q": "reunión", "kind": "text"},
                 {"q": "informe", "limit": 1}, {"q": "def total"}, {"q": "sk-test"}, {"q": "oculto"}, {"q": "Tr0ub4dor"}, {"q": "contenido portapapeles", "limit": 3},
                 {"q": "zzzz-no-existe"}, {"q": "AND OR NEAR \"quote"}, {"q": ""}, {}, {"q": "x", "limit": 0}, {"q": "x", "kind": "otro"}, {"q": "recorte"}, {"q": "imagen"}):
        add("clip_search", args)
    # --- get ---
    for args in ({"id": 1}, {"id": 2}, {"id": 5}, {"id": 8}, {"id": 8, "max_chars": 100}, {"id": 8, "max_chars": 100, "offset": 100}, {"id": 8, "offset": 99999},
                 {"id": 8, "max_chars": 50000}, {"id": 11}, {"id": 7}, {"id": 12}, {"id": 13}, {"id": 999}, {"id": 0}, {}, {"id": 1, "max_chars": 0}):
        add("clip_get", args)
    # --- bundle ---
    for args in ({"ids": [1, 10]}, {"ids": [10, 1, 2]}, {"ids": [8], "max_chars_per_clip": 120}, {"ids": [1, 1]}, {"ids": [1, 999]}, {"ids": [1, 7]}, {"ids": [11, 5]},
                 {"ids": []}, {"ids": list(range(1, 22))}, {"ids": [13]}, {}):
        add("clip_bundle", args)
    # --- set / copy (the fake backend records the write; nothing reaches the real clipboard) ---
    add("clip_set", {"text": "texto puesto por el asistente"}); add("clip_set", {"text": "texto puesto por el asistente"}); add("clip_set", {"text": "https://example.com/puesto"})
    add("clip_set", {"text": "sk-puesto-0987654321zyx"}); add("clip_set", {"text": ""}); add("clip_set", {})
    add("clip_recent", {"n": 5}); add("clip_search", {"q": "puesto"})
    add("clip_copy", {"id": 1}); add("clip_copy", {"id": 7}); add("clip_copy", {"id": 7, "allow_sensitive": True}); add("clip_copy", {"id": 12, "allow_sensitive": True})
    add("clip_copy", {"id": 11}); add("clip_copy", {"id": 13}); add("clip_copy", {"id": 999}); add("clip_copy", {})
    add("clip_recent", {"n": 4})
    # --- pin / label / tags ---
    for args in ({"id": 3, "pinned": True}, {"id": 3, "pinned": True, "label": "Contacto de Lucía", "tags": ["Persona", "persona", " correo "]}, {"id": 3, "pinned": False},
                 {"id": 3, "pinned": False, "tags": []}, {"id": 999, "pinned": True}, {"id": 3}, {"pinned": True}, {"id": 1, "pinned": True, "tags": ["x"] * 31},
                 {"id": 7, "pinned": True, "label": "token"}, {"id": 4, "pinned": True, "label": "x" * 301}):
        add("clip_pin", args)
    add("clip_search", {"q": "persona"}); add("clip_search", {"q": "Lucía"}); add("clip_recent", {"n": 20})
    # --- delete ---
    add("clip_delete", {"id": 9}); add("clip_delete", {"id": 9}); add("clip_delete", {"id": 999}); add("clip_delete", {}); add("clip_get", {"id": 9}); add("clip_search", {"q": "pricing"})
    add("clip_recent", {"n": 30})
    # --- capture switch ---
    add("clip_capture", {"action": "pause"}); add("clip_status"); add("clip_capture", {"action": "pause"}); add("clip_capture", {"action": "resume"}); add("clip_status")
    add("clip_capture", {"action": "stop"}); add("clip_capture", {})
    add("clip_status")
    add("no_such_tool", {}, loose=True)
    return c


def mutate():
    """A deliberate regression in Talos's copy: the length of every clip is off by one."""
    import echo.store as store
    original = store.ClipStore.get

    def get(self, clip_id, include_deleted=False):
        clip = original(self, clip_id, include_deleted)
        return {**clip, "chars": clip["chars"] + 1} if clip else clip
    store.ClipStore.get = get
