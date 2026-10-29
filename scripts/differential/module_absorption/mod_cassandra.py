"""Servicios (Cassandra): the original app against Talos's `services` module.

The base data is built by the ORIGINAL code with a fake network, clock, process table, GPU and hub: four apps found by their manifests
(one goes down and comes back with another pid, one degrades, one answers as a foreign program, one never ran), logs with errors, GPU
samples, the mirrored family bus, and three public sites (one goes down). Then the call sequence replays on both sides with the poller,
the bus mirror and the site watcher switched off (they would talk to the real PC), a fixed clock, a fake restart backend and a fake
Faustus on a private port.
Not compared on purpose: the SEO / GEO watch that Cassandra did not have (its tools, its two optional arguments of `sites_watch` and the
`seo` block of the status).
"""
import datetime as dt
import json
import sys
import threading
from pathlib import Path

TALOS_ID = "services"
OLD_PKG = "cassandra_hoard"
T0 = 1_790_000_000.0
NOW_SERVE = T0 + 6 * 3600
ENV = {"CASSANDRA_AUTOSTART": "0", "CASSANDRA_EXTERNALS": "0", "CASSANDRA_GPU": "0", "CASSANDRA_DEFAULT_LOGS": "0", "CASSANDRA_HUB_REGISTRY": "0",
       "CASSANDRA_BUS": "0", "CASSANDRA_PORT_CHECK": "0", "CASSANDRA_ROOTS": "<fix>/apps", "CASSANDRA_HUB_URL": "http://127.0.0.1:1", "PYTHONUTF8": "1"}
VOLATILE_KEYS = {"started_at", "db_bytes", "took_ms", "last_tick_ms"}
# Optional arguments Talos added on purpose to tools the original already had.
ADDITIVE_ARGUMENTS: dict = {"sites_watch": ["seo_interval_h", "seo_drop_points"]}
DOWN_WORDS = ()
APPS = {"borges": 5184, "scribe": 5185, "vulcan": 5186, "atlas": 5187}


