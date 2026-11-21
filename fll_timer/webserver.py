"""Local web server that feeds the OBS Browser Source.

The Qt model is the single source of truth. Every change is pushed to all
connected browser sources over Server-Sent Events, with a 1 s heartbeat that
re-syncs clocks. The browser counts time locally between messages, so the
display stays smooth and keeps running even if a message is late.
"""
from __future__ import annotations

import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import QObject, QTimer, Signal

from .model import AppModel
from .theme import ROOT

WEB_DIR = ROOT / "web"
ASSETS = {"/assets/bioglow_logo.png": (ROOT / "assets" / "bioglow_logo.png", "image/png")}
PORTS = range(8765, 8786)


class Hub:
    """Thread-safe fan-out of state messages to SSE clients.

    `on_active(table_id, active)` is called (from a server thread) when an OBS
    Browser Source reports that it is on / off program.
    """

    def __init__(self) -> None:
        self.on_active = lambda tid, active: None
        self._clients: set[queue.Queue] = set()
        self._lock = threading.Lock()
        self.latest = "{}"

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=64)
        with self._lock:
            self._clients.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._clients.discard(q)

    def publish(self, text: str) -> None:
        self.latest = text
        with self._lock:
            clients = list(self._clients)
        for q in clients:
            try:
                q.put_nowait(text)
            except queue.Full:       # slow client: drop old messages, keep newest
                try:
                    q.get_nowait()
                    q.put_nowait(text)
                except (queue.Empty, queue.Full):
                    pass


def make_handler(hub: Hub):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FLLTimer"

        def log_message(self, *args) -> None:
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            try:
                if path == "/" or path.startswith("/t/") or path == "/index.html":
                    self._send(200, (WEB_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
                elif path in ASSETS:
                    f, ctype = ASSETS[path]
                    self._send(200, f.read_bytes(), ctype)
                elif path == "/state":
                    self._send(200, hub.latest.encode(), "application/json")
                elif path == "/events":
                    self._events()
                else:
                    self._send(404, b"not found", "text/plain")
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self) -> None:
            if self.path.split("?", 1)[0] != "/active":
                self._send(404, b"not found", "text/plain")
                return
            try:
                n = min(int(self.headers.get("Content-Length", 0)), 4096)
                data = json.loads(self.rfile.read(n) or b"{}")
                hub.on_active(str(data["id"]), bool(data["active"]))
                self._send(204, b"", "text/plain")
            except (ValueError, KeyError, TypeError):
                self._send(400, b"bad request", "text/plain")
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _events(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            q = hub.subscribe()
            try:
                self.wfile.write(f"data: {hub.latest}\n\n".encode())
                self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=10)
                        self.wfile.write(f"data: {msg}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                hub.unsubscribe(q)

    return Handler


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class WebServer:
    def __init__(self, hub: Hub):
        self.hub = hub
        self.httpd = None
        handler = make_handler(hub)
        for port in PORTS:
            try:
                self.httpd = _Server(("127.0.0.1", port), handler)   # local machine only
                self.port = port
                break
            except OSError:
                continue
        if self.httpd is None:
            raise RuntimeError("No free port between 8765 and 8785 for the OBS page")

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start(self) -> None:
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


class StateBridge(QObject):
    """Publishes the model to the hub on every change (plus a 1 s heartbeat) and
    relays OBS on-air reports from the server threads back onto the Qt thread."""

    _reported = Signal(str, bool)

    def __init__(self, model: AppModel, hub: Hub):
        super().__init__()
        self.model, self.hub = model, hub
        self._pending = False
        # Server threads emit this signal; Qt queues it onto the main thread.
        self._reported.connect(model.report_active)
        hub.on_active = self._reported.emit
        for sig in (model.tablesChanged, model.configChanged, model.matchEvent):
            sig.connect(self._schedule)
        self._beat = QTimer(self)
        self._beat.setInterval(1000)
        self._beat.timeout.connect(self._publish)
        self._beat.start()
        self._publish()

    def _schedule(self, *_args) -> None:     # coalesce bursts of signals into one message
        if not self._pending:
            self._pending = True
            QTimer.singleShot(0, self._publish)

    def _publish(self) -> None:
        self._pending = False
        m = self.model
        state = {"tables": [{
            "id": t.id,
            "name": m.display_name(i),
            "state": t.clock.state,
            "duration": t.clock.duration,
            "endgame": t.clock.endgame,
            "lead": t.clock.lead,
            "remaining": round(t.clock.countdown_remaining() if t.clock.state == "countdown"
                               else t.clock.remaining(), 4),
            "run": t.clock.run_id,
        } for i, t in enumerate(m.tables)]}
        self.hub.publish(json.dumps(state))
