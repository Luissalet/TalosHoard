"""Oracle / probe for the module-absorption differentials (Pantalla/Argus, Portapapeles/Echo, Servicios/Cassandra, Disco/DiskHoard).

usage: side.py <oracle|main|native> <inputs.jsonl> <trace.jsonl>

oracle  the last commit of the original app, run as its own server (``python -m <package>``)
main    Talos with that one module on, called through Talos's own address ``/api/agent/call`` (the Talos token)
native  the same Talos module called through its own prefix ``/<module>/api/agent/call`` (the module's token)

The module under test comes from the environment (``ABSORB_PATHS`` holds the paths written by run.py). Every side starts from a copy
of the same base data in a temporary folder that is deleted at the end; the servers are child processes of this one.
"""
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CFG: dict = {}


def load_config():
    CFG.update(json.loads(Path(os.environ["ABSORB_PATHS"]).read_text(encoding="utf-8")))
    mod = importlib.import_module("mod_" + CFG["module"])
    return mod


ISO = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
VOLATILE_KEYS = {"pid", "port", "uptime_s", "elapsed_s", "duration_ms", "took_ms", "ms", "time_ms"}


class Norm:
    """Replaces what legitimately differs between two runs: the clock, temporary paths, ports and (per module) generated ids."""

    def __init__(self, tmp: str, mod):
        self.tmp = tmp.replace("\\", "/").lower()
        self.t0 = time.time()
        self.mod = mod
        self.volatile = VOLATILE_KEYS | set(getattr(mod, "VOLATILE_KEYS", ()))
        self.down = set(getattr(mod, "DOWN_WORDS", ()))
        self.seen: dict[str, dict[str, str]] = {}
        self.tool = ""

    def alias(self, kind: str, raw: str) -> str:
        table = self.seen.setdefault(kind, {})
        return table.setdefault(raw, f"<{kind}{len(table)}>")

    def text(self, s: str) -> str:
        s = s.replace("\\", "/")
        s = re.sub(re.escape(self.tmp) + r"[^\s\"']*", "<tmp>", s, flags=re.I)
        s = re.sub(r"\b[0-9a-f]{32}\b", "<hex32>", s)
        s = re.sub(r"http://127\.0\.0\.1:\d+", "http://127.0.0.1:<port>", s)
        for pattern, kind in getattr(self.mod, "ALIASES", ()):
            s = re.sub(pattern, lambda m, k=kind: self.alias(k, m.group(0)), s)
        for pattern, repl in getattr(self.mod, "SUBS", ()):
            s = re.sub(pattern, repl, s)
        return s

    def near_now(self, x: float) -> bool:
        return abs(x - self.t0) < 6 * 3600

    def value(self, v, key=None):
        if isinstance(v, dict):
            return {k: ("<volatile>" if k in self.volatile else self.value(x, k)) for k, x in sorted(v.items())}
        if isinstance(v, list):
            return [self.value(x, key) for x in v]
        if isinstance(v, bool) or v is None:
            return v
        if isinstance(v, (int, float)):
            return "<now>" if isinstance(v, float) and self.near_now(v) else v
        if isinstance(v, str):
            if ISO.match(v):
                try:
                    import datetime as dt
                    when = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
                    if abs((when.timestamp() if when.tzinfo else when.timestamp()) - self.t0) < 6 * 3600:
                        return "<now>"
                except ValueError:
                    pass
            return self.text(v)
        return v

    def shape(self, v):
        """Only the structure: for answers that describe this very machine (its drives, its clock)."""
        if isinstance(v, dict):
            return {k: self.shape(x) for k, x in sorted(v.items())}
        if isinstance(v, list):
            return [self.shape(v[0])] if v else []
        return type(v).__name__


def free_port() -> int:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def http(method, url, token, body=None, timeout=180):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            code = r.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        code = e.code
    try:
        return code, json.loads(raw)
    except ValueError:
        return code, {"raw": raw.decode("utf-8", "replace")[:400]}


