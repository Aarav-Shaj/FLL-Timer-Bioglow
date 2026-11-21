"""Official BIOGLOW palette (FIRST style guide) + shared helpers."""
from pathlib import Path

from PySide6.QtGui import QColor, QFont

ROOT = Path(__file__).resolve().parent.parent
SOUNDS_DIR = ROOT / "sounds"
LOGO_PATH = ROOT / "assets" / "bioglow_logo.png"

# FIRST BIOGLOW style guide
LIME = QColor("#C6DE94")
LEAF = QColor("#70A334")
FOREST = QColor("#2C5535")
YELLOW = QColor("#F0E973")
INK = QColor("#111921")        # dark used inside the logo artwork
RED = QColor("#E5383B")        # FLL program red
RED_LIGHT = QColor("#FF8A8C")

CHROMA = QColor("#00B140")     # key this out in OBS
BAR = QColor("#0C1317")
TRACK = QColor("#1C2A31")
WHITE = QColor("#FFFFFF")

FONT_FAMILIES = [".AppleSystemUIFont", "SF Pro Display", "Helvetica Neue", "Arial"]


def font(px: float, weight=QFont.Weight.Bold) -> QFont:
    f = QFont()
    f.setFamilies(FONT_FAMILIES)
    f.setPixelSize(max(1, int(px)))
    f.setWeight(weight)
    return f


def lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )
