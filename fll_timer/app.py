from __future__ import annotations

import sys

from PySide6.QtCore import QDir, QLockFile
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import theme
from .audio import SoundPlayer
from .control import ControlWindow
from .model import AppModel
from .obsws import ObsClient
from .webserver import Hub, StateBridge, WebServer


_activity = None  # keep a reference so the activity token isn't released


def _disable_app_nap() -> None:
    """Stop macOS from throttling this app when its windows are covered or in the
    background, so OBS keeps receiving frames from the presentation window."""
    global _activity
    try:
        from Foundation import NSProcessInfo
        user_initiated = 0x00EFFFFF            # NSActivityUserInitiatedAllowingIdleSystemSleep
        latency_critical = 0xFF00000000        # NSActivityLatencyCritical
        _activity = NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
            user_initiated | latency_critical, "Live timer output for OBS")
    except Exception:
        pass


def main() -> int:
    _disable_app_nap()
    app = QApplication(sys.argv)
    # One copy only: a second copy would grab a different port and break the OBS URLs.
    lock = QLockFile(QDir.temp().filePath("fll_timer.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        print("FLL Timer is already running.")
        return 0
    app.setApplicationName("FLL Timer")
    app.setWindowIcon(QIcon(str(theme.LOGO_PATH)))

    model = AppModel()
    sounds = SoundPlayer(app)
    sounds.volume, sounds.muted = model.volume, model.muted

    # Sounds are played for the table that is on air.
    def on_event(index: int, kind: str) -> None:
        if index != model.current_index:
            return
        if kind in ("beep", "voice") and model.countdown_audio != kind:
            return
        # The spoken countdown recording already ends with the horn, so don't play it twice
        # (unless that recording isn't installed, in which case use the plain horn).
        voice_ok = sounds.available("voice")
        if kind == "voice" and not voice_ok:
            return
        if kind == "start" and model.countdown_audio == "voice" and model.countdown > 0 and voice_ok:
            return
        sounds.play(kind)
    model.matchEvent.connect(on_event)

    hub = Hub()
    server = WebServer(hub)
    server.start()
    bridge = StateBridge(model, hub)   # noqa: F841  (kept alive by this reference)

    # OBS WebSocket: lets the app know which scene is live (optional; off until enabled in the panel).
    obs = ObsClient(server.port, app)
    obs.updated.connect(model.set_obs_state)
    model.configChanged.connect(lambda: obs.configure(
        model.obs_enabled, model.obs_host, model.obs_port, model.obs_password))
    app.aboutToQuit.connect(obs.shutdown)
    obs.configure(model.obs_enabled, model.obs_host, model.obs_port, model.obs_password)

    controls = ControlWindow(model, sounds, server.url)
    controls.move(60, 80)
    controls.show()
    return app.exec()
