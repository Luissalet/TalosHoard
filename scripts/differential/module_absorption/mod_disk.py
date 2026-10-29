"""Disco (DiskHoard): the original app against Talos's `disk` module.

The base data is a saved scan made by the ORIGINAL code (so Talos has to read an old-format snapshot); then the call sequence scans a
fresh copy of a fixture tree, reads it every way the tools allow, deletes with the permanent mode only inside that copy, splits it into
ZIPs, and lists a toy Ollama store. The trash is never used and the real Ollama is replaced by "not running".
"""
import json
import os
import threading
import time
from pathlib import Path

TALOS_ID = "disk"
OLD_PKG = "diskhoard"
ENV = {"PYTHONUTF8": "1", "DISKHOARD_DATA_DIR": "<data>"}
VOLATILE_KEYS = {"elapsed_s", "uptime_s", "age_h", "started", "finished", "scanned_at", "t", "seq", "rate", "speed", "eta_s", "elapsed"}
ADDITIVE_ARGUMENTS: dict = {}
ALIASES = [(r"\b[0-9a-f]{8,12}-[0-9a-f]{4,12}\b|\bzip-?[0-9a-f]{6,12}\b|\bjob[-_]?[0-9a-z]{4,12}\b", "job")]
SUBS = [(r"# Fecha: \d{4}-\d{2}-\d{2} \d{2}:\d{2}", "# Fecha: <date>")]   # the cleanup script is stamped with the minute it was written
DAY = 86400.0


def _write(path: Path, size: int, age_days: float = 0):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"\0" * size if size < 5_000_000 else b"")
        if size >= 5_000_000:
            fh.truncate(size)
    if age_days:
        stamp = time.time() - age_days * DAY
        os.utime(path, (stamp, stamp))


def build_fixtures(out: Path):
    tree = out / "tree"
    p = tree / "proyecto"
    _write(p / "node_modules" / "a" / "index.js", 300_000)
    _write(p / "node_modules" / "b" / "index.js", 200_000)
    _write(p / ".git" / "objects" / "pack" / "x.pack", 150_000)
    _write(p / "package.json", 50)
    _write(p / "dist" / "bundle.js", 120_000)
    _write(p / ".venv" / "pyvenv.cfg", 20)
    _write(p / ".venv" / "lib" / "site.py", 90_000)
    _write(p / "__pycache__" / "mod.cpython-313.pyc", 40_000)
    _write(tree / "videos" / "peli.mp4", 900_000, age_days=3000)
    _write(tree / "descargas" / "imagen.iso", 700_000)
    _write(tree / "descargas" / "notas.txt", 10)
    _write(tree / "descargas" / "copia-1.zip", 60_000)
    _write(tree / "descargas" / "foto.JPG", 30_000, age_days=400)
    _write(tree / "archivo_viejo" / "datos" / "dump.bin", 64 * 1024 * 1024, age_days=900)
    _write(tree / "archivo_viejo" / "leeme.md", 300, age_days=900)
    _write(tree / "grande.bin", 6 * 1024 * 1024)
    # a toy Ollama store: one complete model, one orphan blob, one abandoned partial download, one backup-looking folder
    import hashlib
    store = out / "ollama" / "models"
    (store / "blobs").mkdir(parents=True)
    (store / "manifests" / "registry.ollama.ai" / "library" / "tiny").mkdir(parents=True)

    def blob(data: bytes, age=40 * DAY):
        digest = hashlib.sha256(data).hexdigest()
        path = store / "blobs" / ("sha256-" + digest)
        path.write_bytes(data)
        stamp = time.time() - age
        os.utime(path, (stamp, stamp))
        return {"digest": "sha256:" + digest, "size": len(data)}
    cfg = {**blob(b'{"config":"tiny"}'), "mediaType": "application/vnd.docker.container.image.v1+json"}
    layer = {**blob(b"tiny-weights" * 500), "mediaType": "application/vnd.ollama.image.model"}
    manifest = store / "manifests" / "registry.ollama.ai" / "library" / "tiny" / "latest"
    manifest.write_text(json.dumps({"schemaVersion": 2, "mediaType": "application/vnd.docker.distribution.manifest.v2+json", "config": cfg, "layers": [layer]}), encoding="utf-8")
    stamp = time.time() - 40 * DAY
    os.utime(manifest, (stamp, stamp))
    blob(b"orphan-blob-content" * 400)
    partial = store / "blobs" / ("sha256-" + "0" * 64 + "-partial")
    partial.write_bytes(b"x" * 5000)
    os.utime(partial, (stamp, stamp))
    (out / "ollama" / "models.bak").mkdir(parents=True)
    (out / "ollama" / "models.bak" / "old.bin").write_bytes(b"old" * 100)


