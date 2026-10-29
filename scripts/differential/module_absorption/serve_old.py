"""Starts the original app (the oracle) from its pre-absorption source tree on <port> over <data>.

usage: serve_old.py <module> <pre tree> <data> <port>
"""
import importlib
import os
import runpy
import sys
from pathlib import Path

module, pre, data, port = sys.argv[1:5]
sys.path.insert(0, str(Path(__file__).resolve().parent))
mod = importlib.import_module("mod_" + module)
sys.path.insert(0, pre)
pkg = importlib.import_module(mod.OLD_PKG)
assert os.path.normcase(os.path.abspath(pre)) in os.path.normcase(os.path.abspath(pkg.__file__)), pkg.__file__   # never an installed copy
if hasattr(mod, "prepare_old"):
    mod.prepare_old()
if hasattr(mod, "run_old"):
    mod.run_old(pre, data, port)
else:
    sys.argv = [mod.OLD_PKG, "--no-browser", "--port", port, "--data-dir", data]
    runpy.run_module(mod.OLD_PKG + ".__main__", run_name="__main__")