def iso_local(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")


def stamp(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S,123")


def write_manifest(root: Path, app_id: str, port: int):
    app_dir = root / f"{app_id.title()}Hoard"
    app_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": 1, "id": app_id, "name": f"{app_id.title()}'s Hoard", "defaults": {"APP_URL": f"http://127.0.0.1:{port}", "PYTHON": "{FAUSTUS_PYTHON}"},
                "app": {"url_default": f"http://127.0.0.1:{port}", "health": {"path": "/api/health", "expect": {"service": f"{app_id}-hoard"}},
                        "launch_hint": {"kind": "process", "executable": "{PYTHON}", "argv": ["-m", app_id], "cwd": "{" + app_id.upper() + "_DIR}"}}}
    (app_dir / "faustus-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (app_dir / "data").mkdir(exist_ok=True)
    (app_dir / "data" / "mcp-token").write_text("x" * 40, encoding="utf-8")
    return app_dir


def build_fixtures(out: Path):
    apps = out / "apps"
    for app_id, port in APPS.items():
        write_manifest(apps, app_id, port)
    (apps / "BorgesHoard" / ".gitignore").write_text("data/\n", encoding="utf-8")
    (apps / "ScribeHoard" / ".env").write_text("TOKEN=abc\n", encoding="utf-8")


def _fakes():
    import httpx
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse, PlainTextResponse
    from cassandra_hoard.gpu import GpuSample
    from cassandra_hoard.procs import ProcInfo

    class FakeService:
        def __init__(self, service):
            self.service, self.mode = service, "up"
            app = FastAPI()

            @app.get("/{path:path}")
            def health(path: str):
                if self.mode == "down":
                    raise RuntimeError("connection refused")
                if self.mode == "degraded":
                    return JSONResponse({"service": self.service}, status_code=503)
                if self.mode == "foreign":
                    return PlainTextResponse("<html>something else</html>")
                return {"service": self.service, "status": "ok", "models": [], "system": {}}
            self.app = app

    class FakeNet(httpx.AsyncBaseTransport):
        def __init__(self):
            self.apps = {}

        def add(self, port, service):
            self.apps[port] = FakeService(service)
            return self.apps[port]

        async def handle_async_request(self, request):
            fake = self.apps.get(request.url.port)
            if fake is None:
                raise httpx.ConnectError("refused", request=request)
            return await httpx.ASGITransport(app=fake.app).handle_async_request(request)

    class FakeSiteNet:
        def __init__(self):
            self.http = {"status": 200, "latency_ms": 120.0, "redirect": None, "final_url": "", "body": "<html>Welcome to the shop</html>", "error": None}
            self.dns = {"ok": True, "addresses": ["203.0.113.10"], "error": None}
            self.tls = {"ok": True, "chain_valid": True, "hostname_match": True, "not_after": T0 + 80 * 86400, "not_before": T0 - 10 * 86400, "days_left": 80,
                        "issuer": "Example CA (E1)", "subject": "example.com", "san": ["example.com"], "fingerprint": "fp-one", "error": None}

        def http_fn(self, url, *, timeout=15.0, follow=False, transport=None):
            return dict(self.http)

        def tls_fn(self, host, port=443, **kwargs):
            return dict(self.tls)

        def dns_fn(self, host, port=443, **kwargs):
            return dict(self.dns)

        def fail(self, kind, detail):
            self.http = {**self.http, "status": None, "latency_ms": None, "body": None, "error": {"kind": kind, "detail": detail}}

        def respond(self, status=200, body="<html>Welcome to the shop</html>", latency=120.0):
            self.http = {**self.http, "status": status, "latency_ms": latency, "body": body, "redirect": None, "error": None}

    return httpx, FakeService, FakeNet, FakeSiteNet, GpuSample, ProcInfo


class FakeClock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def build_base(out: Path, fixtures: Path):
    import httpx
    from cassandra_hoard.audit import BusMirror
    from cassandra_hoard.config import Config
    from cassandra_hoard.services import Services
    httpx_, FakeService, FakeNet, FakeSiteNet, GpuSample, ProcInfo = _fakes()
    apps_root = fixtures / "apps"
    net, sitenet, clock = FakeNet(), FakeSiteNet(), FakeClock(T0)
    for app_id in ("borges", "scribe", "vulcan"):
        net.add(APPS[app_id], f"{app_id}-hoard")
    pids = {APPS[a]: 1000 + APPS[a] for a in ("borges", "scribe", "vulcan")}
    gpu = {"samples": [GpuSample(0, 2000, 24000, 5.0), GpuSample(1, 1000, 12000, 0.0)]}
    logs = out.parent / "applogs"
    logs.mkdir(parents=True, exist_ok=True)
    log_files = {a: logs / f"{a}.log" for a in ("borges", "scribe", "vulcan")}
    globs = [f"{a}={p}" for a, p in log_files.items()]
    config = Config(data_dir=out, roots=[str(apps_root)], externals=False, gpu=True, autostart=False, default_logs=False, log_globs=globs, data_dir_configured=True,
                    poll_s=20.0, sample_every_s=60.0, hub_registry=False, retention_days=3650)
    no_hub = lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(599)))

    def spawn(cmd, cwd, log_path, env=None):
        class Child:
            pid = 4242
        return Child()
    svc = Services(
        config, clock_fn=clock,
        poller_kwargs=dict(transport=net, listeners_fn=lambda: {p: pid for p, pid in pids.items() if net.apps[p].mode != "down"},
                           proc_fn=lambda pid: ProcInfo(pid, name="python.exe", cmdline=f"python -m app{pid}", started=T0 - 100 - pid),
                           alive_fn=lambda pid, started=None: None, boot_fn=lambda: T0 - 3600, gpu_reader=lambda: list(gpu["samples"]), restart_async=False),
        restarter_kwargs=dict(hub_client=no_hub(), spawn=spawn, stop_fn=lambda pid, started=None: {"ok": True}),
        registry_kwargs=dict(hub_client=no_hub()),
        sites_kwargs=dict(http_fn=sitenet.http_fn, tls_fn=sitenet.tls_fn, dns_fn=sitenet.dns_fn, rdap_client=no_hub()),
    )

    def tick(adv=20.0):
        clock.advance(adv)
        return svc.poller.tick()

    def log(app, ts, text):
        with open(log_files[app], "a", encoding="utf-8") as fh:
            fh.write(f"{stamp(ts)} {text}\n")
    try:
        for n in range(3):
            log("borges", T0 + n, "INFO borges started and serving")
            log("scribe", T0 + n, "INFO scribe ready")
            log("vulcan", T0 + n, "INFO vulcan ready")
        for _ in range(4):
            tick()
        # borges crashes: errors in its log, nothing listens
        crash = clock.now + 5
        log("borges", crash, "ERROR unhandled exception in worker")
        log("borges", crash + 1, "Traceback (most recent call last):")
        log("borges", crash + 2, "ValueError: model file missing")
        net.apps[APPS["borges"]].mode = "down"
        tick(); tick(); tick()
        # the scribe answers 503 for a while, vulcan answers as another program
        log("scribe", clock.now + 3, "WARNING queue is growing")
        net.apps[APPS["scribe"]].mode = "degraded"
        net.apps[APPS["vulcan"]].mode = "foreign"
        gpu["samples"] = [GpuSample(0, 21000, 24000, 97.0), GpuSample(1, 1500, 12000, 3.0)]
        tick(); tick()
        # borges comes back with another pid; vulcan stops answering altogether
        pids[APPS["borges"]] = 7001
        net.apps[APPS["borges"]].mode = "up"
        net.apps[APPS["scribe"]].mode = "up"
        net.apps[APPS["vulcan"]].mode = "down"
        gpu["samples"] = [GpuSample(0, 4000, 24000, 12.0), GpuSample(1, 9000, 12000, 55.0)]
        tick(); tick()
        pids[APPS["scribe"]] = 7002   # a restart that nobody reported
        net.apps[APPS["vulcan"]].mode = "up"
        tick(); tick(); tick(60)
        # the family bus, mirrored from a fake hub
        events = [
            ("agent.call", "vulcan", {"tool": "models_search", "ok": True, "ms": 120, "caller": "hub"}, T0 + 100),
            ("agent.call", "vulcan", {"tool": "model_listing_set", "ok": False, "ms": 30, "error": "no such model", "caller": "faustus"}, T0 + 130),
            ("agent.call", "scribe", {"tool": "scribe_search", "ok": True, "ms": 45, "caller": "faustus"}, T0 + 140),
            ("scribe.transcript.done", "scribe", {"session_id": 7}, T0 + 150),
            ("hub.backup.done", "hub", {"snapshot": "daily"}, T0 + 160),
            ("agent.call", "borges", {"tool": "borges_open", "ok": False, "ms": 900, "error": "boom", "caller": "faustus"}, T0 + 100 + 85),
        ]
        hub_events = [{"id": i + 1, "ts": ts, "type": t, "source": s, "data": d} for i, (t, s, d, ts) in enumerate(events)]

        def handler(request):
            since = int(request.url.params.get("since_id", 0))
            batch = [e for e in hub_events if e["id"] > since]
            return httpx.Response(200, json={"ok": True, "last_id": hub_events[-1]["id"], "events": batch})
        mirror = BusMirror(svc.db, "http://hub.test", clock_fn=clock, client=httpx.Client(transport=httpx.MockTransport(handler)), incidents=svc.incidents,
                           service_kind=lambda sid: (svc.registry.get(sid).kind if svc.registry.get(sid) else None))
        mirror.sync_once()
        # public sites
        svc.sites.store.upsert({"url": "https://example.com/", "keyword": "Welcome"})
        svc.sites.store.upsert({"url": "https://shop.example.org/", "name": "Tienda", "interval_min": 10})
        svc.sites.store.upsert({"url": "https://old.example.net/", "enabled": False})
        shop = svc.sites.store.find("shop.example.org")
        main = svc.sites.store.find("example.com")
        clock.advance(30)
        svc.sites.check(main); svc.sites.check(shop)
        sitenet.fail("timeout", "Timeout: no answer within 15 s")
        clock.advance(300); svc.sites.check(shop)
        clock.advance(60); svc.sites.check(shop)
        sitenet.respond(200)
        clock.advance(300); svc.sites.check(shop); svc.sites.check(main)
        assert clock.now < NOW_SERVE - 600, clock.now
    finally:
        svc.stop()


