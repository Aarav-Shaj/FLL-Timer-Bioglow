"""OBS WebSocket (v5) client: tells the app which scene is live in OBS and which
tables' Browser Sources are visible in it.

OBS 28+ has the server built in (Tools > WebSocket Server Settings). We connect, read the
scene list, find every Browser Source whose URL is one of our table pages, and follow
scene changes. Runs on its own thread and reports to Qt through the `updated` signal.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import time
import uuid
from urllib.parse import urlparse

import websocket                      # websocket-client
from PySide6.QtCore import QObject, Signal

TABLE_PATH = re.compile(r"^/t/([^/?#]+)")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
RESCAN_EVERY = 20.0                   # seconds: safety net in case an event was missed
DIRTY_EVENTS = {
    "SceneItemEnableStateChanged", "SceneItemCreated", "SceneItemRemoved", "SceneItemListReindexed",
    "SceneCreated", "SceneRemoved", "SceneNameChanged",
    "InputCreated", "InputRemoved", "InputNameChanged", "InputSettingsChanged",
}


class _AuthError(Exception):
    pass


def auth_string(password: str, salt: str, challenge: str) -> str:
    """Authentication string per the obs-websocket 5.x protocol (SHA256 + base64, twice)."""
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


class _Session:
    def __init__(self, ws, stop: threading.Event, app_port: int, emit):
        self.ws, self.stop, self.app_port, self.emit = ws, stop, app_port, emit
        self.events: list[dict] = []
        self.current = ""
        self.live: dict[str, set[str]] = {}      # scene -> table ids visible in it

    # -- protocol ----------------------------------------------------------
    def identify(self, password: str) -> None:
        hello = json.loads(self.ws.recv())
        if hello.get("op") != 0:
            raise OSError("Not an OBS WebSocket server")
        d: dict = {"rpcVersion": 1}
        auth = hello["d"].get("authentication")
        if auth:
            if not password:
                raise _AuthError("OBS needs a password")
            d["authentication"] = auth_string(password, auth["salt"], auth["challenge"])
        self.ws.send(json.dumps({"op": 1, "d": d}))
        try:
            raw = self.ws.recv()               # '' when the server closes the socket on us
        except websocket.WebSocketConnectionClosedException:
            raw = ""
        if not raw or json.loads(raw).get("op") != 2:
            raise _AuthError("Authentication failed")

    def req(self, rtype: str, data: dict | None = None) -> dict:
        rid = str(uuid.uuid4())
        self.ws.send(json.dumps({"op": 6, "d": {"requestType": rtype, "requestId": rid,
                                                "requestData": data or {}}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg["op"] == 7 and msg["d"]["requestId"] == rid:
                if not msg["d"]["requestStatus"]["result"]:
                    raise RuntimeError(f'{rtype}: {msg["d"]["requestStatus"].get("comment", "failed")}')
                return msg["d"].get("responseData") or {}
            if msg["op"] == 5:
                self.events.append(msg["d"])     # handle after this request completes

    # -- scene scanning ---------------------------------------------------
    def table_id(self, item: dict, cache: dict[str, str | None]) -> str | None:
        if item.get("inputKind") != "browser_source":
            return None
        name = item["sourceName"]
        if name not in cache:
            url = self.req("GetInputSettings", {"inputName": name})["inputSettings"].get("url", "")
            u = urlparse(url)
            m = TABLE_PATH.match(u.path or "")
            ok = m and (u.hostname or "") in LOCAL_HOSTS and (u.port or 80) == self.app_port
            cache[name] = m.group(1) if ok else None
        return cache[name]

    def scan(self) -> None:
        data = self.req("GetSceneList")
        self.current = data.get("currentProgramSceneName") or ""
        scenes = [s["sceneName"] for s in data.get("scenes", [])]
        items = {n: self.req("GetSceneItemList", {"sceneName": n}).get("sceneItems", []) for n in scenes}
        groups: dict[str, list] = {}
        cache: dict[str, str | None] = {}

        def visible(scene: str, seen: frozenset) -> set[str]:
            found: set[str] = set()
            if scene in seen:                                   # scene inside itself: stop
                return found
            seen = seen | {scene}
            if scene in items:
                children = items[scene]
            else:                                               # a group
                if scene not in groups:
                    groups[scene] = self.req("GetGroupSceneItemList", {"sceneName": scene}).get("sceneItems", [])
                children = groups[scene]
            for it in children:
                if not it.get("sceneItemEnabled", True):
                    continue
                if it.get("isGroup"):
                    found |= visible(it["sourceName"], seen)
                elif it.get("sourceType") == "OBS_SOURCE_TYPE_SCENE":
                    found |= visible(it["sourceName"], seen)
                else:
                    tid = self.table_id(it, cache)
                    if tid:
                        found.add(tid)
            return found

        self.live = {n: visible(n, frozenset()) for n in scenes}

    def publish(self, message: str = "Connected") -> None:
        self.emit({"connected": True, "message": message, "scene": self.current,
                   "live_ids": sorted(self.live.get(self.current, set())),
                   "scene_tables": {k: sorted(v) for k, v in self.live.items() if v}})

    # -- main loop ----------------------------------------------------------
    def run(self) -> None:
        self.ws.settimeout(5)
        self.scan()
        self.publish()
        self.ws.settimeout(0.5)
        last_scan, dirty_since = time.monotonic(), None
        while not self.stop.is_set():
            try:
                msg = json.loads(self.ws.recv())
                if msg["op"] == 5:
                    self.events.append(msg["d"])
            except websocket.WebSocketTimeoutException:
                pass
            for ev in self.events:
                t = ev.get("eventType")
                if t == "CurrentProgramSceneChanged":
                    self.current = ev["eventData"]["sceneName"]
                    self.publish()
                elif t in DIRTY_EVENTS and dirty_since is None:
                    dirty_since = time.monotonic()
                elif t == "ExitStarted":
                    raise OSError("OBS is closing")
            self.events.clear()
            now = time.monotonic()
            if (dirty_since is not None and now - dirty_since > 0.3) or now - last_scan > RESCAN_EVERY:
                self.ws.settimeout(5)
                self.scan()
                self.publish()
                self.ws.settimeout(0.5)
                last_scan, dirty_since = now, None


class ObsClient(QObject):
    updated = Signal(dict)     # {connected, message, scene, live_ids, scene_tables}

    def __init__(self, app_port: int, parent=None):
        super().__init__(parent)
        self.app_port = app_port
        self._cfg = None
        self._stop: threading.Event | None = None
        self._ws = None

    @staticmethod
    def _state(connected: bool, message: str) -> dict:
        return {"connected": connected, "message": message, "scene": "", "live_ids": [], "scene_tables": {}}

    def configure(self, enabled: bool, host: str, port: int, password: str) -> None:
        cfg = (enabled, host, port, password)
        if cfg == self._cfg:
            return
        self._cfg = cfg
        self.shutdown()
        if not enabled:
            self.updated.emit(self._state(False, "Off"))
            return
        stop = threading.Event()
        self._stop = stop
        self.updated.emit(self._state(False, "Connecting..."))
        threading.Thread(target=self._run, args=(stop, host, port, password), daemon=True).start()

    def shutdown(self) -> None:
        if self._stop:
            self._stop.set()
        ws, self._ws = self._ws, None
        if ws:
            try:
                ws.close()
            except Exception:
                pass

    def _run(self, stop: threading.Event, host: str, port: int, password: str) -> None:
        emit = self.updated.emit
        while not stop.is_set():
            ws = None
            try:
                ws = websocket.create_connection(f"ws://{host}:{port}", timeout=5)
                self._ws = ws
                session = _Session(ws, stop, self.app_port, emit)
                session.identify(password)
                session.run()
                msg = "Disconnected"
            except _AuthError as e:
                msg, delay = f"{e} - check the OBS WebSocket password", 4
            except (OSError, websocket.WebSocketException, RuntimeError, ValueError, KeyError) as e:
                msg = "Can't reach OBS - is the WebSocket server enabled?" if isinstance(e, OSError) else f"OBS error: {e}"
                delay = 3
            else:
                delay = 2
            finally:
                if ws:
                    try:
                        ws.close()
                    except Exception:
                        pass
            if stop.is_set():
                return
            emit(self._state(False, msg))      # tell the panel first, then wait before retrying
            stop.wait(delay)
