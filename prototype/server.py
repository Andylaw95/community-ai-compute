"""Loopback-only HTTP surface and a supervisor for exactly three local workers."""
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .engine import Problem, fields

WEB = Path(__file__).parent / "web"


class Supervisor:
    def __init__(self, coordinator, port):
        self.core, self.port = coordinator, port
        self.token = secrets.token_urlsafe(32)
        self.processes = {}
        self.lock = threading.RLock()

    def start(self, node):
        self.core._node(node)
        with self.lock, self.core.lock:
            existing = self.processes.get(node)
            if existing and existing.poll() is None:
                return {"started": False}
            env = os.environ.copy()
            env["DEMO_WORKER_TOKEN"] = self.token
            process = subprocess.Popen([sys.executable, "-m", "prototype.worker", "--node", node,
                                        "--port", str(self.port)], cwd=Path(__file__).parent.parent,
                                       env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
            self.processes[node] = process
            self.core.nodes[node].update(pid=process.pid, alive=True)
            return {"started": True, "pid": process.pid}

    def stop(self, node):
        self.core._node(node)
        with self.lock:
            process = self.processes.get(node)
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            with self.core.lock:
                self.core.nodes[node]["alive"] = False
            return {"stopped": True}

    def sync(self):
        with self.lock, self.core.lock:
            for node, process in self.processes.items():
                self.core.nodes[node]["alive"] = process.poll() is None

    def close(self):
        for node in self.core.nodes:
            self.stop(node)


def handler_factory(core, supervisor):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CommunityLocalDemo/0.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *args):
            pass

        def guard(self):
            port = self.server.server_port
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
            host = self.headers.get("Host", "")
            if host not in allowed:
                raise Problem(403, "只接受 loopback Host")
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://{host}"}:
                raise Problem(403, "不接受跨來源請求")
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                raise Problem(403, "不接受跨網站請求")

        def reply(self, status, value, mime="application/json; charset=utf-8"):
            data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            try:
                self.guard()
                path = urlsplit(self.path).path
                static = {"/": ("index.html", "text/html; charset=utf-8"),
                          "/app.css": ("app.css", "text/css; charset=utf-8"),
                          "/app.js": ("app.js", "text/javascript; charset=utf-8")}
                if path in static:
                    file, mime = static[path]
                    return self.reply(200, (WEB / file).read_bytes(), mime)
                if path == "/favicon.ico":
                    return self.reply(204, b"", "image/x-icon")
                if path == "/api/state":
                    supervisor.sync()
                    return self.reply(200, core.snapshot())
                parts = path.split("/")
                if len(parts) in (4, 5) and parts[1:3] == ["api", "jobs"]:
                    if len(parts) == 5 and parts[4] == "results":
                        return self.reply(200, core.results(parts[3]))
                    if len(parts) == 4:
                        for job in core.snapshot()["jobs"]:
                            if job["id"] == parts[3]:
                                return self.reply(200, job)
                raise Problem(404, "找不到這個資源")
            except Problem as error:
                self.reply(error.status, {"error": error.message})
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass

        def do_POST(self):
            try:
                self.guard()
                path = urlsplit(self.path).path
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise Problem(415, "只接受 application/json")
                if self.headers.get("Transfer-Encoding"):
                    raise Problem(400, "不接受分塊請求")
                raw_length = self.headers.get("Content-Length", "")
                if not raw_length.isdecimal():
                    raise Problem(411, "需要 Content-Length")
                length = int(raw_length)
                maximum = 262144 if path.startswith("/internal/") else 4096
                if not 0 < length <= maximum:
                    raise Problem(413, "請求內容超出限制")
                try:
                    data = json.loads(self.rfile.read(length), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
                except (ValueError, UnicodeError, RecursionError):
                    raise Problem(400, "無效 JSON")
                if not isinstance(data, dict):
                    raise Problem(400, "JSON 必須是物件")
                if path == "/api/jobs":
                    result = core.submit(data, self.headers.get("Idempotency-Key"))
                    return self.reply(200 if result["duplicate"] else 201, result)
                if path == "/api/policy":
                    return self.reply(200, core.set_policy(data))
                if path == "/api/demo/fault":
                    fields(data, ("node", "mode"))
                    node, mode = data.get("node"), data.get("mode")
                    core._node(node)
                    if mode not in ("exit", "invalid", "replay"):
                        raise Problem(400, "不支援的故障模式")
                    with core.lock:
                        core.nodes[node]["fault"] = mode
                    return self.reply(200, {"queued_fault": mode, "node": node})
                parts = path.split("/")
                if len(parts) == 5 and parts[1:3] == ["api", "nodes"] and parts[4] in ("start", "stop"):
                    fields(data, ())
                    action = supervisor.start if parts[4] == "start" else supervisor.stop
                    return self.reply(200, action(parts[3]))
                if path.startswith("/internal/"):
                    if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + supervisor.token):
                        raise Problem(403, "需要本次執行的工作程序憑證")
                    node = data.pop("node", None)
                    if not isinstance(node, str):
                        raise Problem(400, "需要工作程序名稱")
                    core._node(node)
                    if path == "/internal/claim":
                        fields(data, ())
                        return self.reply(200, core.claim(node))
                    if path == "/internal/control":
                        fields(data, ())
                        return self.reply(200, core.limits())
                    if path in ("/internal/heartbeat", "/internal/release"):
                        fields(data, ("attempt_id",))
                        if not isinstance(data.get("attempt_id"), str):
                            raise Problem(400, "需要 attempt_id")
                        action = core.heartbeat if path.endswith("heartbeat") else core.release
                        return self.reply(200, action(node, data["attempt_id"]))
                    if path == "/internal/result":
                        return self.reply(200, core.accept(node, data))
                raise Problem(404, "找不到這個操作")
            except Problem as error:
                self.reply(error.status, {"error": error.message})
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass
            except Exception as error:
                print(f"Request failed: {type(error).__name__}", file=sys.stderr)
                self.reply(500, {"error": "本機服務錯誤；請查看終端機"})

    return Handler


def make_server(core, port):
    supervisor = Supervisor(core, port)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler_factory(core, supervisor))
    server.daemon_threads = True
    supervisor.port = server.server_port
    return server, supervisor
