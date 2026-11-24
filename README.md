# FLL Timer (BIOGLOW) - macOS

A match timer for FIRST LEGO League streams. A small control panel runs the clocks, and each table
shows up in OBS as its own Browser Source (the BIOGLOW bottom-bar timer on a chroma-green background).

- Per-table OBS URLs, e.g. `http://127.0.0.1:8765/t/1`
- **Follow OBS:** the panel selects whichever table's source is on air, so Start/Abort act on the right table
- **OBS WebSocket (optional):** the app asks OBS which scene is live and which table sources are in it, including
  nested scenes and groups. Without it, the table pages report when they go on air.
- Configurable countdown ("3, 2, 1, go"), match length and end-game time
- Match sounds that cut each other off (no overlap)

## Run (macOS)
Needs Python 3.10+.

```bash
./run.command          # first run creates .venv and installs PySide6
.venv/bin/python tools/make_launcher.py   # optional: puts "FLL Timer.app" on your Desktop
```

## OBS setup
1. In the panel, **Copy** the URL for a table.
2. OBS: add a **Browser** source, paste the URL, width 1920, height 1080.
3. Add a **Chroma Key** filter (the background is green), or append `?bg=transparent` to the URL instead.
4. Leave "Shutdown source when not visible" and "Refresh browser when scene becomes active" **off**.
5. Add one source per table, one in each camera scene. Keep **Follow OBS** ticked in the panel.

### Optional: OBS WebSocket
In OBS: **Tools > WebSocket Server Settings**, tick *Enable WebSocket server*, set a password (default port 4455).
In the panel, tick **Connect to OBS**, enter the password. The panel then shows the live scene, and
**Follow OBS** selects the table whose source is visible in it. The password is stored in plain text in the
app's settings.

Sounds play on the computer running the app. To put them on stream, add an OBS audio capture source.

See `THIRD_PARTY_NOTICES.md` for sound and logo attributions.
