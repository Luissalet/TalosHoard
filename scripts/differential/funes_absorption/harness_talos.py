"""Kit harness: the original Funes (oracle) against Talos's Activity and Audio modules called through /api/agent/call (probe)."""
import os
import sys
from pathlib import Path

from hoard_link.parity import Command, Corpus, Harness

HERE = Path(__file__).resolve().parent
SIDE = "talos"
NAME = "funes-absorption-talos"
SCOPE = ("The calls of the original Activity (19) and Audio (16) tools over three synthetic days and three audio sessions, with a fake audio "
         "backend, a fake transcriber, no language model and no other app running. Not covered: real capture, a real speech model, minutes "
         "written by a model, the web interfaces, concurrency and data migrated from a real installation. Compared after masking generated "
         "ids, the clock, temporary paths, the ports and the up/down wording of sibling apps (now modules of one server) and with the "
         "optional arguments Talos added on purpose ignored.")


def harness() -> Harness:
    sys.path.insert(0, str(HERE))
    from corpus_cases import cases

    def corpus() -> Corpus:
        c = Corpus(seed="funes-absorption")
        for spec in cases():
            c.add(spec)
        return c

    env = {"FUNES_DIFF_PATHS": os.environ["FUNES_DIFF_PATHS"]}
    if os.environ.get("FUNES_DIFF_MUTATE"):
        env["FUNES_DIFF_MUTATE"] = "1"
    return Harness(name=NAME, root=HERE, corpus=corpus, scope=SCOPE,
                   oracle=Command([sys.executable, str(HERE / "side.py"), "oracle"], env=env, timeout=900),
                   probe=Command([sys.executable, str(HERE / "side.py"), SIDE], env=env, timeout=900),
                   depends_on=["*.py"], oracle_depends_on=["side.py", "serve_old.py", "corpus_cases.py", "make_base.py"],
                   description="Differential test of the absorption of Funes (activity and audio) into Talos.")