def prepare_old():
    _install()


def prepare_talos():
    _install()


def _install():
    """Both servers get the same fixed clock and fake engines: the poller, the bus mirror and the site watcher are off and nothing reaches the real PC."""
    import httpx
    import cassandra_hoard.main as main_module
    from cassandra_hoard.procs import ProcInfo
    real = main_module.Services

    def no_hub():
        return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(599)))

    def spawn(cmd, cwd, log_path, env=None):
        class Child:
            pid = 4242
        return Child()

    def build(config, *args, **kwargs):
        sitenet = _fakes()[3]()
        extra = dict(
            clock_fn=lambda: NOW_SERVE,
            poller_kwargs=dict(listeners_fn=lambda: {}, proc_fn=lambda pid: None, alive_fn=lambda pid, started=None: None, boot_fn=lambda: None, restart_async=False),
            restarter_kwargs=dict(hub_client=no_hub(), spawn=spawn, stop_fn=lambda pid, started=None: {"ok": True}),
            registry_kwargs=dict(hub_client=no_hub()),
            sites_kwargs=dict(http_fn=sitenet.http_fn, tls_fn=sitenet.tls_fn, dns_fn=sitenet.dns_fn, rdap_client=no_hub()),
        )
        return real(config, *args, **{**extra, **kwargs})
    main_module.Services = build


