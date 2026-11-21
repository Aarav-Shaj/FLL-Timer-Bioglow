# FLL Timer (BIOGLOW) - Windows

A match timer for FIRST LEGO League streams. A small control panel runs the clocks, and each table
shows up in OBS as its own Browser Source (the BIOGLOW bottom-bar timer on a chroma-green background).

- Per-table OBS URLs, e.g. `http://127.0.0.1:8765/t/1`
- **Follow OBS:** the panel selects whichever table's source is on air, so Start/Abort act on the right table
- Configurable countdown ("3, 2, 1, go"), match length and end-game time
- Match sounds that cut each other off (no overlap)

## Run (Windows 10/11)
1. Install Python 3.10 or newer from https://www.python.org/downloads/ (tick **Add python.exe to PATH**).
2. Double-click **`run.bat`**. The first run creates `.venv` and installs PySide6 (a few hundred MB).
3. Optional: double-click **`make_shortcut.bat`** to put an "FLL Timer" icon on your Desktop.

If Windows Firewall asks about Python, you can click Cancel: the app only listens on `127.0.0.1` (this PC).

## OBS setup
1. In the panel, **Copy** the URL for a table.
2. OBS: add a **Browser** source, paste the URL, width 1920, height 1080.
3. Add a **Chroma Key** filter (the background is green), or append `?bg=transparent` to the URL instead.
4. Leave "Shutdown source when not visible" and "Refresh browser when scene becomes active" **off**.
5. Add one source per table, one in each camera scene. Keep **Follow OBS** ticked in the panel.

Sounds play on the computer running the app. To put them on stream, add an OBS audio capture source
(Audio Output Capture).

> This Windows version was ported from the macOS branch and has not been tested on a Windows PC yet.

See `THIRD_PARTY_NOTICES.md` for sound and logo attributions.
