"""Starts Talos with the activity and audio modules on, on <port> over <data>, with the same fixed probe and fake audio."""
import json, os, sys
from pathlib import Path
root, data, port = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3])
sys.path.insert(0, root); sys.path.insert(0, str(Path(root) / ".venv" / "Lib" / "site-packages"))
for k, v in {"HOARD_HUB_URL": "http://127.0.0.1:1", "HOARD_HUB_AUTOSTART": "0", "HOARD_LLM_URL": "http://127.0.0.1:1/v1", "SCRIBE_AUDIO": "fake", "SCRIBE_TRANSCRIBER": "fake", "ARGUS_CAPTURE": "fake",
             "ARGUS_WINDOW": "fake", "ARGUS_VISUAL": "none", "ECHO_BACKEND": "fake", "CASSANDRA_AUTOSTART": "0", "TANTALUS_OFFLINE": "1", "PHILEAS_OFFLINE": "1",
             "PYTHONIOENCODING": "utf-8", "SCRIBE_DEVICE": "cpu", "SCRIBE_COMPUTE_TYPE": "int8"}.items():
    os.environ[k] = v
(data / "modules.json").write_text(json.dumps({"enabled": ["activity", "audio"], "data_paths": {}}), encoding="utf-8")
import funes_hoard.api as fapi
from funes_hoard.demo import LiveDemoProbe
fapi._pick_probe = lambda demo: LiveDemoProbe()
fapi.windows_recent_dir = lambda: None       # the oracle (demo mode) never reads the real Recent folder either   # same stand-in the oracle gets from --demo: never the real desktop
if os.environ.get("FUNES_DIFF_MUTATE"):   # negative control: a deliberate regression the differential must catch
    from funes_hoard.audio_memory.store import SessionStore
    for _name in ("append_notes", "append_notes_once"):
        setattr(SessionStore, _name, (lambda original: lambda self, sid, text, *a, **k: original(self, sid, text[1:], *a, **k))(getattr(SessionStore, _name)))
from talos_hoard.app import create_app
import uvicorn
uvicorn.run(create_app(data, port=port), host="127.0.0.1", port=port, log_level="warning")
