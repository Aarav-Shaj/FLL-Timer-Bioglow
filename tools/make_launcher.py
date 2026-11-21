#!/usr/bin/env python3
"""Build a double-clickable "FLL Timer.app" (default: on the Desktop).

    .venv/bin/python tools/make_launcher.py [destination-folder]

Re-run it if you move this project folder.
"""
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPixmap

ROOT = Path(__file__).resolve().parent.parent
dest = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path.home() / "Desktop"
app = dest / "FLL Timer.app"

# ---- icon: official logo (unaltered) centred on a dark rounded square -------------
QGuiApplication(sys.argv[:1])
size = 1024
img = QImage(size, size, QImage.Format.Format_ARGB32)
img.fill(Qt.GlobalColor.transparent)
p = QPainter(img)
p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
path = QPainterPath()
path.addRoundedRect(QRectF(60, 60, size - 120, size - 120), 190, 190)
p.fillPath(path, QColor("#0C1317"))
logo = QPixmap(str(ROOT / "assets" / "bioglow_logo.png"))
w = (size - 120) * 0.80
h = w * logo.height() / logo.width()
p.drawPixmap(QRectF((size - w) / 2, (size - h) / 2, w, h), logo, QRectF(logo.rect()))
p.end()

tmp = Path(tempfile.mkdtemp())
big = tmp / "icon.png"
img.save(str(big))
iconset = tmp / "icon.iconset"
iconset.mkdir()
for s in (16, 32, 128, 256, 512):
    for scale in (1, 2):
        px = s * scale
        name = f"icon_{s}x{s}{'@2x' if scale == 2 else ''}.png"
        subprocess.run(["sips", "-z", str(px), str(px), str(big), "--out", str(iconset / name)],
                       check=True, capture_output=True)
subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(tmp / "icon.icns")], check=True)

# ---- bundle ------------------------------------------------------------------------
if app.exists():
    shutil.rmtree(app)
(app / "Contents" / "MacOS").mkdir(parents=True)
(app / "Contents" / "Resources").mkdir()
shutil.copy(tmp / "icon.icns", app / "Contents" / "Resources" / "icon.icns")
with open(app / "Contents" / "Info.plist", "wb") as f:
    plistlib.dump({
        "CFBundleName": "FLL Timer", "CFBundleDisplayName": "FLL Timer",
        "CFBundleIdentifier": "local.fll-timer.launcher", "CFBundleVersion": "1.0",
        "CFBundlePackageType": "APPL", "CFBundleExecutable": "launch",
        "CFBundleIconFile": "icon", "LSMinimumSystemVersion": "11.0",
    }, f)

launcher = app / "Contents" / "MacOS" / "launch"
launcher.write_text(f'''#!/bin/zsh
# Opens the FLL Timer control panel (or brings it to the front if it's already running).
PROJECT={str(ROOT)!r}
PY="$PROJECT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  osascript -e 'display alert "FLL Timer" message "Run ./run.command once in the project folder to set it up."'
  exit 1
fi
if pgrep -f "[P]ython -m fll_timer$" > /dev/null; then
  PYAPP="$("$PY" -c 'import sys; print(sys.base_prefix)')/Resources/Python.app"
  open "$PYAPP"          # already running: just bring it forward
  exit 0
fi
cd "$PROJECT"
exec "$PY" -m fll_timer
''')
launcher.chmod(0o755)
subprocess.run(["touch", str(app)])
print("Created", app)
