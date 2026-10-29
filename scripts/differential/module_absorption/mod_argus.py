"""Pantalla (Argus): the original app against Talos's `screen` module.

The base data is built by the ORIGINAL code: frames (rendered screens) with fixed capture times, OCR results written the way the OCR
worker writes them, a pinned frame, hidden ticks, an exclusion rule and the settings; then the call sequence replays on both sides.
"""
import datetime as dt
import time
from pathlib import Path

TALOS_ID = "screen"
OLD_PKG = "argus"
ENV = {"ARGUS_CAPTURE": "fake", "ARGUS_WINDOW": "fake", "ARGUS_VISUAL": "none", "ARGUS_AUTOSTART": "0", "PYTHONUTF8": "1"}
VOLATILE_KEYS = {"ocr_ms", "queue_depth", "disk_free_bytes", "ocr_processed", "ocr_last_ms", "janitor_last_run", "uptime_s"}
# Talos reports "ocr_notes" with the engine it picked; the original does the same, and both run on the same machine.
ADDITIVE_ARGUMENTS: dict = {}


def at(day, hhmm):
    """A local wall-clock time as epoch seconds (the days are fixed, so the base never depends on the date it is built)."""
    return dt.datetime.fromisoformat(f"{day}T{hhmm}:00").timestamp()


def build_fixtures(out: Path):
    from argus.capture.fixtures import render_screen
    render_screen(["Informe trimestral", "Total facturado: 12.480 EUR", "Cliente: Hoard Studio SL"], (640, 360), "informe.pdf - Lector").save(out / "informe.png")
    render_screen(["Error de conexion", "No se pudo abrir el puerto 5183"], (640, 360), "Terminal").save(out / "error.png")
    (out / "notas.txt").write_text("not an image\n", encoding="utf-8")


SCENES = [
    # day, time, count, monitor, app, title, ocr lines
    ("2026-09-22", "09:00", 6, 1, "code", "main.py - Atlas - Visual Studio Code", ["def build_report(invoice):", "total = sum(line.amount for line in invoice.lines)", "return render(total)"]),
    ("2026-09-22", "09:30", 4, 1, "chrome", "Pull request #42 - GitHub", ["Pull request merge conflict resolved", "Reviewers: Lucía Mario", "Facturación mensual"]),
    ("2026-09-22", "11:00", 3, 2, "slack", "Equipo producto - Slack", ["Reunión de producto a las doce", "Lucía: la exportación a PDF ya está"]),
    ("2026-09-22", "15:00", 5, 1, "code", "report.py - Atlas - Visual Studio Code", ["def export_pdf(report):", "raise ValueError('export failed')", "traceback error line 42"]),
    ("2026-09-23", "10:00", 5, 1, "code", "report.py - Atlas - Visual Studio Code", ["def export_pdf(report):", "return pdf.render(report)", "tests passed"]),
    ("2026-09-23", "10:30", 3, 1, "chrome", "Documentación de facturación - Docs", ["Cómo configurar la facturación electrónica", "Paso uno: crear la cuenta del cliente"]),
    ("2026-09-23", "16:00", 4, 1, "explorer", "Descargas", ["presupuesto-2026.xlsx", "contrato-alquiler.pdf", "foto-equipo.jpg"]),
    ("2026-09-24", "08:45", 4, 2, "terminal", "PowerShell - Atlas", ["PS C:\\Atlas> pytest -q", "154 passed in 12.31s"]),
]


