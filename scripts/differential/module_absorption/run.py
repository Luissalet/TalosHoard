"""Runs the differential test of the absorption of Argus (Pantalla), Echo (Portapapeles), Cassandra (Servicios) and DiskHoard (Disco).

    python run.py --pre-root <folder with ArgusHoard, EchoHoard, CassandraHoard, DiskHoard> --kit <HoardLink checkout>
                  [--module argus|echo|cassandra|disk|all] [--work <folder>] [--stable 3] [--mutate]

* --pre-root  the last commit of each original repository, brought in with ``git archive`` into one folder per app. Only read.
* --kit       the HoardLink checkout that holds ``hoard_link.parity``.
* --work      scratch folder (default: a new temporary one, left in place so the reports can be read). Never inside this repository.
* --mutate    negative control: Talos runs with a deliberate regression and every module's test must fail.

Per module: the base data is built with the OLD code, then the kit runs two harnesses (Talos's main address and the module's own prefix).
The kit's report.json files are copied to ``<work>/state``; the exit code is the worst of the kit's (0 equal, 1 differs).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
MODULES = {"argus": "ArgusHoard", "echo": "EchoHoard", "cassandra": "CassandraHoard", "disk": "DiskHoard"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre-root", required=True)
    ap.add_argument("--kit", required=True)
    ap.add_argument("--module", default="all", choices=["all", *MODULES])
    ap.add_argument("--work")
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--stable", type=int, default=3, help="consecutive passes required (the kit advises three for a new harness)")
    args = ap.parse_args()
    pre_root, kit = Path(args.pre_root).resolve(), Path(args.kit).resolve()
    work = Path(args.work).resolve() if args.work else Path(tempfile.mkdtemp(prefix="absorb-diff-"))
    if REPO in work.parents or work == REPO:
        raise SystemExit("the work folder must be outside the repository")
    work.mkdir(parents=True, exist_ok=True)
    site = REPO / ".venv" / ("Lib" if os.name == "nt" else "lib") / "site-packages"
    env = {**os.environ, "PYTHONUTF8": "1"}
    code = 0
    for module in (MODULES if args.module == "all" else [args.module]):
        pre = pre_root / MODULES[module]
        if not pre.is_dir():
            raise SystemExit(f"missing {pre}")
        mwork = work / module
        base, fixtures = mwork / "base", mwork / "fixtures"
        mwork.mkdir(parents=True, exist_ok=True)
        old_env = {**env, "PYTHONPATH": os.pathsep.join([str(pre), str(site)] if site.exists() else [str(pre)]),
                   **__import__(f"mod_{module}").ENV, **getattr(__import__(f"mod_{module}"), "OLD_ENV", {})}
        subprocess.run([sys.executable, str(HERE / "make_base.py"), module, str(base), str(fixtures)], check=True, env=old_env, cwd=str(pre))
        paths = mwork / "paths.json"
        paths.write_text(json.dumps({"module": module, "base": str(base), "pre": str(pre), "talos": str(REPO), "python": sys.executable,
                                     "fixtures": str(fixtures)}), encoding="utf-8")
        run_env = {**env, "PYTHONPATH": str(kit), "ABSORB_PATHS": str(paths), "ABSORB_MODULE": module}
        if args.mutate:
            run_env["ABSORB_MUTATE"] = "1"
        for harness in ("harness_main.py", "harness_native.py"):
            done = subprocess.run([sys.executable, "-m", "hoard_link.parity", "run", str(HERE / harness), "--state-dir", str(mwork / "state"), "--fresh",
                                   "--force", "--stable", str(args.stable)], env=run_env)
            code = max(code, done.returncode)
    print("work folder (delete it when done):", work)
    print("reports:", *(str(p) for p in work.glob("*/state/*/report.json")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
