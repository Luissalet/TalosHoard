"""ASGI entry for the incorporated disk engine's complete native HTTP API.

The original request dispatcher runs directly in a worker thread with in-memory
request/response streams. There is no secondary server, socket or subprocess.
"""
import io
import json
from contextlib import asynccontextmanager
from email.message import Message
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from starlette.responses import Response


def create_app(data_dir, port):
    from diskhoard import server as engine
    from diskhoard.hoard_link.copilot_stdlib import CopilotRelay
    engine.ST.port = port
    engine.TOKEN = engine.load_token()
    engine.family.configure("diskhoard", str(data_dir), token_file=str(data_dir / "mcp-token"))
    relay = CopilotRelay("diskhoard", str(data_dir), app_name="Talos's Hoard")
    engine.restore_snapshot()

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if engine.ST.scanner:
                engine.ST.scanner.cancel()
                finish = getattr(engine.ST.scanner, "finish_thread", None)
                if finish:
                    await run_in_threadpool(finish.join)
            for job in list(engine.zipsplit.REGISTRY.jobs.values()):
                job.cancel()
                if job.thread:
                    await run_in_threadpool(job.thread.join)
            for worker in engine.ST.workers:
                await run_in_threadpool(worker.join)

    class Handler(engine.Handler):
        def send_response(self, code, message=None):
            self.code = code

        def send_header(self, name, value):
            self.response_headers[name] = value

        def end_headers(self):
            pass

        def send_error(self, code, message=None, explain=None):
            self._json({"error": message or "Not found"}, code)

    def dispatch(method, path, headers, body):
        handler = Handler.__new__(Handler)
        handler.command, handler.path = method, path
        handler.headers = Message()
        for k, v in headers.items():
            handler.headers[k] = v
        handler.rfile, handler.wfile = io.BytesIO(body), io.BytesIO()
        handler.response_headers, handler.code = {}, 200
        handler.server = SimpleNamespace(copilot=relay)
        if path.split("?", 1)[0] == "/api/quit":
            handler._json({"ok": True})  # Parent disables this module after the response.
        elif method in ("GET", "HEAD"):
            handler.do_GET()
        elif method == "POST":
            handler.do_POST()
        else:
            handler.send_error(405)
        hdr = {k: v for k, v in handler.response_headers.items() if k.lower() != "content-length"}
        return Response(handler.wfile.getvalue(), status_code=handler.code, headers=hdr)

    app = FastAPI(lifespan=lifespan)

    @app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "DELETE"])
    async def route(path: str, request: Request):
        uri = "/" + path + ("?" + request.url.query if request.url.query else "")
        return await run_in_threadpool(dispatch, request.method, uri, dict(request.headers), await request.body())

    return app
