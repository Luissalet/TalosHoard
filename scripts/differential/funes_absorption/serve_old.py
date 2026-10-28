"""Starts the pre-absorption Funes (activity + audio in one process) on <port> over <data>, as the oracle."""
import os, sys
pre, data, port = sys.argv[1:4]
sys.path.insert(0, pre)
for k, v in {"HOARD_HUB_URL": "http://127.0.0.1:1", "HOARD_HUB_AUTOSTART": "0", "HOARD_LLM_URL": "http://127.0.0.1:1/v1", "SCRIBE_AUDIO": "fake", "SCRIBE_TRANSCRIBER": "fake", "PYTHONIOENCODING": "utf-8"}.items():
    os.environ[k] = v
sys.argv = ["funes_hoard", "--demo", "--no-browser", "--port", port, "--data-dir", data]
import funes_hoard
assert os.path.normcase(os.path.abspath(pre)) in os.path.normcase(os.path.abspath(funes_hoard.__file__)), funes_hoard.__file__
from funes_hoard.__main__ import main
main()
