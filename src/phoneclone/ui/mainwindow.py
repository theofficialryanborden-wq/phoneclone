from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
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
from phoneclone.adb import AdbClient
from phoneclone.apps import AppManager
from phoneclone.config import EmulatorConfig
from phoneclone.display import DisplayPanel
from phoneclone.qemu import QemuEmulator
from phoneclone.runtime import RuntimeManager
from phoneclone.ui.styles import BLUESTACKS_STYLE
from phoneclone.ui.welcome import WelcomeOverlay


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
        self._boot_display_timer = QTimer(self)
        self._boot_display_timer.setSingleShot(True)
        self._boot_display_timer.timeout.connect(self._connect_display)

        self._build_ui()

        self.welcome = WelcomeOverlay(self)
        self.welcome.setGeometry(self.rect())
        self._wire_runtime()

        if RuntimeManager.is_ready():
            self.welcome.hide()
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
        self._start_android()

    def _on_runtime_failed(self, message: str) -> None:
        self.welcome.start_btn.setEnabled(True)
        QMessageBox.critical(self, "Setup failed", message)

    def _start_android(self) -> None:
        if self.emulator.is_running:
            return
        self.config.apply_bundled_defaults()
        self.emulator.config = self.config
        errors = self.config.validate()
        if errors:
            self.welcome.show()
            self._set_status("Setup required", "#d29922")
            return
        try:
            self.emulator.start()
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, "Could not start Android", str(exc))
            return
        self._set_status("Starting Android…", "#58a6ff")
        self._output_timer.start(300)
        self._boot_display_timer.start(5000)
        self._adb_timer.start(20000)

    def _connect_display(self) -> None:
        self.display.start(self.config.vnc_port)
        self._set_status("Android running", "#3fb950")

    def _restart_android(self) -> None:
        self._stop_android()
        QTimer.singleShot(800, self._start_android)

    def _stop_android(self) -> None:
        self._output_timer.stop()
        self._adb_timer.stop()
        self._boot_display_timer.stop()
        self.display.stop()
        self.emulator.stop()
        self._set_status("Offline", "#8b949e")

    def _poll_qemu(self) -> None:
        if not self.emulator.is_running:
            self._output_timer.stop()
            self.display.stop()
            self._set_status("Android stopped", "#d29922")

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
            QMessageBox.information(self, "Android not running", "Wait for Android to finish starting.")
            return
        self.adb.connect()
        ok = 0
        for path in paths:
            if self.adb.install_apk(path):
                ok += 1
        if ok:
            QMessageBox.information(self, "Installed", f"Installed {ok} app(s). Open them from My Apps.")
            self._refresh_apps()

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