def main(side, inputs, output):
    mod = load_config()
    tag = {"oracle": "orac", "main": "main", "native": "nati"}[side]   # same length on every side: some answers (ZIP manifests) carry paths
    tmp = Path(tempfile.mkdtemp(prefix=f"absorb-{CFG['module']}-{tag}-"))
    log = open(tmp / "server.log", "wb")
    proc = None
    closers: list = []
    try:
        base = Path(CFG["base"])
        port = free_port()
        data = tmp / "data"
        fix = tmp / "fix"
        shutil.copytree(CFG["fixtures"], fix)
        base_env = {**os.environ, "PYTHONUTF8": "1", "HOARD_HUB_URL": "http://127.0.0.1:1", "HOARD_HUB_AUTOSTART": "0", "HOARD_LLM_URL": "http://127.0.0.1:1/v1",
                    "HOARD_NO_BROWSER": "1", "PYTHONIOENCODING": "utf-8"}
        base_env.update(mod.ENV)
        site = str(Path(CFG["talos"]) / ".venv" / "Lib" / "site-packages")
        if side == "oracle":
            shutil.copytree(base, data)
            cmd = [CFG["python"], str(HERE / "serve_old.py"), CFG["module"], CFG["pre"], str(data), str(port)]
            env = {**base_env, **getattr(mod, "OLD_ENV", {}), "PYTHONPATH": CFG["pre"] + os.pathsep + site}
            health = f"http://127.0.0.1:{port}/api/health"
            token_file = data / "mcp-token"
            call_path, tools_path = "/api/agent/call", "/api/agent/tools"
        else:
            data.mkdir()
            shutil.copytree(base, data / mod.TALOS_ID)
            cmd = [CFG["python"], str(HERE / "serve_talos.py"), CFG["module"], CFG["talos"], str(data), str(port)]
            env = {**base_env, **getattr(mod, "TALOS_ENV", {})}
            env.pop("PYTHONPATH", None)
            health = f"http://127.0.0.1:{port}/api/health"
            if side == "main":
                token_file = data / "mcp-token"
                call_path, tools_path = "/api/agent/call", "/api/agent/tools"
            else:
                token_file = data / mod.TALOS_ID / "mcp-token"
                call_path, tools_path = f"/{mod.TALOS_ID}/api/agent/call", f"/{mod.TALOS_ID}/api/agent/tools"
        if os.environ.get("ABSORB_MUTATE"):
            env["ABSORB_MUTATE"] = "1"
        if hasattr(mod, "helpers"):   # stand-ins for other programs (a fake Faustus), on a private port, in this process
            extra_env, closer = mod.helpers(tmp, fix)
            closers.append(closer)
            env.update(extra_env)
        env = {k: v.replace("<fix>", str(fix)).replace("<data>", str(data)) if isinstance(v, str) else v for k, v in env.items()}   # per-side folders
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env, cwd=str(tmp))
        deadline = time.time() + 180
        while time.time() < deadline:
            if proc.poll() is not None:
                raise SystemExit(f"{side} server exited: {(tmp / 'server.log').read_text(errors='replace')[-900:]}")
            try:
                with urllib.request.urlopen(health, timeout=3) as r:
                    body = json.loads(r.read())
                    ready = r.status == 200 and token_file.exists()
                    if ready and side != "oracle":
                        ready = any(m.get("id") == mod.TALOS_ID and m.get("enabled") for m in body.get("modules", []))
                    if ready:
                        break
            except (urllib.error.URLError, OSError, ValueError):
                pass
            time.sleep(0.5)
        else:
            raise SystemExit(f"{side} server never became healthy: {(tmp / 'server.log').read_text(errors='replace')[-900:]}")
        time.sleep(1.0)
        token = token_file.read_text(encoding="utf-8").strip()
        norm = Norm(str(tmp), mod)
        saved: dict[str, str] = {}
        root = f"http://127.0.0.1:{port}"
        with open(output, "w", encoding="utf-8", newline="\n") as out:
            for line in open(inputs, encoding="utf-8"):
                case = json.loads(line)
                spec = case["input"]
                raw_args = json.dumps(spec.get("args", {}), ensure_ascii=False)
                raw_args = re.sub(r"@(\w+)", lambda m: saved.get(m.group(1), m.group(0)), raw_args)
                raw_args = raw_args.replace("<fix>", json.dumps(str(fix))[1:-1]).replace("<data>", json.dumps(str(data))[1:-1])   # native separators, as an assistant sends them
                args = json.loads(raw_args)
                if spec.get("list_tools"):
                    code, body = http("GET", root + tools_path, token)
                    tools = {}
                    for t in (body.get("tools") or []) if isinstance(body, dict) else []:
                        sch = t.get("inputSchema") or {}
                        tools[t["name"]] = {"props": {k: v.get("type") for k, v in sorted((sch.get("properties") or {}).items())}, "required": sorted(sch.get("required") or [])}
                    result = {n: tools.get(n, "<absent>") for n in spec["list_tools"]}
                    for tname, extra in (spec.get("additive") or {}).items():   # optional arguments added on purpose; any other new argument diverges
                        for prop in extra:
                            if isinstance(result.get(tname), dict):
                                result[tname]["props"].pop(prop, None)
                    out.write(json.dumps({"id": case["id"], "ev": [["query", "tools", spec["list_tools"][:1]]], "out": result}, ensure_ascii=False, separators=(",", ":")) + "\n")
                    continue
                if spec.get("setup"):
                    getattr(mod, spec["setup"])(Path(fix), Path(data), saved)
                code, body = http("POST", root + call_path, token, {"name": spec["tool"], "arguments": args}, timeout=spec.get("timeout", 180))
                for name, where in (spec.get("save") or {}).items():
                    cur = body
                    for part in where.split("."):
                        cur = cur.get(part) if isinstance(cur, dict) else (cur[int(part)] if isinstance(cur, list) and part.isdigit() and int(part) < len(cur) else None)
                    if isinstance(cur, (str, int)) and not isinstance(cur, bool):
                        saved[name] = str(cur)
                if spec.get("sleep"):
                    time.sleep(spec["sleep"])
                norm.tool = spec["tool"]
                if spec.get("shape"):
                    result = {"status": code, "shape": norm.shape(body)}
                elif spec.get("loose"):   # known wording/envelope differences: only succeeded or failed is compared
                    result = {"failed": code >= 400 or (isinstance(body, dict) and body.get("ok") is False)}
                else:
                    result = {"status": code, "body": body}
                record = {"id": case["id"], "ev": [["query", spec["tool"], norm.value(args)]], "out": norm.value(result)}
                out.write(json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
                if spec.get("after"):
                    getattr(mod, spec["after"])(Path(fix), Path(data), saved)
    except BaseException:
        log.flush()
        sys.stderr.write(f"--- {side} server log (tail) ---\n{(tmp / 'server.log').read_text(errors='replace')[-1800:]}\n")
        raise
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(20)
            except subprocess.TimeoutExpired:
                proc.kill()
        for closer in closers:
            try:
                closer()
            except Exception:
                pass
        log.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
