"""Builds the shared starting data with the ORIGINAL code (run with it first on PYTHONPATH and as the working folder).

usage: make_base.py <module> <out> <fixtures>
"""
import importlib
import shutil
import sys
from pathlib import Path

module, out, fixtures = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(Path(__file__).resolve().parent))
mod = importlib.import_module("mod_" + module)
pkg = importlib.import_module(mod.OLD_PKG)
assert Path(pkg.__file__).resolve().parent.parent == Path.cwd().resolve(), f"run this from the old source tree, not {pkg.__file__}"
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)
shutil.rmtree(fixtures, ignore_errors=True)
fixtures.mkdir(parents=True)
mod.build_fixtures(fixtures)
mod.build_base(out, fixtures)
for leftover in ("mcp-token", "url", "logs"):   # per-run files each side creates for itself
    p = out / leftover
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
    elif p.exists():
        p.unlink()
print("base ready", out)