def helpers(tmp: Path, fix: Path):
    """A fake Faustus on a private port: the token decides what it answers."""
    import http.server
    farm = {
        "schema": 1, "generated_at": NOW_SERVE,
        "counts": {"total": 3, "roots": 2, "by_kind": {"chat_run": 1, "worker": 1, "dispatch_job": 1}, "by_state": {"running": 2, "stalled": 1}},
        "items": [
            {"id": "run:s1", "kind": "chat_run", "title": "Refactor the importer", "parent": None, "state": "running", "started_at": NOW_SERVE - 600,
             "last_event_at": NOW_SERVE - 4, "model": "qwen-9b", "progress": {"percent": 40.0, "unit": "plan"}, "link": "/studio?s=s1", "phase": "tool", "tool": "read_file",
             "children": [{"id": "worker:c1", "kind": "worker", "title": "reader", "parent": "run:s1", "state": "stalled", "started_at": NOW_SERVE - 300,
                           "last_event_at": NOW_SERVE - 200, "model": None, "progress": None, "link": None, "children": []}]},
            {"id": "job:j1", "kind": "dispatch_job", "title": "Port the parser", "parent": None, "state": "running", "started_at": NOW_SERVE - 90,
             "last_event_at": NOW_SERVE - 2, "model": "local-27b", "progress": {"done": 1, "total": 2, "unit": "tasks", "percent": 50.0}, "link": None, "children": []}],
        "budget": {"enabled": True, "window": "week", "window_resets_at": NOW_SERVE + 5000, "interactive_active": True,
                   "providers": [{"provider": "hosted", "metric": "usd", "window": "week", "used": 2.5, "target": 10.0, "used_fraction": 0.25, "pace_fraction": 0.3,
                                  "pace_allowed": 3.0, "paused": False, "paused_until": None, "reason": "ok", "resets_at": NOW_SERVE + 5000}],
                   "gpu": {"provider": "local", "metric": "gpu_seconds", "window": "day", "used": 120.0, "target": 600, "used_fraction": 0.2, "pace_fraction": 0.5,
                           "pace_allowed": 300.0, "paused": False, "paused_until": None},
                   "breaker": {"enabled": True, "open": True, "consecutive_failures": 3, "threshold": 3, "reopens_at": NOW_SERVE + 900, "last_failure_kind": "dispatch"},
                   "cooldowns": [{"endpoint": "api.example.com", "status": 429, "until": NOW_SERVE + 120, "hits": 2}]}}
    attention = {"unread_count": 2, "runs": [
        {"session_id": "s-a", "label": "Revisar factura", "kind": "approval", "since": NOW_SERVE - 40 * 60, "next_action": "approve or deny", "detail": "write_file"},
        {"session_id": "s-b", "label": "Plan semanal", "kind": "question", "since": NOW_SERVE - 3 * 60, "next_action": "answer"},
        {"session_id": "s-c", "label": "Tarea larga", "kind": "disconnected", "since": NOW_SERVE - 25 * 60, "next_action": "check"},
        {"session_id": "s-d", "label": "Informe", "kind": "finished_unreviewed", "since": None}]}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            token = self.headers.get("Authorization", "").replace("Bearer ", "")
            path = self.path.split("?")[0]
            if token == "tok-bad":
                return self.reply(403, {"error": "forbidden"})
            if path == "/api/attention" and token in ("tok-attn", "tok-farm"):
                return self.reply(200, attention)
            if path == "/api/farm/state" and token == "tok-farm":
                return self.reply(200, farm)
            return self.reply(403 if token else 401, {"error": "scope"})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return {"CASSANDRA_FAUSTUS_URL": f"http://127.0.0.1:{server.server_port}"}, server.shutdown


