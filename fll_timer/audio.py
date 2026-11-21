"""Match sound effects, played through macOS afplay (no extra dependencies)."""
from __future__ import annotations

from PySide6.QtCore import QObject, QProcess

from .theme import SOUNDS_DIR

# key -> (label, description, file)
SOUNDS = {
    "voice":   ("Countdown + start", "Spoken 3, 2, 1 then the horn (one 3 s + horn recording)", "countdown_start.wav"),
    "start":   ("Match start", "Horn only, when the match begins", "start.wav"),
    "endgame": ("End game", "Plays with 30 seconds left", "end_game.wav"),
    "end":     ("Match end", "Final buzzer at 0:00", "end.wav"),
    "abort":   ("Abort", "Plays when a match is aborted", "cancel.wav"),
    "beep":    ("Countdown beep", "Short tone on 3, 2, 1 (generated, not an official sound)", "beep.wav"),
}


class SoundPlayer(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.volume = 80
        self.muted = False
        self._procs: list[QProcess] = []

    def play(self, key: str, force: bool = False) -> None:
        """Play a sound, cutting off anything still playing so sounds never overlap.
        `force` bypasses mute (used by the preview button)."""
        if self.muted and not force:
            return
        self.stop_all()
        path = SOUNDS_DIR / SOUNDS[key][2]
        if not path.exists():
            return
        proc = QProcess(self)
        proc.finished.connect(lambda *_: self._reap(proc))
        proc.start("/usr/bin/afplay", ["-v", f"{max(0, self.volume) / 100:.2f}", str(path)])
        self._procs.append(proc)

    def available(self, key: str) -> bool:
        return (SOUNDS_DIR / SOUNDS[key][2]).exists()

    def stop_all(self) -> None:
        for p in list(self._procs):
            p.kill()

    def _reap(self, proc: QProcess) -> None:
        if proc in self._procs:
            self._procs.remove(proc)
        try:
            proc.deleteLater()
        except RuntimeError:       # already destroyed during shutdown
            pass