def build_base(out: Path, fixtures: Path):
    from PIL import Image
    from argus.capture.fixtures import render_screen
    from argus.config import Config
    from argus.services import Services
    from argus.store import Block
    cfg = Config(data_dir=out, capture_backend="none", window_backend="none", autostart=False, data_dir_configured=True, visual_backend="none")
    svc = Services(cfg)
    try:
        svc.settings.update({"retention_days": 0})   # keep forever: the fixed days are older than the default retention
        counter = 0
        for day, hhmm, count, monitor, app, title, lines in SCENES:
            image = render_screen(lines, (640, 360), title)
            for i in range(count):
                counter += 1
                when = at(day, hhmm) + i * 60
                fid = svc.frames.insert_frame(image, captured_at=when, interval_s=60, monitor=monitor, app=app, window_title=title, phash=f"{counter:016x}")
                blocks = [Block(text=line, x=48, y=96 + 40 * n, w=400, h=30, conf=0.9 - 0.01 * n) for n, line in enumerate(lines)]
                svc.frames.set_ocr_result(fid, blocks, "\n".join(lines), 120 + counter, "fixture")
                svc.frames.record_tick(when, False)
        for k in range(3):
            svc.frames.record_tick(at("2026-09-22", "09:00") + k, True)
        # two frames from the last hour, so the "what was I just looking at" tools have something to return
        now = time.time()
        for n, (age, title, lines) in enumerate([(25 * 60, "recent.py - Atlas - Visual Studio Code", ["def recent_marker():", "pass"]), (12 * 60, "Navegador - Docs", ["Documentación reciente de Atlas", "marcador reciente"])]):
            fid = svc.frames.insert_frame(render_screen(lines, (640, 360), title), captured_at=now - age, interval_s=60, monitor=1, app="code" if n == 0 else "chrome",
                                          window_title=title, phash=f"{900 + n:016x}")
            svc.frames.set_ocr_result(fid, [Block(text=l, x=48, y=96 + 40 * i, w=400, h=30, conf=0.9) for i, l in enumerate(lines)], "\n".join(lines), 99, "fixture")
        svc.frames.set_pinned(3, True)
        svc.exclusions.add("app", "keepass")
    finally:
        svc.stop()


def install_fake_ocr():
    """Both sides get the same stand-in for the OCR engine: the real ones load a neural model and are slow and machine dependent. The
    worker, the queue, the statuses and the full-text index stay the real ones; only the recognition is replaced by a digest of the image."""
    import hashlib
    import argus.worker as worker
    from argus.ocr.base import OcrBackend, OcrResult
    from argus.store import Block

    class FixtureOcr(OcrBackend):
        name = "fixture-ocr"

        def recognise(self, image):
            digest = hashlib.sha1(image.convert("L").resize((16, 9)).tobytes()).hexdigest()[:8]
            lines = ["captura importada", f"huella {digest}", f"tamano {image.width}x{image.height}"]
            blocks = [Block(text=t, x=40, y=40 + 40 * n, w=300, h=30, conf=0.9) for n, t in enumerate(lines)]
            return OcrResult(blocks=blocks, text="\n".join(lines), backend=self.name)

    worker.select_ocr = lambda requested="auto", language="es", **kw: (FixtureOcr(), ["fixture OCR"])


def prepare_old():
    install_fake_ocr()


def prepare_talos():
    install_fake_ocr()


D1, D2, D3 = "2026-09-22", "2026-09-23", "2026-09-24"
A, B = D1 + "T00:00:00", D3 + "T23:59:00"
TOOLS = ["screen_status", "screen_search", "screen_similar", "screen_timeline", "screen_frame_text", "screen_pin_frame", "screen_recent", "screen_activity", "screen_days",
         "screen_pause", "screen_resume", "screen_delete_range", "screen_import", "screen_import_list", "screen_import_watch", "screen_import_watch_status"]


