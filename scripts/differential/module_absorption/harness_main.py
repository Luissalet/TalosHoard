"""Kit harness: the original app (oracle) against ONE Talos module called through Talos's own address /api/agent/call (probe).
The module comes from the environment (ABSORB_MODULE), so the same file serves Pantalla, Portapapeles, Servicios and Disco."""
import os
import sys
from pathlib import Path

from hoard_link.parity import Command, Corpus, Harness

HERE = Path(__file__).resolve().parent
MODULE = os.environ.get("ABSORB_MODULE", "argus")
ROUTE = "main"
NAME = f"absorb-{MODULE}-{ROUTE}"
SCOPE = ("The calls of every tool of the original app over synthetic data built by the original code, with fake capture, clipboard, window, "
         "process and network backends, no language model and no other app running. Not covered: real hardware capture, real OCR of "
         "live screens, real services, the web interfaces, concurrency and data migrated from a real installation. Compared after "
         "masking the clock, temporary paths, ports and generated ids, and with the arguments and tools Talos added on purpose ignored.")


def harness() -> Harness:
    sys.path.insert(0, str(HERE))
    mod = __import__("mod_" + MODULE)

    def corpus() -> Corpus:
        c = Corpus(seed=f"absorb-{MODULE}")
        for spec in mod.cases():
            c.add(spec)
        return c

    env = {"ABSORB_PATHS": os.environ["ABSORB_PATHS"]}
    if os.environ.get("ABSORB_MUTATE"):
        env["ABSORB_MUTATE"] = "1"
    return Harness(name=NAME, root=HERE, corpus=corpus, scope=SCOPE,
                   oracle=Command([sys.executable, str(HERE / "side.py"), "oracle"], env=env, timeout=1500),
                   probe=Command([sys.executable, str(HERE / "side.py"), ROUTE], env=env, timeout=1500),
                   depends_on=["*.py"], oracle_depends_on=["side.py", "serve_old.py", f"mod_{MODULE}.py", "make_base.py"],
                   description=f"Differential test of the absorption of {MODULE} into Talos ({ROUTE} route).")
