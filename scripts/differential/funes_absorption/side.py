"""Oracle / probe for the Funes absorption differential.

usage: side.py <oracle|talos|legacy> <inputs.jsonl> <trace.jsonl>

oracle  the last Funes commit before the absorption, run as its own server (activity + audio in one process)
talos   Talos's modules (activity + audio) called through /api/agent/call
legacy  the same Talos modules called through the old Funes address /legacy/funes/api/agent/call
Every side starts from a copy of the same base data in a temporary folder that is deleted at the end; servers are own child processes.
"""
import json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request, urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG: dict = {}   # base, pre, talos, python, fixtures and ids; written by run.py (env FUNES_DIFF_PATHS)


def load_config() -> dict:
    CFG.update(json.loads(Path(os.environ["FUNES_DIFF_PATHS"]).read_text(encoding="utf-8")))
    CFG["ids"] = json.loads((Path(CFG["base"]) / "ids.json").read_text(encoding="utf-8"))
    return CFG


SID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{4}")
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
VOLATILE_KEYS = {"pid", "port", "uptime_s", "elapsed_s", "duration_ms", "took_ms", "ms", "time_ms"}


class Norm:
    """Replaces what legitimately differs between two runs: generated ids (by first appearance), the clock and temp paths."""
    def __init__(self, tmp: str, ids: dict | None = None):
        self.ids = ids if ids is not None else CFG.get("ids", {})
        self.sids: dict[str, str] = {}
        self.t0 = time.time()
        self.tmp = tmp.replace("\\", "/").lower()
        self.jobs: dict[str, str] = {}
        self.tool = ""
        self.elapsed: set[str] = set()   # live recordings: their length is wall-clock time

    def sid(self, m):
        known = {v: f"<{k}>" for k, v in self.ids.items()}
        return known.get(m.group(0)) or self.sids.setdefault(m.group(0), f"<sid{len(self.sids)}>")

    def stamp(self, m) -> str:
        """A 'YYYY-MM-DD HH:MM' stamp (export headers) is masked only when it is the current time."""
        import datetime as dt
        try:
            return "<now>" if abs(dt.datetime.strptime(m.group(0), "%Y-%m-%d %H:%M").timestamp() - self.t0) < 6 * 3600 else m.group(0)
        except ValueError:
            return m.group(0)

    def near_now(self, x: float) -> bool:
        return abs(x - self.t0) < 6 * 3600

    def text(self, s: str) -> str:
        s = s.replace("\\", "/")
        s = re.sub(re.escape(self.tmp) + r"[^\s\"']*", "<tmp>", s, flags=re.I)
        s = SID.sub(self.sid, s)
        s = re.sub(r"\b[0-9a-f]{32}\b", "<hex32>", s)
        s = re.sub(r"\btoday \d{2}:\d{2}\b", "today <hh:mm>", s)
        s = re.sub(r"\b\d{4}-\d{2}-\d{2} \d{2}:\d{2}\b", self.stamp, s)
        s = re.sub(r"http://127\.0\.0\.1:\d+(/\w+)?", "http://127.0.0.1:<port>", s)   # the sibling apps are now modules of one server
        return re.sub(r"\b[0-9a-f]{12}\b", lambda m: self.jobs.setdefault(m.group(0), f"<job{len(self.jobs)}>"), s)

    def value(self, v, key=None):
        if isinstance(v, dict):
            if v.get("id") in self.elapsed:
                v = {k: ("<elapsed>" if k in ("duration", "duration_s", "ended_at", "first_line", "no_speech") else x) for k, x in v.items()}
            return {k: ("<volatile>" if k in VOLATILE_KEYS or (k == "since" and self.tool == "activity_project_resume")
                        else "<down>" if k == "reason" and x in ("unreachable", "disabled") else self.value(x, k)) for k, x in sorted(v.items())}
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
                    if abs(dt.datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp() - self.t0) < 6 * 3600:
                        return "<now>"
                except ValueError:
                    pass
            return self.text(v)
        return v


def free_port() -> int:
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def http(method, url, token, body=None, timeout=120):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(); code = r.status
    except urllib.error.HTTPError as e:
        raw = e.read(); code = e.code
    try:
        return code, json.loads(raw)
    except ValueError:
        return code, {"raw": raw.decode("utf-8", "replace")[:400]}