def _dir(data: Path) -> Path:
    return data if (data / "cassandra.db").exists() else data / TALOS_ID


def tok_bad(fix, data, saved):
    (_dir(data) / "faustus-token").write_text("tok-bad", encoding="utf-8")


def tok_attention(fix, data, saved):
    (_dir(data) / "faustus-token").write_text("tok-attn", encoding="utf-8")


def tok_farm(fix, data, saved):
    (_dir(data) / "faustus-farm-token").write_text("tok-farm", encoding="utf-8")


TOOLS = ["svc_status", "svc_incidents", "svc_why_down", "logs_search", "gpu_timeline", "svc_history", "audit_search", "audit_stats", "secrets_audit", "faustus_attention",
         "faustus_farm", "sites_status", "site_history", "svc_restart", "svc_watch", "sites_watch"]
BORGES_DOWN = iso_local(T0 + 4 * 20 + 20 + 5)


def cases():
    c = [{"tool": "tools", "list_tools": TOOLS, "additive": ADDITIVE_ARGUMENTS}]

    def add(tool, args=None, **kw):
        c.append({"tool": tool, "args": args or {}, **kw})
    at_crash = iso_local(T0 + 4 * 20 + 6)
    # --- status ---
    add("svc_status")
    for who in ("borges", "Scribe's Hoard", "5186", "atlas", "ATLAS", "nope", ""):
        add("svc_status", {"service": who})
    # --- incidents / why ---
    for args in ({}, {"open_only": True}, {"service": "borges"}, {"service": "vulcan"}, {"service": "scribe"}, {"service": "atlas"}, {"limit": 1}, {"at": at_crash, "window_min": 5},
                 {"at": at_crash, "window_min": 0}, {"since": "10h", "until": "1h"}, {"since": "30m"}, {"since": "1d"}, {"service": "nope"}, {"at": "no-time"}, {"limit": 0}, {"window_min": 5000}):
        add("svc_incidents", args)
    for args in ({"service": "borges"}, {"service": "vulcan"}, {"service": "scribe"}, {"service": "atlas"}, {"service": "borges", "incident_id": 1}, {"service": "borges", "incident_id": 999},
                 {"service": "vulcan", "incident_id": 1}, {"service": "nope"}, {}):
        add("svc_why_down", args)
    # --- logs ---
    for args in ({}, {"query": "Traceback"}, {"query": "model file"}, {"level": "error"}, {"level": "warning"}, {"level": "info", "limit": 2}, {"service": "borges"}, {"service": "scribe", "level": "warning"},
                 {"at": at_crash, "window_min": 2}, {"query": "zzz-no-existe"}, {"service": "nope"}, {"level": "fatal"}, {"limit": 1}, {"since": "10h", "until": "1h"}):
        add("logs_search", args)
    # --- gpu / history ---
    for args in ({}, {"gpu": 0}, {"gpu": 1}, {"gpu": 7}, {"points": 4}, {"at": at_crash, "window_min": 60}, {"since": "10h"}, {"points": 3}):
        add("gpu_timeline", args)
    for args in ({"service": "borges"}, {"service": "scribe"}, {"service": "vulcan", "since": "10h"}, {"service": "atlas"}, {"service": "nope"}, {"service": "borges", "at": at_crash, "window_min": 3}, {}):
        add("svc_history", args)
    # --- bus ---
    for args in ({}, {"type": "agent.call"}, {"failed": True}, {"tool": "models_search"}, {"source": "scribe"}, {"query": "snapshot"}, {"type": "scribe.*|hub.*"}, {"limit": 2},
                 {"at": iso_local(T0 + 130), "window_min": 1}, {"since": "10h", "until": "1h"}, {"type": "zzz"}):
        add("audit_search", args)
    for args in ({}, {"since": "10h"}, {"since": "10h", "until": "1h"}, {"at": iso_local(T0 + 130), "window_min": 5}):
        add("audit_stats", args)
    # --- secrets (fixture folders, no git repository) ---
    for args in ({}, {"service": "borges"}, {"service": "scribe"}, {"service": "atlas"}, {"service": "nope"}):
        add("secrets_audit", args)
    # --- Faustus (a fake one; the token decides) ---
    add("faustus_attention"); add("faustus_farm")
    add("faustus_attention", {"wait_min": 5}, setup="tok_bad"); add("faustus_farm", {}, setup="tok_bad")
    add("faustus_attention", {"wait_min": 10}, setup="tok_attention"); add("faustus_attention", {"wait_min": 1}); add("faustus_attention", {"wait_min": 100}); add("faustus_attention", {"wait_min": -1})
    add("faustus_farm", {}, sleep=1.2); add("faustus_farm", {"include_budget": False}, sleep=1.2)
    add("faustus_farm", {}, setup="tok_farm", sleep=1.2); add("faustus_farm", {"include_budget": False}, sleep=1.2); add("faustus_attention", {})
    # --- public sites ---
    add("sites_status")
    for who in ("example.com", "shop.example.org", "Tienda", "old.example.net", "https://example.com/", "site:example.com", "nope", ""):
        add("sites_status", {"site": who})
    for args in ({"site": "example.com"}, {"site": "shop.example.org"}, {"site": "shop.example.org", "since": "10h"}, {"site": "shop.example.org", "at": iso_local(T0 + 4 * 20 + 20 + 2 * 20 + 6 * 20), "window_min": 600},
                 {"site": "old.example.net"}, {"site": "nope"}, {}):
        add("site_history", args)
    # --- writes (all against the copy of the data) ---
    add("svc_restart", {"service": "borges"}); add("svc_restart", {"service": "vulcan"}); add("svc_restart", {"service": "atlas"}); add("svc_restart", {"service": "nope"}); add("svc_restart", {})
    add("svc_status", {"service": "borges"}); add("svc_incidents", {"service": "borges"}); add("svc_why_down", {"service": "borges"})
    add("svc_watch", {"id": "demo", "url": "http://127.0.0.1:9", "name": "Demo", "health_path": "/health", "expect": {"ok": "*"}})
    add("svc_status", {"service": "demo"}); add("svc_watch", {"id": "demo", "name": "Demo 2"}); add("svc_watch", {"id": "demo", "restart": {"enabled": True, "max_per_hour": 2}})
    add("svc_watch", {"id": "demo", "restart": {"cmd": "echo hola"}}); add("svc_watch", {"id": "Bad Id!", "url": "http://127.0.0.1:9"}); add("svc_watch", {"id": "nuevo"})
    add("svc_watch", {"id": "borges", "name": "Borges renombrado", "log_paths": ["<fix>/apps/BorgesHoard/data/logs/*.log"]}); add("svc_watch", {"id": "x", "url": "http://example.com:99999"})
    add("svc_watch", {}); add("svc_status", {"service": "borges"}); add("svc_status")
    add("sites_watch", {"action": "add", "url": "https://nuevo.example.com/", "keyword": "Hola", "interval_min": 15})
    add("sites_watch", {"action": "add", "url": "https://nuevo.example.com/"}); add("sites_watch", {"action": "add"}); add("sites_watch", {"action": "add", "url": "ftp://x"})
    add("sites_watch", {"action": "edit", "id": "nuevo.example.com", "interval_min": 30, "enabled": False, "expect_status": ["200", "301"]})
    add("sites_watch", {"action": "edit", "id": "nope"}); add("sites_watch", {"action": "edit", "id": "nuevo.example.com", "interval_min": 0.5}); add("sites_watch", {"action": "edit"})
    add("sites_watch", {"action": "remove", "id": "nuevo.example.com"}); add("sites_watch", {"action": "remove", "id": "nuevo.example.com"}); add("sites_watch", {"action": "remove"})
    add("sites_watch", {"action": "borrar", "id": "x"}); add("sites_watch", {"action": "remove", "id": "old.example.net"})
    add("sites_status"); add("svc_incidents", {"since": "10h"})
    add("no_such_tool", {}, loose=True)
    return c


def mutate():
    """A deliberate regression in Talos's copy: the history of every service loses its uptime."""
    import cassandra_hoard.views as views
    views.uptime_pct = lambda *a, **k: -1.0
