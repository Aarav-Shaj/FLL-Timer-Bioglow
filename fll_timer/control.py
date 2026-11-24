"""Operator control panel."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFontDatabase, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget)

from . import theme
from .audio import SOUNDS, SoundPlayer
from .model import COUNTDOWN, RUNNING, AppModel, format_time

QSS = f"""
QPushButton[role="seg"] {{ border: 1px solid palette(mid); border-radius: 9px; padding: 8px 16px;
                          font-weight: 600; background: transparent; }}
QPushButton[role="seg"]:checked {{ background: {theme.FOREST.name()}; color: white;
                                  border-color: {theme.FOREST.name()}; }}
QPushButton[role="seg"][air="true"] {{ border: 2px solid {theme.RED.name()}; }}
QPushButton[role="tool"] {{ border: 1px solid palette(mid); border-radius: 9px; padding: 8px 12px;
                           font-weight: 700; background: transparent; }}
QPushButton[role="primary"] {{ background: {theme.LEAF.name()}; color: white; border: none;
                              border-radius: 14px; padding: 18px; font-size: 20px; font-weight: 800; }}
QPushButton[role="primary"][running="true"] {{ background: {theme.RED.name()}; }}
QPushButton[role="secondary"] {{ border: 1px solid palette(mid); border-radius: 14px; padding: 18px;
                                font-size: 16px; font-weight: 700; background: transparent; }}