def main(side, inputs, output):
    load_config()
    tmp = Path(tempfile.mkdtemp(prefix=f"funes-diff-{side}-"))
    log = open(tmp / "server.log", "wb")
    proc = None
    try:
        base = Path(CFG["base"])
        port = free_port()
        if side == "oracle":
            data = tmp / "data"; shutil.copytree(base, data)
            cmd = [CFG["python"], str(HERE / "serve_old.py"), CFG["pre"], str(data), str(port)]
            env = {**os.environ, "PYTHONPATH": CFG["pre"] + os.pathsep + str(Path(CFG["talos"]) / ".venv" / "Lib" / "site-packages"), "PYTHONUTF8": "1"}
            health = f"http://127.0.0.1:{port}/api/health"
            token_file = data / "mcp-token"
        else:
            data = tmp / "data"; (data / "activity").mkdir(parents=True)
            shutil.copytree(base / "audio", data / "audio")
            for item in base.iterdir():
                if item.name != "audio" and item.is_file():
                    shutil.copy2(item, data / "activity" / item.name)
            cmd = [CFG["python"], str(HERE / "serve_talos.py"), CFG["talos"], str(data), str(port)]
            env = {**os.environ, "PYTHONUTF8": "1"}; env.pop("PYTHONPATH", None)
            health = f"http://127.0.0.1:{port}/legacy/funes/api/health"
            token_file = data / ("activity" if side == "legacy" else "") / "mcp-token"
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env, cwd=str(tmp))
        deadline = time.time() + 120
        while time.time() < deadline:
            if proc.poll() is not None:
                raise SystemExit(f"{side} server exited: {(tmp / 'server.log').read_text(errors='replace')[-600:]}")
            try:
                with urllib.request.urlopen(health, timeout=3) as r:
                    if r.status == 200 and token_file.exists():
                        break
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.5)
        else:
            raise SystemExit(f"{side} server never became healthy")
        time.sleep(1.0)
        token = token_file.read_text(encoding="utf-8").strip()
        norm = Norm(str(tmp), CFG["ids"])
        saved: dict[str, str] = dict(CFG["ids"])
        base_url = f"http://127.0.0.1:{port}"
        with open(output, "w", encoding="utf-8", newline="\n") as out:
            for line in open(inputs, encoding="utf-8"):
                case = json.loads(line); spec = case["input"]
                args = json.loads(re.sub(r"@(\w+)", lambda m: saved.get(m.group(1), m.group(0)),
                                         json.dumps(spec.get("args", {}), ensure_ascii=False)).replace("<fix>", CFG["fixtures"].replace("\\", "/")))
                if side == "oracle":
                    path = "/audio/api/agent/call" if spec.get("via") == "audio" else "/api/agent/call"
                elif side == "talos":
                    path = "/api/agent/call"
                else:
                    path = "/legacy/funes/api/agent/call"
                if spec.get("list_tools"):
                    tools = {}
                    lists = [("/api/agent/tools", token)] if side != "legacy" else [("/legacy/funes/api/agent/tools", token)]
                    if side == "oracle":
                        lists.append(("/audio/api/agent/tools", (data / "audio" / "mcp-token").read_text(encoding="utf-8").strip()))
                    for lpath, ltoken in lists:
                        code, body = http("GET", base_url + lpath, ltoken)
                        for t in (body.get("tools") or []) if isinstance(body, dict) else []:
                            sch = t.get("inputSchema") or {}
                            tools.setdefault(t["name"], {"props": {k: v.get("type") for k, v in sorted((sch.get("properties") or {}).items())}, "required": sorted(sch.get("required") or [])})
                    result = {n: tools.get(n, "<absent>") for n in spec["list_tools"]}
                    for tname, extra in (spec.get("additive") or {}).items():   # optional arguments Talos added on purpose; any other new argument diverges
                        for prop in extra:
                            if isinstance(result.get(tname), dict):
                                result[tname]["props"].pop(prop, None)
                    out.write(json.dumps({"id": case["id"], "ev": [["query", "tools", spec["list_tools"][:1]]], "out": result}, ensure_ascii=False, separators=(",", ":")) + "\n")
                    continue
                use = token
                if side == "oracle" and spec.get("via") == "audio":
                    use = (data / "audio" / "mcp-token").read_text(encoding="utf-8").strip()
                code, body = http("POST", base_url + path, use, {"name": spec["tool"], "arguments": args})
                for name, where in (spec.get("save") or {}).items():
                    cur = body
                    for part in where.split("."):
                        cur = cur.get(part) if isinstance(cur, dict) else (cur[int(part)] if isinstance(cur, list) and part.isdigit() and int(part) < len(cur) else None)
                    if isinstance(cur, str):
                        saved[name] = cur
                        if name in ("live", "both"):
                            norm.elapsed.add(cur)
                if spec.get("sleep"):
                    time.sleep(spec["sleep"])
                norm.tool = spec["tool"]
                if spec.get("coarse"):   # a live recording: segment boundaries follow the wall clock, so only who said what is compared
                    lines = []
                    if isinstance(body, dict):
                        lines += [f"{x.get('speaker')}: {x.get('text')}" for x in body.get("segments") or []]
                        lines += [re.sub(r"^\[\d+:\d+\] ", "", x) for x in str(body.get("text") or "").splitlines()[3:]]
                    result = {"status": code, "lines": sorted(lines)}
                elif spec.get("loose"):   # known wording/envelope differences of the proxied activity route: only succeeded or failed is compared
                    result = {"failed": code >= 400 or (isinstance(body, dict) and body.get("ok") is False)}
                else:
                    result = {"status": code, "body": body}
                record = {"id": case["id"], "ev": [["query", spec["tool"], norm.value(args)]], "out": norm.value(result)}
                out.write(json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(15)
            except subprocess.TimeoutExpired:
                proc.kill()
        log.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
