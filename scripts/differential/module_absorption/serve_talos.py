"""Starts Talos with ONE module on, on <port> over <data>, with the same fixed fake engines the oracle gets.

usage: serve_talos.py <module> <talos checkout> <data> <port>
"""
import importlib
import json
import os
import sys
from pathlib import Path

module, root, data, port = sys.argv[1], sys.argv[2], Path(sys.argv[3]), int(sys.argv[4])
sys.path.insert(0, str(Path(__file__).resolve().parent))
mod = importlib.import_module("mod_" + module)
sys.path.insert(0, root)
sys.path.insert(1, str(Path(root) / ".venv" / "Lib" / "site-packages"))
(data / "modules.json").write_text(json.dumps({"enabled": [mod.TALOS_ID], "data_paths": {}}), encoding="utf-8")
if hasattr(mod, "prepare_talos"):
    mod.prepare_talos()
if os.environ.get("ABSORB_MUTATE"):   # negative control: a deliberate regression the differential must catch
    mod.mutate()
from talos_hoard.app import create_app
import uvicorn
uvicorn.run(create_app(data, port=port), host="127.0.0.1", port=port, log_level="warning")