QLabel[role="caption"] {{ color: palette(text); font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
"""


def caption(text: str) -> QLabel:
    lab = QLabel(text.upper())
    lab.setProperty("role", "caption")
    return lab


def hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFrameShadow(QFrame.Shadow.Plain)
    f.setStyleSheet("color: palette(mid);")
    return f


class ControlWindow(QWidget):
    def __init__(self, model: AppModel, sounds: SoundPlayer, base_url: str):
        super().__init__()
        self.model, self.sounds, self.base_url = model, sounds, base_url
        self.setWindowTitle("FLL Timer - Controls")
        self.setStyleSheet(QSS)
        self.setFixedWidth(460)
        self._building = False

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 22)
        root.setSpacing(12)

        # tables
        root.addWidget(caption("Table"))
        self.seg_row = QHBoxLayout()
        self.seg_row.setSpacing(8)
        root.addLayout(self.seg_row)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Name this table (shown on stream)")
        self.name_edit.textEdited.connect(lambda _t: self._update_save_state())
        self.name_edit.returnPressed.connect(self._save_name)
        self._name_id: str | None = None          # table whose name the field is showing
        name_row = QHBoxLayout()
        name_row.addWidget(self.name_edit, 1)
        self.save_btn = self._button("Save", "tool", self._save_name)
        name_row.addWidget(self.save_btn)
        root.addLayout(name_row)

        # readout
        self.readout = QLabel("2:30")
        f = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        f.setPixelSize(64)
        f.setWeight(f.Weight.Bold)
        self.readout.setFont(f)
        self.readout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status = QLabel("Ready")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setProperty("role", "caption")
        root.addWidget(self.readout)
        root.addWidget(self.status)

        row = QHBoxLayout()
        self.go = self._button("Start", "primary", model.toggle_match)
        self.go.setMinimumWidth(240)
        row.addWidget(self.go, 2)
        row.addWidget(self._button("Reset", "secondary", model.reset), 1)
        root.addLayout(row)
        root.addWidget(hline())

        # match timing
        root.addWidget(caption("Match timing"))
        t = QHBoxLayout()
        self.min_spin, self.sec_spin, self.eg_spin = QSpinBox(), QSpinBox(), QSpinBox()
        self.min_spin.setRange(0, 9); self.min_spin.setSuffix(" min")
        self.sec_spin.setRange(0, 59); self.sec_spin.setSuffix(" sec")
        self.eg_spin.setRange(0, 300); self.eg_spin.setSuffix(" s")
        t.addWidget(QLabel("Length")); t.addWidget(self.min_spin); t.addWidget(self.sec_spin)
        t.addStretch(1)
        t.addWidget(QLabel("End game at")); t.addWidget(self.eg_spin)
        root.addLayout(t)
        for sp in (self.min_spin, self.sec_spin, self.eg_spin):
            sp.valueChanged.connect(self._timing_edited)
        cd = QHBoxLayout()
        self.cd_spin = QSpinBox()
        self.cd_spin.setRange(0, 10); self.cd_spin.setSuffix(" s"); self.cd_spin.setSpecialValueText("Off")
        self.cd_audio = QComboBox()
        for key, label in (("voice", "Spoken 3-2-1"), ("beep", "Beeps"), ("none", "Silent")):
            self.cd_audio.addItem(label, key)
        cd.addWidget(QLabel("Countdown")); cd.addWidget(self.cd_spin)
        cd.addStretch(1); cd.addWidget(QLabel("Audio")); cd.addWidget(self.cd_audio)
        root.addLayout(cd)
        self.cd_spin.valueChanged.connect(self._countdown_edited)
        self.cd_audio.currentIndexChanged.connect(self._countdown_edited)
        root.addWidget(hline())

        # sounds
        root.addWidget(caption("Sounds"))
        s = QHBoxLayout()
        self.sound_box = QComboBox()
        for key, (label, desc, _f) in SOUNDS.items():
            self.sound_box.addItem(label, key)
        s.addWidget(self.sound_box, 1)
        play = self._button("Play", "tool", lambda: sounds.play(self.sound_box.currentData(), force=True))
        s.addWidget(play)
        s.addWidget(self._button("Stop", "tool", sounds.stop_all))
        root.addLayout(s)
        self.sound_desc = QLabel()
        self.sound_desc.setProperty("role", "caption")
        root.addWidget(self.sound_desc)
        self.sound_box.currentIndexChanged.connect(
            lambda: self.sound_desc.setText(SOUNDS[self.sound_box.currentData()][1]))
        self.sound_desc.setText(SOUNDS[self.sound_box.currentData()][1])
        v = QHBoxLayout()
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.mute = QCheckBox("Mute match sounds")
        v.addWidget(QLabel("Volume")); v.addWidget(self.volume, 1); v.addWidget(self.mute)
        root.addLayout(v)
        self.volume.valueChanged.connect(self._sound_edited)
        self.mute.toggled.connect(self._sound_edited)
        root.addWidget(hline())

        # OBS output
        root.addWidget(caption("OBS Browser Source for this table"))
        u = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setReadOnly(True)
        u.addWidget(self.url_edit, 1)
        u.addWidget(self._button("Copy", "tool", self._copy_url))
        u.addWidget(self._button("Preview", "tool",
                                 lambda: QDesktopServices.openUrl(QUrl(self._table_url()))))
        root.addLayout(u)
        self.follow = QCheckBox("Follow OBS: select the table whose source goes on air")
        self.follow.toggled.connect(lambda on: None if self._building else model.set_follow_obs(on))
        root.addWidget(self.follow)
        # OBS WebSocket connection
        root.addWidget(hline())
        root.addWidget(caption("OBS connection (WebSocket)"))
        self.obs_on = QCheckBox("Connect to OBS to know which scene is live")
        self.obs_on.toggled.connect(self._obs_edited)
        root.addWidget(self.obs_on)
        o = QHBoxLayout()
        self.obs_host = QLineEdit(); self.obs_host.setPlaceholderText("127.0.0.1")
        self.obs_port = QSpinBox(); self.obs_port.setRange(1, 65535)
        self.obs_pw = QLineEdit(); self.obs_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.obs_pw.setPlaceholderText("Password")
        o.addWidget(self.obs_host, 3); o.addWidget(QLabel(":")); o.addWidget(self.obs_port, 2)
        o.addWidget(self.obs_pw, 3)
        root.addLayout(o)
        for w in (self.obs_host, self.obs_pw):
            w.editingFinished.connect(self._obs_edited)
        self.obs_port.editingFinished.connect(self._obs_edited)
        self.obs_status = QLabel()
        self.obs_status.setWordWrap(True)
        root.addWidget(self.obs_status)
        obs_hint = QLabel("In OBS: Tools > WebSocket Server Settings > enable it, set a password.")
        obs_hint.setProperty("role", "caption"); obs_hint.setWordWrap(True)
        root.addWidget(obs_hint)

        self.air_label = QLabel()
        self.air_label.setProperty("role", "caption")
        root.addWidget(self.air_label)
        hint = QLabel("Space start / abort   R reset   Cmd+1-9 select table")
        hint.setProperty("role", "caption")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._shortcuts(self)
        model.tablesChanged.connect(self._rebuild_tables)
        model.changed.connect(self._refresh)
        self._load_config()
        self._rebuild_tables()
        self._refresh()

    # -- helpers -----------------------------------------------------------
    def _button(self, text, role, slot) -> QPushButton:
        b = QPushButton(text)
        b.setProperty("role", role)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # keep Space for start/abort
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda *_: slot())
        return b

    def _shortcuts(self, w: QWidget) -> None:
        def bind(seq, fn):
            QShortcut(QKeySequence(seq), w, activated=fn)
        bind("Space", self.model.toggle_match)
        bind("R", self.model.reset)
        for n in range(1, 10):
            bind(f"Ctrl+{n}", lambda n=n: self.model.select(n - 1))

    def _save_name(self) -> None:
        self.model.rename(self.model.current_index, self.name_edit.text().strip())
        self.name_edit.clearFocus()

    def _update_save_state(self) -> None:
        self.save_btn.setEnabled(self.name_edit.text().strip() != self.model.current.name)

    def _table_url(self) -> str:
        return f"{self.base_url}t/{self.model.current.id}"

    def _copy_url(self) -> None:
        QGuiApplication.clipboard().setText(self._table_url())

    def closeEvent(self, e) -> None:
        self.sounds.stop_all()
        super().closeEvent(e)

    # -- state sync --------------------------------------------------------
    def _load_config(self) -> None:
        m = self.model
        self._building = True
        self.min_spin.setValue(m.duration // 60)
        self.sec_spin.setValue(m.duration % 60)
        self.eg_spin.setValue(m.endgame)
        self.cd_spin.setValue(m.countdown)
        self.cd_audio.setCurrentIndex(max(0, self.cd_audio.findData(m.countdown_audio)))
        self.volume.setValue(m.volume)
        self.mute.setChecked(m.muted)
        self.follow.setChecked(m.follow_obs)
        self.obs_on.setChecked(m.obs_enabled)
        self.obs_host.setText(m.obs_host)
        self.obs_port.setValue(m.obs_port)
        self.obs_pw.setText(m.obs_password)
        self._building = False
        self.sounds.volume, self.sounds.muted = m.volume, m.muted

    def _timing_edited(self) -> None:
        if self._building:
            return
        total = self.min_spin.value() * 60 + self.sec_spin.value()
        self.model.set_timing(max(total, 1), self.eg_spin.value())

    def _obs_edited(self) -> None:
        if not self._building:
            self.model.set_obs_config(self.obs_on.isChecked(), self.obs_host.text(),
                                      self.obs_port.value(), self.obs_pw.text())

    def _countdown_edited(self) -> None:
        if self._building:
            return
        audio = self.cd_audio.currentData()
        if audio == "voice" and 0 < self.cd_spin.value() < 3:
            self.cd_spin.setValue(3)          # the recorded voice is 3 s long
            return                            # (setValue re-enters this method)
        self.model.set_countdown(self.cd_spin.value(), audio)

    def _sound_edited(self) -> None:
        if self._building:
            return
        self.model.set_sound(self.volume.value(), self.mute.isChecked())
        self.sounds.volume, self.sounds.muted = self.volume.value(), self.mute.isChecked()

    def _rebuild_tables(self) -> None:
        m = self.model
        while self.seg_row.count():
            item = self.seg_row.takeAt(0)
            if item.widget():
                self.group.removeButton(item.widget())
                item.widget().deleteLater()
        air = m.on_air_ids()
        for i, t in enumerate(m.tables):
            dot = "● " if t.clock.state == RUNNING else ""
            b = QPushButton(dot + m.display_name(i))
            b.setProperty("role", "seg")
            b.setProperty("air", "true" if t.id in air else "false")
            b.setCheckable(True)
            b.setChecked(i == m.current_index)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _c=False, i=i: m.select(i))
            self.group.addButton(b)
            self.seg_row.addWidget(b)
        self.seg_row.addStretch(1)
        self.seg_row.addWidget(self._button("+", "tool", m.add_table))
        rm = self._button("−", "tool", m.remove_current)
        rm.setEnabled(len(m.tables) > 1)
        self.seg_row.addWidget(rm)
        # Switching tables always loads that table's name (discarding unsaved edits);
        # otherwise leave what the operator is typing alone until they Save.
        if self._name_id != m.current.id:
            self._name_id = m.current.id
            self.name_edit.setText(m.current.name)
        self._update_save_state()
        self.url_edit.setText(self._table_url())
        names = [m.display_name(i) for i, t in enumerate(m.tables) if t.id in air]
        scene = f" (live scene: {m.obs_scene})" if m.obs_connected and m.obs_scene else ""
        self.air_label.setText("ON AIR IN OBS: " + (", ".join(names) if names else "none") + scene)
        if m.obs_connected:
            self.obs_status.setText(f"\u25CF Connected - live scene: {m.obs_scene or '?'}")
            self.obs_status.setStyleSheet(f"color: {theme.LEAF.name()}; font-weight: 700;")
        else:
            self.obs_status.setText(f"\u25CB {m.obs_message}" + ("  (using page reports instead)" if m.obs_enabled else ""))
            self.obs_status.setStyleSheet("")
        self._refresh()

    def _refresh(self) -> None:
        c = self.model.current.clock
        self.readout.setText(str(c.display_seconds()) if c.state == COUNTDOWN
                             else format_time(c.display_seconds()))
        running = c.state in (RUNNING, COUNTDOWN)
        self.go.setText("Abort" if running else "Start")
        self.go.setProperty("running", "true" if running else "false")
        self.go.style().unpolish(self.go)
        self.go.style().polish(self.go)
        self.status.setText({"idle": "READY", "countdown": "GET READY", "run": "MATCH IN PROGRESS",
                             "endgame": "END GAME", "final": "FINAL SECONDS",
                             "done": "MATCH COMPLETE"}[c.phase()])