def build_base(out: Path, fixtures: Path):
    os.environ["DISKHOARD_DATA_DIR"] = str(out)
    from diskhoard import server as srv
    result = srv.api_scan(str(fixtures / "tree"))
    assert "error" not in result, result
    deadline = time.time() + 60
    while not (srv.ST.scanner.done and os.path.exists(srv.snapshot_path())) and time.time() < deadline:
        time.sleep(0.2)
    assert os.path.exists(srv.snapshot_path()), "the old code did not save its scan"
    time.sleep(0.5)


def prepare_old():
    _stub_ollama()


def prepare_talos():
    _stub_ollama()


def _stub_ollama():
    """The real Ollama of this PC is neither asked nor run: it is "not running" on both sides."""
    from diskhoard import ollama_backups as ob
    ob._cli_version = lambda: "0.40.2"
    ob._api_get = lambda path, timeout=1.5: None
    ob._list_processes = lambda: []


def run_old(pre, data, port):
    import runpy
    import sys
    sys.argv = ["diskhoard", "--no-browser", "--port", str(port)]
    runpy.run_module("diskhoard.__main__", run_name="__main__")


def grow_node(fix: Path, data: Path, saved: dict):
    with open(fix / "tree" / "proyecto" / "node_modules" / "a" / "index.js", "ab") as fh:
        fh.write(b"x" * 5000)


TOOLS = ["disk_drives", "disk_scan", "disk_status", "disk_dir", "disk_hotspots", "disk_junk", "disk_stale", "disk_top_files", "disk_types", "disk_find", "disk_explain",
         "disk_script", "disk_delete", "disk_rescan", "disk_ollama_backups", "disk_ollama_free", "disk_zip_plan", "disk_zip_split", "disk_zip_status", "disk_zip_cancel"]
T = "<fix>\\tree"
OLL = "<fix>\\ollama\\models"