def cases():
    c = [{"tool": "tools", "list_tools": TOOLS, "additive": ADDITIVE_ARGUMENTS}]

    def add(tool, args=None, **kw):
        c.append({"tool": tool, "args": args or {}, **kw})
    add("screen_status")
    add("screen_days")
    # --- search ---
    for args in ({"q": "factura"}, {"q": "facturacion"}, {"q": "Facturación", "mode": "text"}, {"q": "export", "from": A, "to": B}, {"q": "traceback"},
                 {"q": "error", "app": "code"}, {"q": "pdf", "limit": 1}, {"q": "zzzz-no-existe"}, {"q": "report", "from": D2 + "T00:00:00", "to": D2 + "T23:59:00"},
                 {"q": "reunión producto"}, {"q": "pytest", "app": "terminal"}, {"q": "Atlas", "limit": 3}, {"q": "def", "from": "hace 2 horas"},
                 {"q": "a", "mode": "bad"}, {"q": ""}, {}):
        add("screen_search", args)
    add("screen_search", {"q": "gráfica azul", "mode": "visual"}); add("screen_search", {"q": "gráfica azul"})
    add("screen_similar", {"id": 1}); add("screen_similar", {"id": 99999}); add("screen_similar", {})
    # --- timeline ---
    for args in ({"from": A, "to": B}, {"from": A, "to": B, "limit": 3}, {"from": A, "to": B, "group": False, "limit": 5}, {"from": D2 + "T10:00:00", "to": D2 + "T11:00:00"},
                 {"from": A, "to": B, "app": "code"}, {"from": A, "to": B, "limit": 2, "cursor": at(D2, "10:03")}, {"from": B, "to": A}, {"from": "no-es-fecha"}, {"limit": 0}):
        add("screen_timeline", args)
    # --- frames ---
    for args in ({"id": 1}, {"id": 1, "blocks": True}, {"id": 20, "blocks": True}, {"id": 99999}, {"id": 0}, {}):
        add("screen_frame_text", args)
    # --- recent / activity ---
    add("screen_recent", {"minutes": 720}); add("screen_recent", {"minutes": 720, "limit": 1}); add("screen_recent", {"minutes": 1}); add("screen_recent", {"minutes": 0})
    for args in ({"from": A, "to": B}, {"from": D1 + "T00:00:00", "to": D1 + "T23:59:00"}, {"from": D2 + "T00:00:00", "to": D2 + "T23:59:00"}, {"from": B, "to": A}, {"from": "ayer-x"}):
        add("screen_activity", args)
    # --- pin ---
    add("screen_pin_frame", {"id": 5, "pinned": True}); add("screen_pin_frame", {"id": 5, "pinned": False}); add("screen_pin_frame", {"id": 99999, "pinned": True}); add("screen_pin_frame", {"id": 5})
    # --- import (real OCR of two rendered screens, on both sides the same engine) ---
    add("screen_import_list")
    add("screen_import", {"paths": ["<fix>/informe.png"], "captured_at": "2026-09-21T08:00:00", "app": "Archivo de prueba"}, sleep=8)
    add("screen_import", {"paths": ["<fix>/informe.png"], "captured_at": "2026-09-21T08:00:00"})
    add("screen_import", {"paths": ["<fix>"], "captured_at": "2026-09-21T09:00:00"}, sleep=8)
    add("screen_import", {"paths": ["<fix>/missing.png"]}); add("screen_import", {"paths": ["<fix>/notas.txt"]}); add("screen_import", {})
    add("screen_import_list"); add("screen_import_list", {"limit": 1})
    add("screen_search", {"q": "huella"}); add("screen_search", {"q": "importada", "limit": 1})
    # --- watched folders ---
    add("screen_import_watch_status")
    add("screen_import_watch", {"folders": ["<fix>"], "recursive": False}); add("screen_import_watch_status"); add("screen_import_watch", {"folders": []}); add("screen_import_watch_status")
    add("screen_import_watch", {"recursive": True}); add("screen_import_watch", {"folders": ["<fix>/does-not-exist"]})
    # --- pause / resume / delete ---
    add("screen_pause"); add("screen_status"); add("screen_resume"); add("screen_status")
    add("screen_delete_range", {"from": D3 + "T08:00:00", "to": D3 + "T09:00:00"})
    add("screen_delete_range", {"from": D3 + "T08:00:00", "to": D3 + "T09:00:00"})
    add("screen_delete_range", {"from": B, "to": A}); add("screen_delete_range", {"from": D1 + "T00:00:00"}); add("screen_delete_range", {})
    add("screen_days"); add("screen_timeline", {"from": A, "to": B, "limit": 50}); add("screen_search", {"q": "pytest"}); add("screen_frame_text", {"id": 38})
    add("screen_status")
    add("no_such_tool", {}, loose=True)
    return c


def mutate():
    """A deliberate regression in Talos's copy: the day list loses its first day."""
    import argus.queries as q
    original = q.Queries.days
    q.Queries.days = lambda self: original(self)[1:]
