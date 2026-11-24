"""Match clocks and the multi-table model. No UI code here."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QObject, QSettings, QTimer, Signal

IDLE, COUNTDOWN, RUNNING, DONE = "idle", "countdown", "running", "done"
FINAL_SECONDS = 10
VOICE_SECONDS = 3.0   # length of the spoken "3, 2, 1" recording


class MatchClock:
    """idle -> [countdown ->] running -> done.  The countdown ("3, 2, 1") runs for
    `lead` seconds; the match clock starts exactly when it reaches zero."""

    def __init__(self, duration: int, endgame: int, lead: int = 0):
        self.duration = duration
        self.endgame = endgame
        self.lead = lead
        self.state = IDLE
        self._t0 = 0.0
        self._endgame_fired = False
        self._last_beep = 0
        self._voice_fired = False
        self.run_id = 0  # increments on every start; lets web clients tell runs apart

    def countdown_remaining(self) -> float:
        return max(0.0, self.lead - (time.monotonic() - self._t0)) if self.state == COUNTDOWN else 0.0

    def remaining(self) -> float:
        """Match time left (the full duration while idle or counting down)."""
        if self.state in (IDLE, COUNTDOWN):
            return float(self.duration)
        if self.state == DONE:
            return 0.0
        return max(0.0, self.duration - (time.monotonic() - self._t0))

    def display_seconds(self) -> int:
        if self.state == COUNTDOWN:
            return math.ceil(self.countdown_remaining())
        if self.state == RUNNING:
            return math.ceil(self.remaining())
        return int(round(self.remaining()))

    def start(self) -> None:
        self._endgame_fired = False
        self._last_beep = 0
        self._voice_fired = False
        self.run_id += 1
        self._t0 = time.monotonic()
        self.state = COUNTDOWN if self.lead > 0 else RUNNING

    def reset(self) -> None:
        self.state = IDLE

    def poll(self) -> list[str]:
        """Advance the state machine; returns events: 'beep', 'start', 'endgame', 'end'."""
        events: list[str] = []
        if self.state == COUNTDOWN:
            cd = self.countdown_remaining()
            n = math.ceil(cd)
            if n > 0 and n != self._last_beep:
                self._last_beep = n
                events.append("beep")
            if not self._voice_fired and cd <= VOICE_SECONDS:
                self._voice_fired = True            # the spoken "3, 2, 1" lasts 3 s and ends on "go"
                events.append("voice")
            if cd <= 0:
                self._t0 += self.lead          # match clock continues seamlessly from here
                self.state = RUNNING
                events.append("start")
        if self.state != RUNNING:
            return events
        r = self.remaining()
        if not self._endgame_fired and 0 < self.endgame < self.duration and r <= self.endgame:
            self._endgame_fired = True
            events.append("endgame")
        if r <= 0:
            self.state = DONE
            events.append("end")
        return events

    def phase(self) -> str:
        if self.state == IDLE:
            return "idle"
        if self.state == COUNTDOWN:
            return "countdown"
        if self.state == DONE:
            return "done"
        s = self.display_seconds()
        if s <= FINAL_SECONDS:
            return "final"
        if self.endgame and s <= self.endgame:
            return "endgame"
        return "run"


def format_time(seconds: int) -> str:
    m, s = divmod(max(0, seconds), 60)
    return f"{m}:{s:02d}"


ACTIVE_TTL = 12.0   # seconds an OBS "this source is on air" report stays valid


class Table:
    def __init__(self, tid: str, name: str, clock: MatchClock):
        self.id = tid          # stable; used in the table's OBS URL
        self.name = name
        self.clock = clock


class AppModel(QObject):
    changed = Signal()                 # clock display changed
    tablesChanged = Signal()           # table list / names / selection / on-air changed
    configChanged = Signal()           # durations, sound, follow settings
    matchEvent = Signal(int, str)      # table index, 'start'|'endgame'|'end'|'abort'

    def __init__(self):
        super().__init__()
        self._s = QSettings("FLLTimer", "FLLTimer")
        self.duration = int(self._s.value("duration", 150))
        self.endgame = int(self._s.value("endgame", 30))
        self.volume = int(self._s.value("volume", 80))
        self.muted = int(self._s.value("muted", 0)) == 1
        self.follow_obs = int(self._s.value("follow_obs", 1)) == 1
        self.countdown = int(self._s.value("countdown", 3))      # FLL: "3, 2, 1, go"
        self.countdown_audio = str(self._s.value("countdown_audio", "voice"))  # voice | beep | none
        if self.countdown_audio == "voice" and 0 < self.countdown < VOICE_SECONDS:
            self.countdown = int(VOICE_SECONDS)

        names = self._s.value("tables", ["Table A", "Table B"])
        ids = self._s.value("table_ids", [])
        if isinstance(names, str):
            names = [names]
        if isinstance(ids, str):
            ids = [ids]
        names = [str(n) for n in names] or ["Table A"]
        if len(ids) != len(names):                       # first run / older settings
            ids = [str(i + 1) for i in range(len(names))]
        self._next_id = max(int(self._s.value("next_id", 0)), *(int(i) for i in ids if str(i).isdigit()), 0) + 1
        self.tables = [Table(str(i), n, MatchClock(self.duration, self.endgame, self.countdown))
                       for i, n in zip(ids, names)]
        self.current_index = min(max(int(self._s.value("current", 0)), 0), len(self.tables) - 1)

        # OBS WebSocket (optional): when connected it is the authority on what is on air.
        self.obs_enabled = int(self._s.value("obs_enabled", 0)) == 1
        self.obs_host = str(self._s.value("obs_host", "127.0.0.1"))
        self.obs_port = int(self._s.value("obs_port", 4455))
        self.obs_password = str(self._s.value("obs_password", ""))
        self.obs_connected = False
        self.obs_message = "Off"
        self.obs_scene = ""
        self.obs_live: frozenset[str] = frozenset()
        self.obs_scene_tables: dict[str, list[str]] = {}

        self._active: dict[str, float] = {}              # table id -> last OBS report time
        self._air_snapshot: frozenset[str] = frozenset()

        self._beat = QTimer(self)
        self._beat.setInterval(25)
        self._beat.timeout.connect(self._heartbeat)
        self._beat.start()

    # -- access -----------------------------------------------------------
    @property
    def current(self) -> Table:
        return self.tables[self.current_index]

    def display_name(self, i: int) -> str:
        return self.tables[i].name.strip() or f"Table {i + 1}"

    def index_of(self, tid: str) -> int:
        return next((i for i, t in enumerate(self.tables) if t.id == tid), -1)

    def on_air_ids(self) -> frozenset[str]:
        if self.obs_connected:                      # OBS WebSocket is authoritative
            return self.obs_live
        now = time.monotonic()
        return frozenset(t for t, ts in self._active.items() if now - ts < ACTIVE_TTL)

    # -- OBS focus ----------------------------------------------------------
    def report_active(self, tid: str, active: bool) -> None:
        """Called when a table's OBS Browser Source reports it is (not) on program."""
        was_air = tid in self.on_air_ids()
        if active:
            self._active[tid] = time.monotonic()
        else:
            self._active.pop(tid, None)
        i = self.index_of(tid)
        if active and not was_air and self.follow_obs and i >= 0:
            self.select(i)                               # newly on air -> take focus
        self._notify_air()

    def set_obs_state(self, st: dict) -> None:
        """Called with each update from the OBS WebSocket client."""
        before = self.on_air_ids()
        self.obs_connected = bool(st["connected"])
        self.obs_message = st["message"]
        self.obs_scene = st["scene"]
        self.obs_live = frozenset(st["live_ids"])
        self.obs_scene_tables = st.get("scene_tables", {})
        after = self.on_air_ids()
        if self.follow_obs and after:
            # Prefer a table that just went on air; otherwise, if the selected table is no
            # longer on air, take the first one that is.
            want = (after - before) or (after if self.current.id not in after else frozenset())
            for i, t in enumerate(self.tables):
                if t.id in want:
                    self.select(i)
                    break
        self._air_snapshot = after
        self.tablesChanged.emit()

    def set_obs_config(self, enabled: bool, host: str, port: int, password: str) -> None:
        self.obs_enabled, self.obs_host, self.obs_port, self.obs_password = enabled, host.strip() or "127.0.0.1", port, password
        self._save()
        self.configChanged.emit()

    def _notify_air(self) -> None:
        now = self.on_air_ids()
        if now != self._air_snapshot:
            self._air_snapshot = now
            self.tablesChanged.emit()

    # -- commands ---------------------------------------------------------
    def select(self, i: int) -> None:
        if i == self.current_index or not (0 <= i < len(self.tables)):
            return
        self.current_index = i
        self._save()
        self.tablesChanged.emit()

    def toggle_match(self) -> None:
        i, c = self.current_index, self.current.clock
        if c.state in (RUNNING, COUNTDOWN):
            c.reset()
            self.matchEvent.emit(i, "abort")
        else:
            c.start()
            if c.state == RUNNING:                       # no countdown: start sound right away
                self.matchEvent.emit(i, "start")        # (otherwise poll() emits it at "go")
        self.changed.emit()
        self.tablesChanged.emit()

    def reset(self) -> None:
        self.current.clock.reset()
        self.changed.emit()
        self.tablesChanged.emit()

    def rename(self, i: int, name: str) -> None:
        self.tables[i].name = name
        self._save()
        self.changed.emit()
        self.tablesChanged.emit()

    def add_table(self) -> None:
        n = len(self.tables)
        label = f"Table {chr(65 + n)}" if n < 26 else f"Table {n + 1}"
        self.tables.append(Table(str(self._next_id), label, MatchClock(self.duration, self.endgame, self.countdown)))
        self._next_id += 1
        self.current_index = n
        self._save()
        self.tablesChanged.emit()

    def remove_current(self) -> None:
        if len(self.tables) <= 1:
            return
        i = self.current_index
        self._active.pop(self.tables[i].id, None)
        del self.tables[i]
        self.current_index = min(i, len(self.tables) - 1)
        self._save()
        self.tablesChanged.emit()
        self.changed.emit()

    def set_timing(self, duration: int, endgame: int) -> None:
        self.duration, self.endgame = max(1, duration), max(0, endgame)
        for t in self.tables:
            t.clock.endgame = self.endgame
            if t.clock.state == IDLE:
                t.clock.duration = self.duration
        self._save()
        self.changed.emit()
        self.configChanged.emit()

    def set_countdown(self, seconds: int, audio: str) -> None:
        if audio == "voice" and 0 < seconds < VOICE_SECONDS:
            seconds = int(VOICE_SECONDS)        # the recording is 3 s long and ends on the horn
        self.countdown, self.countdown_audio = max(0, seconds), audio
        for t in self.tables:
            t.clock.lead = self.countdown
        self._save()
        self.configChanged.emit()

    def set_sound(self, volume: int, muted: bool) -> None:
        self.volume, self.muted = volume, muted
        self._save()
        self.configChanged.emit()

    def set_follow_obs(self, on: bool) -> None:
        self.follow_obs = on
        self._save()
        self.configChanged.emit()

    # -- internals --------------------------------------------------------
    def _heartbeat(self) -> None:
        running = False
        for i, t in enumerate(self.tables):
            for ev in t.clock.poll():
                self.matchEvent.emit(i, ev)
                self.tablesChanged.emit()
            running |= t.clock.state in (RUNNING, COUNTDOWN)
        if running:
            self.changed.emit()
        self._notify_air()                               # expire stale OBS reports

    def _save(self) -> None:
        s = self._s
        s.setValue("tables", [t.name for t in self.tables])
        s.setValue("table_ids", [t.id for t in self.tables])
        s.setValue("next_id", self._next_id)
        s.setValue("current", self.current_index)
        s.setValue("duration", self.duration)
        s.setValue("endgame", self.endgame)
        s.setValue("volume", self.volume)
        s.setValue("muted", 1 if self.muted else 0)
        s.setValue("follow_obs", 1 if self.follow_obs else 0)
        s.setValue("countdown", self.countdown)
        s.setValue("obs_enabled", 1 if self.obs_enabled else 0)
        s.setValue("obs_host", self.obs_host)
        s.setValue("obs_port", self.obs_port)
        s.setValue("obs_password", self.obs_password)
        s.setValue("countdown_audio", self.countdown_audio)