def cases():
    c = [{"tool": "tools", "list_tools": TOOLS, "additive": ADDITIVE_ARGUMENTS}]

    def add(tool, args=None, **kw):
        c.append({"tool": tool, "args": args or {}, **kw})
    # --- the scan saved by the original code, read before any new scan ---
    add("disk_status"); add("disk_dir"); add("disk_top_files", {"limit": 3}); add("disk_hotspots", {"limit": 5}); add("disk_types", {"limit": 3})
    add("disk_drives", shape=True)
    # --- a fresh scan of the per-run copy ---
    add("disk_scan", {"path": T}, timeout=300)
    add("disk_scan", {"path": "<fix>\\no-existe"}); add("disk_scan", {})
    add("disk_status"); add("disk_dir"); add("disk_dir", {"limit": 2}); add("disk_dir", {"dirs_only": True}); add("disk_dir", {"path": T + "\\proyecto"})
    add("disk_dir", {"path": T + "\\proyecto/node_modules"}); add("disk_dir", {"path": T + "\\nada"}); add("disk_dir", {"limit": 0})
    for args in ({}, {"limit": 3}, {"limit": 0}):
        add("disk_hotspots", args)
    for args in ({"min_mb": 0}, {"min_mb": 0, "safety": "safe"}, {"min_mb": 0, "safety": "review"}, {"min_mb": 0, "safety": "danger"}, {"min_mb": 0, "category": "Compilaciones"},
                 {"min_mb": 0, "limit": 2}, {}, {"min_mb": 0, "safety": "otro"}):
        add("disk_junk", args)
    for args in ({}, {"months": 1, "min_gb": 0.05}, {"months": 24, "min_gb": 0.05}, {"months": 1, "min_gb": 0.05, "limit": 1}, {"months": 0}, {"min_gb": 0.01}):
        add("disk_stale", args)
    for args in ({}, {"limit": 4}, {"ext": ".iso"}, {"ext": "mp4"}, {"ext": "xyz"}):
        add("disk_top_files", args)
    for args in ({}, {"limit": 2}):
        add("disk_types", args)
    for args in ({"path": T}, {"path": T, "pattern": "*.iso"}, {"path": T, "pattern": "*.JS"}, {"path": T, "min_mb": 1}, {"path": T, "older_than_days": 365}, {"path": T, "pattern": "*.bin", "min_mb": 1},
                 {"path": T, "limit": 2}, {"path": T + "\\nada"}, {"path": T, "max_entries": 1000}, {"path": T, "max_entries": 10}, {}):
        add("disk_find", args)
    for p in (T + "\\proyecto/node_modules", T + "\\proyecto/.git", T + "\\proyecto/dist", T + "\\proyecto/.venv", T + "\\proyecto/package.json", T + "\\videos/peli.mp4", T + "\\descargas/imagen.iso",
              T + "\\nada", T, "C:\\Windows", "C:\\Windows\\System32", "C:\\Users", "C:\\"):
        add("disk_explain", {"path": p})
    add("disk_explain", {})
    # --- scripts (nothing is deleted) ---
    add("disk_script", {"paths": [T + "\\proyecto/node_modules", T + "\\proyecto/dist"]}); add("disk_script", {"paths": []}); add("disk_script", {"paths": [T + "\\proyecto/.git"]}); add("disk_script", {})
    # --- zip ---
    plan = {"path": T, "out_dir": "<fix>\\zips_out", "limit": "300kb", "margin": "1kb"}
    add("disk_zip_plan", plan); add("disk_zip_plan", {**plan, "list_files": True}); add("disk_zip_plan", {**plan, "sort": "size"}); add("disk_zip_plan", {**plan, "include": ["*.js"]})
    add("disk_zip_plan", {**plan, "exclude": ["*.bin"], "too_large": "fail"}); add("disk_zip_plan", {**plan, "limit": "100kb", "too_large": "split"}); add("disk_zip_plan", {**plan, "limit": "nada"})
    add("disk_zip_plan", {**plan, "compression": "deflated"}); add("disk_zip_plan", {"path": "<fix>\\no-existe"}); add("disk_zip_plan", {}); add("disk_zip_plan", {"path": "C:\\"})
    add("disk_zip_status"); add("disk_zip_cancel"); add("disk_zip_status", {"job": "nada"})
    add("disk_zip_split", {**plan, "exclude": ["*.bin", "*.mp4"], "limit": "400kb"}, timeout=300)
    add("disk_zip_status"); add("disk_zip_split", {**plan, "exclude": ["*.bin", "*.mp4"], "limit": "400kb"}); add("disk_zip_split", {**plan, "exclude": ["*.bin", "*.mp4"], "limit": "400kb", "overwrite": True}, timeout=300)
    add("disk_zip_split", {"path": "<fix>\\no-existe"}); add("disk_zip_split", {"path": "C:\\", "limit": "1mb"}); add("disk_zip_cancel", {"job": "nada"}); add("disk_zip_status", {"wait_s": 0})
    add("disk_find", {"path": "<fix>\\zips_out"})
    # --- Ollama (toy store; the real Ollama is replaced by "not running") ---
    for args in ({"models_dir": OLL}, {"models_dir": OLL, "safe_only": True}, {"models_dir": OLL, "kind": "orphan"}, {"models_dir": OLL, "limit": 1}, {"models_dir": "<fix>\\no-existe"}, {"models_dir": OLL, "kind": "otro"}):
        add("disk_ollama_backups", args)
    add("disk_ollama_free", {"models_dir": OLL}); add("disk_ollama_free", {"models_dir": OLL, "dry_run": False}); add("disk_ollama_free", {"models_dir": OLL, "dry_run": False, "confirm": True, "mode": "permanent"})
    add("disk_ollama_free", {"models_dir": OLL, "ids": ["no-existe"]}); add("disk_ollama_free", {"models_dir": "<fix>\\no-existe"})
    add("disk_ollama_backups", {"models_dir": OLL})
    # --- delete (only the permanent mode and only inside the copy) ---
    add("disk_delete", {"paths": [T + "\\proyecto/dist"], "mode": "permanent"})
    add("disk_delete", {"paths": [T + "\\proyecto/.git"], "mode": "permanent", "confirm": True})
    add("disk_delete", {"paths": [T + "\\nada"], "mode": "permanent", "confirm": True}); add("disk_delete", {"paths": []}); add("disk_delete", {"paths": [T + "\\proyecto/dist"], "mode": "otro"}); add("disk_delete", {})
    add("disk_delete", {"paths": [T + "\\proyecto/node_modules"], "mode": "permanent", "confirm": True}, setup="grow_node")
    add("disk_rescan", {"path": T + "\\proyecto"}); add("disk_rescan", {"path": T + "\\nada"}); add("disk_rescan", {})
    add("disk_delete", {"paths": [T + "\\proyecto/node_modules"], "mode": "permanent", "confirm": True})
    add("disk_delete", {"paths": [T + "\\proyecto/dist", T + "\\proyecto/__pycache__"], "mode": "permanent", "confirm": True})
    add("disk_find", {"path": T + "\\proyecto", "limit": 50}); add("disk_dir", {"path": T + "\\proyecto"}); add("disk_status"); add("disk_junk", {"min_mb": 0})
    add("no_such_tool", {}, loose=True)
    return c


def mutate():
    """A deliberate regression in Talos's copy: every human-readable size is replaced by a placeholder."""
    from diskhoard import agent
    agent._fmt = lambda n: "?"
