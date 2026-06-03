from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QApplication,
)
from phoneclone.adb import AdbClient, find_adb
from phoneclone.apps import AppManager
from phoneclone.config import EmulatorConfig
from phoneclone.display import DisplayPanel
from phoneclone.qemu import QemuEmulator
from phoneclone.runtime import RuntimeManager
from phoneclone.ui.styles import BLUESTACKS_STYLE
from phoneclone.ui.welcome import WelcomeOverlay


class _AdbBootstrapWorker(QThread):
    finished_ok = Signal()
    failed = Signal(str)

    def run(self) -> None:
        try:
            from phoneclone.downloads import download_platform_tools

            download_platform_tools()
            self.finished_ok.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class SettingsDialog(QDialog):
    def __init__(self, config: EmulatorConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(460)
        self._config = config

        self.ram_spin = QSpinBox()
        self.ram_spin.setRange(1024, 16384)
        self.ram_spin.setSuffix(" MB")
        self.ram_spin.setValue(config.ram_mb)
        self.cpu_spin = QSpinBox()
        self.cpu_spin.setRange(1, 16)
        self.cpu_spin.setValue(config.cpu_cores)
        self.whp_check = QCheckBox("Hardware acceleration (WHPX)")
        self.whp_check.setChecked(config.use_whp)
        self.auto_start = QCheckBox("Start Android when PhoneClone opens")
        self.auto_start.setChecked(config.auto_start)
        self.gpu_combo = QComboBox()
        for key, label in QemuEmulator.GPU_MODES.items():
            self.gpu_combo.addItem(label, key)
        idx = self.gpu_combo.findData(config.gpu_mode)
        if idx >= 0:
            self.gpu_combo.setCurrentIndex(idx)

        form = QFormLayout()
        form.addRow("RAM", self.ram_spin)
        form.addRow("CPU cores", self.cpu_spin)
        form.addRow("GPU", self.gpu_combo)
        form.addRow("", self.whp_check)
        form.addRow("", self.auto_start)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def apply(self) -> EmulatorConfig:
        self._config.ram_mb = self.ram_spin.value()
        self._config.cpu_cores = self.cpu_spin.value()
        self._config.use_whp = self.whp_check.isChecked()
        self._config.auto_start = self.auto_start.isChecked()
        self._config.gpu_mode = self.gpu_combo.currentData()
        return self._config


class BlueStacksWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PhoneClone")
        self.resize(1280, 800)
        self.setStyleSheet(BLUESTACKS_STYLE)

        self.config = EmulatorConfig.load()
        self.config.apply_bundled_defaults()
        if not self.config.qemu_path:
            self.config.qemu_path = QemuEmulator.find_qemu()

        self.runtime = RuntimeManager()
        self.emulator = QemuEmulator(self.config)
        self.adb = AdbClient(self.config.adb_port)
        self.apps = AppManager(self.adb)

        self._output_timer = QTimer(self)
        self._output_timer.timeout.connect(self._poll_qemu)
        self._adb_timer = QTimer(self)
        self._adb_timer.setSingleShot(True)
        self._adb_timer.timeout.connect(self._on_adb_ready)
        self._vnc_retry_timer = QTimer(self)
        self._vnc_retry_timer.timeout.connect(self._connect_display)
        self._vnc_connected = False
        self._qemu_error_shown = False
        self._qemu_recent_errors: list[str] = []
        self._adb_worker: _AdbBootstrapWorker | None = None

        self._build_ui()

        self.welcome = WelcomeOverlay(self)
        self.welcome.setGeometry(self.rect())
        self._wire_runtime()

        self.display.status_changed.connect(self._on_display_status)

        if RuntimeManager.is_ready():
            self.welcome.hide()
            self._ensure_adb_tools()
            if self.config.auto_start:
                QTimer.singleShot(400, self._start_android)
        else:
            self.welcome.show()
            self._set_status("Setup required", "#d29922")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "welcome"):
            self.welcome.setGeometry(self.rect())

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 20, 12, 20)
        side_layout.setSpacing(4)

        brand = QLabel("PhoneClone")
        brand.setObjectName("brand")
        side_layout.addWidget(brand)
        side_layout.addSpacing(16)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        nav_items = (
            ("home", "Home"),
            ("apps", "My Apps"),
            ("install", "Install APK"),
        )
        self._nav_buttons: dict[str, QPushButton] = {}
        for key, text in nav_items:
            btn = QPushButton(text)
            btn.setProperty("class", "nav")
            btn.setCheckable(True)
            btn.setStyleSheet(BLUESTACKS_STYLE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.nav_group.addButton(btn)
            self._nav_buttons[key] = btn
            side_layout.addWidget(btn)
            btn.clicked.connect(lambda checked, k=key: checked and self._show_page(k))

        side_layout.addStretch()
        settings_btn = QPushButton("Settings")
        settings_btn.setProperty("class", "nav")
        settings_btn.setStyleSheet(BLUESTACKS_STYLE)
        settings_btn.clicked.connect(self._open_settings)
        side_layout.addWidget(settings_btn)

        # Main content
        content = QVBoxLayout()
        content.setContentsMargins(16, 16, 16, 16)
        content.setSpacing(12)

        top = QHBoxLayout()
        self.status_label = QLabel("Offline")
        self.status_label.setObjectName("status")
        top.addWidget(self.status_label)
        top.addStretch()
        self.install_top_btn = QPushButton("Install APK")
        self.install_top_btn.setProperty("class", "primary")
        self.install_top_btn.setStyleSheet(BLUESTACKS_STYLE)
        self.install_top_btn.clicked.connect(self._install_apk)
        top.addWidget(self.install_top_btn)
        content.addLayout(top)

        body = QHBoxLayout()
        self.stack = QStackedWidget()

        # Home — Android display
        home = QWidget()
        home_layout = QVBoxLayout(home)
        home_layout.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("displayFrame")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        self.display = DisplayPanel()
        self.display.files_dropped.connect(self._on_apk_dropped)
        frame_layout.addWidget(self.display)
        home_layout.addWidget(frame, stretch=1)

        nav_bar = QHBoxLayout()
        for text, slot in (("Back", self.adb.back), ("Home", self.adb.home), ("Recents", self.adb.recent_apps)):
            b = QPushButton(text)
            b.setProperty("class", "action")
            b.setStyleSheet(BLUESTACKS_STYLE)
            b.clicked.connect(slot)
            nav_bar.addWidget(b)
        nav_bar.addStretch()
        restart_btn = QPushButton("Restart Android")
        restart_btn.setProperty("class", "action")
        restart_btn.setStyleSheet(BLUESTACKS_STYLE)
        restart_btn.clicked.connect(self._restart_android)
        nav_bar.addWidget(restart_btn)
        home_layout.addLayout(nav_bar)

        # My Apps
        apps_page = QWidget()
        apps_layout = QVBoxLayout(apps_page)
        apps_header = QHBoxLayout()
        apps_header.addWidget(QLabel("Installed apps"))
        apps_header.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setProperty("class", "action")
        refresh_btn.setStyleSheet(BLUESTACKS_STYLE)
        refresh_btn.clicked.connect(self._refresh_apps)
        apps_header.addWidget(refresh_btn)
        apps_layout.addLayout(apps_header)
        self.app_list = QListWidget()
        self.app_list.itemDoubleClicked.connect(self._launch_selected_app)
        apps_layout.addWidget(self.app_list)
        launch_btn = QPushButton("Open selected app")
        launch_btn.setProperty("class", "primary")
        launch_btn.setStyleSheet(BLUESTACKS_STYLE)
        launch_btn.clicked.connect(self._launch_selected_app)
        apps_layout.addWidget(launch_btn)

        # Install page
        install_page = QWidget()
        install_layout = QVBoxLayout(install_page)
        install_layout.addStretch()
        hint = QLabel(
            "Install Android apps from APK files on your PC.\n\n"
            "Drag and drop APK files onto the Home screen, or use the button below.\n"
            "Android must be running before installing."
        )
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #8b949e; font-size: 14px;")
        install_layout.addWidget(hint)
        big_install = QPushButton("Choose APK to install")
        big_install.setProperty("class", "primary")
        big_install.setStyleSheet(BLUESTACKS_STYLE)
        big_install.setFixedWidth(260)
        big_install.clicked.connect(self._install_apk)
        install_layout.addWidget(big_install, alignment=Qt.AlignmentFlag.AlignCenter)
        install_layout.addStretch()

        self.stack.addWidget(home)
        self.stack.addWidget(apps_page)
        self.stack.addWidget(install_page)

        body.addWidget(self.stack, stretch=1)
        content.addLayout(body)
        layout.addWidget(sidebar)
        layout.addLayout(content, stretch=1)

        self._nav_buttons["home"].setChecked(True)
        self.stack.setCurrentIndex(0)

    def _wire_runtime(self) -> None:
        self.runtime.progress.connect(self.welcome.update_progress)
        self.runtime.ready.connect(self._on_runtime_ready)
        self.runtime.failed.connect(self._on_runtime_failed)
        self.welcome.get_started.connect(self._begin_setup)

    def _show_page(self, key: str) -> None:
        index = {"home": 0, "apps": 1, "install": 2}.get(key, 0)
        self.stack.setCurrentIndex(index)
        if key == "apps":
            self._refresh_apps()

    def _set_status(self, text: str, color: str = "#8b949e") -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color}; font-size: 12px;")

    def _begin_setup(self) -> None:
        self.welcome.show_downloading()
        self.runtime.ensure()

    def _on_runtime_ready(self) -> None:
        self.config.apply_bundled_defaults()
        if not self.config.qemu_path:
            self.config.qemu_path = QemuEmulator.find_qemu()
        from phoneclone.paths import PhoneClonePaths

        paths = PhoneClonePaths()
        if paths.android_disk.is_file():
            self.config.system_image = str(paths.android_disk)
        self.config.runtime_ready = True
        self.config.setup_complete = True
        self.config.save()
        self.emulator.config = self.config
        self.welcome.hide_overlay()
        self._refresh_adb_client()
        self._start_android()

    def _on_runtime_failed(self, message: str) -> None:
        self.welcome.start_btn.setEnabled(True)
        QMessageBox.critical(self, "Setup failed", message)

    def _refresh_adb_client(self) -> None:
        self.adb = AdbClient(self.config.adb_port)
        self.apps = AppManager(self.adb)

    def _ensure_adb_tools(self) -> None:
        if find_adb():
            self._refresh_adb_client()
            return
        if self._adb_worker and self._adb_worker.isRunning():
            return
        self._set_status("Downloading ADB tools…", "#58a6ff")
        self._adb_worker = _AdbBootstrapWorker()
        self._adb_worker.finished_ok.connect(self._on_adb_tools_ready)
        self._adb_worker.failed.connect(self._on_adb_tools_failed)
        self._adb_worker.start()

    def _on_adb_tools_ready(self) -> None:
        self._refresh_adb_client()
        self._set_status("Ready", "#3fb950")

    def _on_adb_tools_failed(self, message: str) -> None:
        self._set_status("ADB tools missing", "#d29922")
        QMessageBox.warning(
            self,
            "ADB tools",
            f"Could not download ADB tools:\n{message}\n\n"
            "Install Android platform-tools or retry setup.",
        )

    def _prepare_android_launch(self) -> str | None:
        """Free stale QEMU ports and disable broken WHPX. Returns a user-facing warning."""
        from phoneclone.port_util import release_qemu_ports

        # #region agent log
        from phoneclone._agent_debug import agent_log

        stopped = release_qemu_ports(self.config.adb_port, self.config.vnc_port)
        agent_log(
            "mainwindow.py:_prepare_android_launch",
            "port cleanup",
            data={"stopped_pids": stopped, "adb_port": self.config.adb_port, "vnc_port": self.config.vnc_port},
            hypothesis_id="H8",
            run_id="post-fix",
        )
        # #endregion

        warning = ""
        if self.config.use_whp and not QemuEmulator.whpx_available():
            self.config.use_whp = False
            self.config.enable_cpu_pm = False
            if self.config.cpu_mode == "auto":
                self.config.cpu_mode = "qemu64"
            self.config.save()
            self.emulator.config = self.config
            warning = (
                "Hardware acceleration (WHPX) is unavailable on this PC "
                "(Windows may report “not enough space on device” — that refers to the hypervisor, not your disk). "
                "PhoneClone will run using software emulation, which is slower but should work."
            )
        return warning or None

    @staticmethod
    def _friendly_qemu_line(line: str) -> str:
        lower = line.lower()
        if "no space left on device" in lower and "whpx" in lower:
            return (
                "WHPX (Windows hypervisor) failed — the “not enough space on device” message is misleading; "
                "it is not your hard drive. Disable WHPX in Settings or let PhoneClone turn it off automatically."
            )
        if "could not set up host forwarding" in lower or "hostfwd" in lower:
            return (
                "ADB port is already in use (often a leftover qemu-system-x86_64.exe). "
                "Use Restart Android again after PhoneClone clears the old process."
            )
        if "failed to find an available port" in lower and "vnc" in lower:
            return "VNC display port is already in use. Close other emulators or restart PhoneClone."
        return line.strip()

    def _qemu_exit_message(self) -> str:
        hints = [self._friendly_qemu_line(line) for line in self._qemu_recent_errors[-6:]]
        unique: list[str] = []
        for hint in hints:
            if hint and hint not in unique:
                unique.append(hint)
        body = "\n\n".join(unique) if unique else (
            "The Android emulator exited unexpectedly.\n\n"
            "Try Settings → disable WHPX, then Restart Android."
        )
        return body

    def _on_display_status(self, message: str) -> None:
        lower = message.lower()
        if ("connected" in lower and "connecting" not in lower) or "display connected" in lower:
            self._vnc_connected = True
            self._vnc_retry_timer.stop()
            self._set_status("Android running", "#3fb950")
        elif "error" in lower or "disconnected" in lower:
            self._vnc_connected = False
            self._set_status(message, "#d29922")
        elif message:
            self._set_status(message, "#58a6ff")

    def _start_android(self) -> None:
        # #region agent log
        from phoneclone._agent_debug import agent_log

        agent_log(
            "mainwindow.py:_start_android",
            "enter",
            data={"already_running": self.emulator.is_running},
            hypothesis_id="H3",
        )
        # #endregion
        if self.emulator.is_running:
            return
        self.config.apply_bundled_defaults()
        self.emulator.config = self.config
        whpx_warning = self._prepare_android_launch()
        errors = self.config.validate()
        if errors:
            self.welcome.show()
            self._set_status("Setup required", "#d29922")
            QMessageBox.warning(
                self,
                "Setup required",
                "PhoneClone is not ready to start Android yet:\n\n" + "\n".join(f"• {e}" for e in errors),
            )
            return
        if whpx_warning:
            self._set_status("WHPX disabled — starting with software emulation", "#d29922")
        self._qemu_recent_errors.clear()
        try:
            self.emulator.start()
        except (OSError, ValueError, RuntimeError) as exc:
            # #region agent log
            agent_log(
                "mainwindow.py:_start_android",
                "start failed",
                data={"error": str(exc)},
                hypothesis_id="H3",
            )
            # #endregion
            QMessageBox.critical(self, "Could not start Android", str(exc))
            return
        # #region agent log
        agent_log(
            "mainwindow.py:_start_android",
            "qemu started",
            data={
                "qemu_path": self.config.qemu_path,
                "system_image": self.config.system_image,
                "vnc_port": self.config.vnc_port,
                "use_whp": self.config.use_whp,
                "gpu_mode": self.config.gpu_mode,
            },
            hypothesis_id="H3",
        )
        # #endregion
        self._vnc_connected = False
        self._qemu_error_shown = False
        if whpx_warning:
            QMessageBox.information(self, "Hardware acceleration", whpx_warning)
        self._set_status("Starting Android… (first boot may take 1–2 min)", "#58a6ff")
        self._output_timer.start(300)
        self._vnc_retry_timer.start(4000)
        QTimer.singleShot(12000, self._connect_display)
        self._adb_timer.start(25000)

    def _connect_display(self) -> None:
        # #region agent log
        from phoneclone._agent_debug import agent_log

        agent_log(
            "mainwindow.py:_connect_display",
            "attempt",
            data={
                "qemu_running": self.emulator.is_running,
                "vnc_connected": self._vnc_connected,
                "vnc_port": self.config.vnc_port,
            },
            hypothesis_id="H2",
        )
        # #endregion
        if not self.emulator.is_running or self._vnc_connected:
            return
        self.display.start(self.config.qmp_port)

    def _restart_android(self) -> None:
        self._stop_android()
        QTimer.singleShot(800, self._start_android)

    def _stop_android(self) -> None:
        self._output_timer.stop()
        self._adb_timer.stop()
        self._vnc_retry_timer.stop()
        self._vnc_connected = False
        self.display.stop()
        self.emulator.stop()
        from phoneclone.port_util import release_qemu_ports

        release_qemu_ports(self.config.adb_port, self.config.vnc_port)
        self._set_status("Offline", "#8b949e")

    def _poll_qemu(self) -> None:
        # #region agent log
        import time as _time

        from phoneclone._agent_debug import agent_log

        _poll_t0 = _time.perf_counter()
        _lines = 0
        # #endregion
        while True:
            line = self.emulator.read_output_line()
            if not line:
                break
            # #region agent log
            _lines += 1
            # #endregion
            lower = line.lower()
            if any(token in lower for token in ("error", "failed", "could not", "not supported", "space left")):
                self._qemu_recent_errors.append(line.strip())
                self._set_status(self._friendly_qemu_line(line)[:160], "#d29922")
                # #region agent log
                agent_log(
                    "mainwindow.py:_poll_qemu",
                    "qemu error line",
                    data={"line": line.strip()[:200]},
                    hypothesis_id="H6",
                    run_id="post-fix",
                )
                # #endregion
        # #region agent log
        _poll_ms = int((_time.perf_counter() - _poll_t0) * 1000)
        if _poll_ms >= 100 or _lines or not self.emulator.is_running:
            agent_log(
                "mainwindow.py:_poll_qemu",
                "poll done",
                data={
                    "poll_ms": _poll_ms,
                    "lines_read": _lines,
                    "qemu_running": self.emulator.is_running,
                },
                hypothesis_id="H1",
            )
        # #endregion
        if not self.emulator.is_running:
            self._output_timer.stop()
            self._vnc_retry_timer.stop()
            self.display.stop()
            self._set_status("Android stopped", "#d29922")
            if not self._qemu_error_shown:
                self._qemu_error_shown = True
                # #region agent log
                agent_log(
                    "mainwindow.py:_poll_qemu",
                    "qemu exited",
                    data={"errors": self._qemu_recent_errors[-6:]},
                    hypothesis_id="H3",
                    run_id="post-fix",
                )
                # #endregion
                QMessageBox.warning(self, "Android stopped", self._qemu_exit_message())

    def _on_adb_ready(self) -> None:
        if self.emulator.is_running:
            self.adb.connect()

    def _install_apk(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Install APK", "", "APK files (*.apk)")
        if paths:
            self._install_paths(paths)

    def _on_apk_dropped(self, paths: list) -> None:
        apk_paths = [p for p in paths if str(p).lower().endswith(".apk")]
        if apk_paths:
            self._install_paths(apk_paths)

    def _install_paths(self, paths: list) -> None:
        if not self.emulator.is_running:
            QMessageBox.information(
                self,
                "Android not running",
                "Start Android first (Home screen) and wait until the status shows "
                "“Android running”, then try again.",
            )
            return
        if not self.adb.available:
            self._ensure_adb_tools()
            QMessageBox.warning(
                self,
                "ADB not ready",
                "PhoneClone is still downloading ADB tools, or they are missing.\n\n"
                "Wait a moment and try again, or run Get Started setup.",
            )
            return
        self._set_status("Connecting to Android for install…", "#58a6ff")
        if not self.adb.wait_for_device(timeout_sec=60):
            QMessageBox.warning(
                self,
                "Android not ready",
                "Could not reach Android over ADB yet.\n\n"
                "Wait until the Home screen appears (up to 1–2 minutes on first boot). "
                "If the screen stays blank, restart Android from the Home toolbar.",
            )
            self._set_status("ADB not ready", "#d29922")
            return
        ok = 0
        errors: list[str] = []
        for path in paths:
            success, message = self.adb.install_apk(path)
            if success:
                ok += 1
            else:
                name = Path(path).name
                errors.append(f"{name}: {message}")
        if ok:
            QMessageBox.information(self, "Installed", f"Installed {ok} app(s). Open them from My Apps.")
            self._refresh_apps()
            self._set_status("Android running", "#3fb950")
        elif errors:
            QMessageBox.warning(self, "Install failed", "\n\n".join(errors))
            self._set_status("Install failed", "#d29922")

    def _refresh_apps(self) -> None:
        self.app_list.clear()
        if not self.emulator.is_running:
            self.app_list.addItem("Start Android to see installed apps.")
            return
        self.adb.connect()
        for label, package in self.apps.list_user_apps():
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, package)
            self.app_list.addItem(item)
        if self.app_list.count() == 0:
            self.app_list.addItem("No user apps yet — install an APK.")

    def _launch_selected_app(self) -> None:
        item = self.app_list.currentItem()
        if not item:
            return
        package = item.data(Qt.ItemDataRole.UserRole)
        if not package:
            return
        self.adb.connect()
        if self.apps.launch(package):
            self._nav_buttons["home"].setChecked(True)
            self.stack.setCurrentIndex(0)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.apply()
            self.config.save()
            self.emulator.config = self.config

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop_android()
        super().closeEvent(event)


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PhoneClone")
    app.setOrganizationName("PhoneClone")
    app.setFont(QFont("Segoe UI", 10))
    window = BlueStacksWindow()
    window.show()
    return app.exec()
