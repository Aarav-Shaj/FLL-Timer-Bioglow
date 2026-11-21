"""Match sound effects (Qt Multimedia: works on Windows, with volume and instant stop)."""
from __future__ import annotations

from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QSoundEffect

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
        self._effects: dict[str, QSoundEffect] = {}
        for key, (_label, _desc, filename) in SOUNDS.items():
            path = SOUNDS_DIR / filename
            if path.exists():
                effect = QSoundEffect(self)
                effect.setSource(QUrl.fromLocalFile(str(path)))
                self._effects[key] = effect

    def available(self, key: str) -> bool:
        return key in self._effects

    def play(self, key: str, force: bool = False) -> None:
        """Play a sound, cutting off anything still playing so sounds never overlap.
        `force` bypasses mute (used by the preview button)."""
        if self.muted and not force:
            return
        effect = self._effects.get(key)
        if effect is None:
            return
        self.stop_all()
        effect.setVolume(max(0, min(100, self.volume)) / 100)
        effect.play()

    def stop_all(self) -> None:
        for effect in self._effects.values():
            effect.stop()
