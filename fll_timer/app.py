from __future__ import annotations

import sys

from PySide6.QtCore import QDir, QLockFile
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import theme
from .audio import SoundPlayer
from .control import ControlWindow
from .model import AppModel
from .webserver import Hub, StateBridge, WebServer


def _keep_running_in_background() -> None:
    """Windows 11 can throttle timers of background/minimised apps (EcoQoS) and the default
    timer tick is ~15 ms. Opt out of both so the clocks stay accurate while OBS has focus."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class PowerThrottling(ctypes.Structure):
            _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG),
                        ("StateMask", wintypes.ULONG)]

        state = PowerThrottling(1, 1, 0)          # EXECUTION_SPEED controlled, throttling OFF
        kernel32 = ctypes.windll.kernel32
        kernel32.SetProcessInformation(kernel32.GetCurrentProcess(), 4,   # ProcessPowerThrottling
                                       ctypes.byref(state), ctypes.sizeof(state))
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass


def main() -> int:
    _keep_running_in_background()
    app = QApplication(sys.argv)
    # One copy only: a second copy would grab a different port and break the OBS URLs.
    lock = QLockFile(QDir.temp().filePath("fll_timer.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None, "FLL Timer", "FLL Timer is already running.")
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

    controls = ControlWindow(model, sounds, server.url)
    controls.move(60, 80)
    controls.show()
    return app.exec()
