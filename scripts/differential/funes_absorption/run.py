"""Runs the differential test of the Funes absorption.

    python run.py --pre <Funes source tree before the absorption> --kit <HoardLink checkout> [--work <folder>] [--mutate]

* --pre   a checkout of the last Funes commit before its code moved into Talos (``git archive`` of that commit into an empty folder).
          It is only read; nothing is written inside it.
* --kit   the HoardLink checkout that holds ``hoard_link.parity``.
* --work  scratch folder (default: a new temporary one, left in place so the reports can be read). Never inside this repository.
* --mutate  negative control: Talos runs with a deliberate regression and the test must fail.

Steps: build the shared starting data with the OLD code, write the two WAV inputs, then run the kit on two harnesses (Talos's main route
and the legacy Funes route). The kit's report.json files are copied to ``<work>/state``; the exit code is the kit's (0 equal, 1 differs).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre", required=True)
    ap.add_argument("--kit", required=True)
    ap.add_argument("--work")
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--stable", type=int, default=3, help="consecutive passes required (the kit advises three for a new harness)")
    args = ap.parse_args()
    pre, kit = Path(args.pre).resolve(), Path(args.kit).resolve()
    work = Path(args.work).resolve() if args.work else Path(tempfile.mkdtemp(prefix="funes-diff-"))
    if REPO in work.parents or work == REPO:
        raise SystemExit("the work folder must be outside the repository")
    work.mkdir(parents=True, exist_ok=True)
    site = REPO / ".venv" / ("Lib" if os.name == "nt" else "lib") / "site-packages"
    env = {**os.environ, "PYTHONUTF8": "1"}
    old_env = {**env, "PYTHONPATH": os.pathsep.join([str(pre), str(site)] if site.exists() else [str(pre)])}
    base, fixtures = work / "base", work / "fixtures"
    subprocess.run([sys.executable, str(HERE / "make_base.py"), str(base)], check=True, env=old_env, cwd=str(pre))
    subprocess.run([sys.executable, str(HERE / "mk_fixtures.py"), str(fixtures)], check=True, env=env)
    paths = work / "paths.json"
    paths.write_text(json.dumps({"base": str(base), "pre": str(pre), "talos": str(REPO), "python": sys.executable, "fixtures": str(fixtures)}), encoding="utf-8")
    run_env = {**env, "PYTHONPATH": str(kit), "FUNES_DIFF_PATHS": str(paths)}
    if args.mutate:
        run_env["FUNES_DIFF_MUTATE"] = "1"
    code = 0
    for harness in ("harness_talos.py", "harness_legacy.py"):
        done = subprocess.run([sys.executable, "-m", "hoard_link.parity", "run", str(HERE / harness), "--state-dir", str(work / "state"), "--fresh", "--force", "--stable", str(args.stable)], env=run_env)
        code = max(code, done.returncode)
    print("work folder (delete it when done):", work)
    print("reports:", *(str(p) for p in (work / "state").glob("*/report.json")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
