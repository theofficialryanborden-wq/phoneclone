from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from phoneclone.adb import AdbClient
from phoneclone.config import EmulatorConfig
from phoneclone.display import DisplayPanel
from phoneclone.instances import InstanceManager, InstanceResources
from phoneclone.location import GeocodingError, geocode_address
from phoneclone.qemu import QemuEmulator
from phoneclone.setup_wizard import run_setup_wizard
from phoneclone.spoof import DEVICE_PROFILES, apply_privacy_profile


class SettingsDialog(QDialog):
    def __init__(self, config: EmulatorConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Emulator Settings")
        self.setMinimumWidth(520)
        self._config = config

        self.qemu_path = QLineEdit(config.qemu_path)
        self.image_path = QLineEdit(config.system_image)
        self.template_path = QLineEdit(config.template_image)
        self.ram_spin = QSpinBox()
        self.ram_spin.setRange(512, 16384)
        self.ram_spin.setSuffix(" MB")
        self.ram_spin.setValue(config.ram_mb)
        self.cpu_spin = QSpinBox()
        self.cpu_spin.setRange(1, 16)
        self.cpu_spin.setValue(config.cpu_cores)
        self.vnc_spin = QSpinBox()
        self.vnc_spin.setRange(5900, 5999)
        self.vnc_spin.setValue(config.vnc_port)
        self.adb_spin = QSpinBox()
        self.adb_spin.setRange(5555, 5585)
        self.adb_spin.setValue(config.adb_port)
        self.whp_check = QCheckBox("Use Windows Hypervisor (WHPX)")
        self.whp_check.setChecked(config.use_whp)
        self.cpu_pm_check = QCheckBox("CPU power-management hints (WHPX)")
        self.cpu_pm_check.setChecked(config.enable_cpu_pm)
        self.gpu_combo = QComboBox()
        for key, label in QemuEmulator.GPU_MODES.items():
            self.gpu_combo.addItem(label, key)
        gpu_idx = self.gpu_combo.findData(config.gpu_mode)
        if gpu_idx >= 0:
            self.gpu_combo.setCurrentIndex(gpu_idx)
        self.cpu_combo = QComboBox()
        for key, label in QemuEmulator.CPU_MODES.items():
            self.cpu_combo.addItem(label, key)
        cpu_idx = self.cpu_combo.findData(config.cpu_mode)
        if cpu_idx >= 0:
            self.cpu_combo.setCurrentIndex(cpu_idx)
        self.vram_spin = QSpinBox()
        self.vram_spin.setRange(16, 512)
        self.vram_spin.setSuffix(" MB")
        self.vram_spin.setValue(config.video_memory_mb)
        self.extra_args = QLineEdit(config.extra_qemu_args)
        self.privacy_check = QCheckBox("Hide emulator fingerprints (QEMU + device profile)")
        self.privacy_check.setChecked(config.privacy_mode)
        self.privacy_on_boot = QCheckBox("Apply device profile when ADB connects")
        self.privacy_on_boot.setChecked(config.apply_privacy_on_boot)
        self.profile_combo = QComboBox()
        for key in DEVICE_PROFILES:
            self.profile_combo.addItem(key.replace("_", " ").title(), key)
        idx = self.profile_combo.findData(config.device_profile)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)

        browse_qemu = QPushButton("Browse…")
        browse_qemu.clicked.connect(self._browse_qemu)
        browse_image = QPushButton("Browse…")
        browse_image.clicked.connect(self._browse_image)
        browse_template = QPushButton("Browse…")
        browse_template.clicked.connect(self._browse_template)

        form = QFormLayout()
        qemu_row = QHBoxLayout()
        qemu_row.addWidget(self.qemu_path)
        qemu_row.addWidget(browse_qemu)
        form.addRow("QEMU executable", qemu_row)

        image_row = QHBoxLayout()
        image_row.addWidget(self.image_path)
        image_row.addWidget(browse_image)
        form.addRow("Android disk image", image_row)

        template_row = QHBoxLayout()
        template_row.addWidget(self.template_path)
        template_row.addWidget(browse_template)
        form.addRow("Clone template image", template_row)
        form.addRow(
            "",
            QLabel("Golden/clean image used when creating new instances. Leave empty to use the disk image above."),
        )
        form.addRow("RAM", self.ram_spin)
        form.addRow("CPU cores", self.cpu_spin)
        form.addRow("VNC port", self.vnc_spin)
        form.addRow("ADB port", self.adb_spin)
        form.addRow("", self.whp_check)
        form.addRow("", self.cpu_pm_check)
        form.addRow("GPU adapter", self.gpu_combo)
        form.addRow("Video memory (QXL)", self.vram_spin)
        form.addRow("CPU model", self.cpu_combo)
        form.addRow("Extra QEMU args", self.extra_args)
        form.addRow("", self.privacy_check)
        form.addRow("Device profile", self.profile_combo)
        form.addRow("", self.privacy_on_boot)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _browse_qemu(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select QEMU",
            "",
            "QEMU (qemu-system-x86_64*.exe);;All files (*.*)",
        )
        if path:
            self.qemu_path.setText(path)

    def _browse_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Android disk image",
            "",
            "Disk images (*.img *.qcow2);;All files (*.*)",
        )
        if path:
            self.image_path.setText(path)

    def _browse_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select clone template image",
            "",
            "Disk images (*.img *.qcow2);;All files (*.*)",
        )
        if path:
            self.template_path.setText(path)

    def apply(self) -> EmulatorConfig:
        self._config.qemu_path = self.qemu_path.text().strip()
        self._config.system_image = self.image_path.text().strip()
        self._config.template_image = self.template_path.text().strip()
        self._config.ram_mb = self.ram_spin.value()
        self._config.cpu_cores = self.cpu_spin.value()
        self._config.vnc_port = self.vnc_spin.value()
        self._config.adb_port = self.adb_spin.value()
        self._config.use_whp = self.whp_check.isChecked()
        self._config.enable_cpu_pm = self.cpu_pm_check.isChecked()
        self._config.gpu_mode = self.gpu_combo.currentData()
        self._config.cpu_mode = self.cpu_combo.currentData()
        self._config.video_memory_mb = self.vram_spin.value()
        self._config.extra_qemu_args = self.extra_args.text().strip()
        self._config.privacy_mode = self.privacy_check.isChecked()
        self._config.apply_privacy_on_boot = self.privacy_on_boot.isChecked()
        self._config.device_profile = self.profile_combo.currentData()
        return self._config


class LocationDialog(QDialog):
    def __init__(self, config: EmulatorConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Set GPS Location")
        self.setMinimumWidth(480)
        self._config = config
        self.result_coords: tuple[float, float] | None = None

        self.address_edit = QLineEdit(config.location_address)
        self.address_edit.setPlaceholderText("e.g. 350 Fifth Avenue, New York, NY")
        self.coords_label = QLabel(self._coords_text())

        geocode_btn = QPushButton("Look up address")
        geocode_btn.clicked.connect(self._geocode)
        apply_btn = QPushButton("Apply to running emulator")
        apply_btn.clicked.connect(self._apply_saved)

        self.apply_on_boot = QCheckBox("Apply saved location when emulator boots")
        self.apply_on_boot.setChecked(config.apply_location_on_boot)

        form = QFormLayout()
        form.addRow("Address or place", self.address_edit)
        form.addRow("", geocode_btn)
        form.addRow("Coordinates", self.coords_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(apply_btn)
        layout.addWidget(self.apply_on_boot)
        layout.addWidget(buttons)

    def _coords_text(self) -> str:
        if self._config.latitude or self._config.longitude:
            return f"{self._config.latitude:.6f}, {self._config.longitude:.6f}"
        return "Not set — enter an address and click Look up."

    def _geocode(self) -> None:
        try:
            result = geocode_address(self.address_edit.text())
        except GeocodingError as exc:
            QMessageBox.warning(self, "Location lookup failed", str(exc))
            return
        self._config.location_address = result.display_name
        self._config.latitude = result.latitude
        self._config.longitude = result.longitude
        self._config.save()
        self.address_edit.setText(result.display_name)
        self.coords_label.setText(f"{result.latitude:.6f}, {result.longitude:.6f}")
        self.result_coords = (result.latitude, result.longitude)
        QMessageBox.information(
            self,
            "Location saved",
            f"Resolved to:\n{result.display_name}\n\n{result.latitude:.6f}, {result.longitude:.6f}",
        )

    def _apply_saved(self) -> None:
        parent = self.parent()
        if isinstance(parent, MainWindow):
            if parent._apply_location():
                QMessageBox.information(self, "Location", "GPS coordinates sent to the emulator.")
            else:
                QMessageBox.warning(
                    self,
                    "Location",
                    "Could not apply location. Start the emulator, wait for boot, and ensure ADB is enabled.",
                )

    def apply_options(self) -> None:
        self._config.apply_location_on_boot = self.apply_on_boot.isChecked()
        self._config.save()


class NewInstanceDialog(QDialog):
    """Create a cloned instance with customizable QEMU resources."""

    def __init__(self, config: EmulatorConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Phone Instance")
        self.setMinimumWidth(460)
        self._config = config
        defaults = InstanceResources.from_config(config)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Work phone, Test device")

        self.ram_spin = QSpinBox()
        self.ram_spin.setRange(512, 16384)
        self.ram_spin.setSuffix(" MB")
        self.ram_spin.setValue(defaults.ram_mb)

        self.cpu_spin = QSpinBox()
        self.cpu_spin.setRange(1, 16)
        self.cpu_spin.setValue(defaults.cpu_cores)

        self.gpu_combo = QComboBox()
        for key, label in QemuEmulator.GPU_MODES.items():
            self.gpu_combo.addItem(label, key)
        gpu_idx = self.gpu_combo.findData(defaults.gpu_mode)
        if gpu_idx >= 0:
            self.gpu_combo.setCurrentIndex(gpu_idx)

        self.cpu_combo = QComboBox()
        for key, label in QemuEmulator.CPU_MODES.items():
            self.cpu_combo.addItem(label, key)
        cpu_idx = self.cpu_combo.findData(defaults.cpu_mode)
        if cpu_idx >= 0:
            self.cpu_combo.setCurrentIndex(cpu_idx)

        self.vram_spin = QSpinBox()
        self.vram_spin.setRange(16, 512)
        self.vram_spin.setSuffix(" MB")
        self.vram_spin.setValue(defaults.video_memory_mb)

        self.cpu_pm_check = QCheckBox("CPU power-management hints (WHPX)")
        self.cpu_pm_check.setChecked(defaults.enable_cpu_pm)

        self.full_copy_check = QCheckBox("Quick clone (copy-on-write, shares base disk)")
        self.full_copy_check.setChecked(False)
        self.full_copy_check.setToolTip(
            "Unchecked = full independent copy (recommended for a truly fresh phone)."
        )

        form = QFormLayout()
        form.addRow("Instance name", self.name_edit)
        form.addRow("", self.full_copy_check)
        form.addRow("RAM", self.ram_spin)
        form.addRow("CPU cores", self.cpu_spin)
        form.addRow("GPU adapter", self.gpu_combo)
        form.addRow("Video memory (QXL)", self.vram_spin)
        form.addRow("CPU model", self.cpu_combo)
        form.addRow("", self.cpu_pm_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self.instance_name: str = ""
        self.use_copy_on_write: bool = False
        self.resources: InstanceResources = defaults

    def _try_accept(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Name required", "Enter a name for this instance.")
            return
        self.instance_name = self.name_edit.text().strip()
        self.use_copy_on_write = self.full_copy_check.isChecked()
        self.resources = InstanceResources(
            ram_mb=self.ram_spin.value(),
            cpu_cores=self.cpu_spin.value(),
            gpu_mode=self.gpu_combo.currentData(),
            cpu_mode=self.cpu_combo.currentData(),
            video_memory_mb=self.vram_spin.value(),
            enable_cpu_pm=self.cpu_pm_check.isChecked(),
        )
        self.accept()


class InstanceManagerDialog(QDialog):
    def __init__(
        self,
        manager: InstanceManager,
        config: EmulatorConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Phone Instances")
        self.setMinimumSize(480, 360)
        self._manager = manager
        self._config = config

        self.list_widget = QListWidget()
        self._refresh_list()

        new_btn = QPushButton("New fresh instance…")
        new_btn.clicked.connect(self._create_instance)
        use_btn = QPushButton("Use selected")
        use_btn.clicked.connect(self._use_selected)
        delete_btn = QPushButton("Delete selected")
        delete_btn.clicked.connect(self._delete_selected)

        btn_row = QHBoxLayout()
        btn_row.addWidget(new_btn)
        btn_row.addWidget(use_btn)
        btn_row.addWidget(delete_btn)

        hint = QLabel(
            "Creates an independent copy of your template image. "
            "Set a golden template in Settings for a clean Android each time."
        )
        hint.setWordWrap(True)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.list_widget)
        layout.addLayout(btn_row)
        layout.addWidget(close_box)

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        active_id = self._manager.get_active_id()
        for inst in self._manager.list_instances():
            res = f"{inst.ram_mb} MB RAM, {inst.cpu_cores} cores"
            label = f"{inst.name}  —  {Path(inst.disk_path).name}  ({res})"
            if inst.id == active_id:
                label = f"● {label}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, inst.id)
            self.list_widget.addItem(item)

    def _template_path(self) -> str:
        return self._config.template_image or self._config.system_image

    def _create_instance(self) -> None:
        template = self._template_path()
        if not template or not Path(template).is_file():
            QMessageBox.warning(
                self,
                "Template required",
                "Set an Android disk image or a dedicated clone template in Settings first.",
            )
            return
        dialog = NewInstanceDialog(self._config, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        use_cow = dialog.use_copy_on_write
        qemu_img = InstanceManager.resolve_qemu_img(self._config.qemu_path)
        if use_cow and not qemu_img:
            QMessageBox.warning(self, "qemu-img missing", "qemu-img not found next to QEMU; using full copy instead.")
            use_cow = False
        try:
            info = self._manager.create_fresh(
                template,
                dialog.instance_name,
                qemu_img=qemu_img,
                copy_on_write=use_cow,
                resources=dialog.resources,
            )
        except (OSError, RuntimeError, FileNotFoundError) as exc:
            QMessageBox.critical(self, "Clone failed", str(exc))
            return
        info.apply_to_config(self._config)
        self._config.save()
        self._refresh_list()
        parent = self.parent()
        if isinstance(parent, MainWindow):
            parent.emulator.config = self._config
        res = dialog.resources
        QMessageBox.information(
            self,
            "Instance created",
            f"'{info.name}' is ready.\n\n"
            f"Disk: {info.disk_path}\n"
            f"Resources: {res.ram_mb} MB RAM, {res.cpu_cores} CPU cores\n\n"
            "Press Power to boot this instance.",
        )

    def _use_selected(self) -> None:
        item = self.list_widget.currentItem()
        if not item:
            return
        instance_id = item.data(Qt.ItemDataRole.UserRole)
        active = self._manager.set_active(instance_id)
        if not active:
            return
        active.apply_to_config(self._config)
        self._config.save()
        self._refresh_list()
        parent = self.parent()
        if isinstance(parent, MainWindow):
            parent.emulator.config = self._config
            parent._append_log(
                f"Active instance: {active.name} ({active.ram_mb} MB, {active.cpu_cores} cores)"
            )

    def _delete_selected(self) -> None:
        item = self.list_widget.currentItem()
        if not item:
            return
        instance_id = item.data(Qt.ItemDataRole.UserRole)
        if (
            QMessageBox.question(
                self,
                "Delete instance",
                "Delete this instance and its disk files?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._manager.delete_instance(instance_id)
        active = self._manager.get_active()
        if active:
            active.apply_to_config(self._config)
        self._config.save()
        self._refresh_list()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PhoneClone — Android Emulator")
        self.resize(980, 760)

        self.config = EmulatorConfig.load()
        self.config.apply_bundled_defaults()
        if not self.config.qemu_path:
            self.config.qemu_path = QemuEmulator.find_qemu()

        self._instances = InstanceManager()
        self._apply_active_instance()

        self.emulator = QemuEmulator(self.config, self._append_log)
        self.adb = AdbClient(self.config.adb_port, self._append_log)
        self._output_timer = QTimer(self)
        self._output_timer.timeout.connect(self._poll_qemu_output)
        self._adb_timer = QTimer(self)
        self._adb_timer.setSingleShot(True)
        self._adb_timer.timeout.connect(self._connect_adb)

        self._build_ui()
        self._build_toolbar()
        self.statusBar().showMessage("Ready. Configure QEMU and an Android-x86 image, then press Power.")

    def _apply_active_instance(self) -> None:
        active = self._instances.get_active()
        if active and Path(active.disk_path).is_file():
            active.apply_to_config(self.config)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        power_action = QAction("Power", self)
        power_action.triggered.connect(self._toggle_power)
        toolbar.addAction(power_action)

        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self._open_settings)
        toolbar.addAction(settings_action)

        setup_action = QAction("Setup wizard", self)
        setup_action.triggered.connect(self._open_setup_wizard)
        toolbar.addAction(setup_action)

        toolbar.addSeparator()

        location_action = QAction("Location", self)
        location_action.triggered.connect(self._open_location)
        toolbar.addAction(location_action)

        instances_action = QAction("Instances", self)
        instances_action.triggered.connect(self._open_instances)
        toolbar.addAction(instances_action)

        send_action = QAction("Send file", self)
        send_action.triggered.connect(self._send_file)
        toolbar.addAction(send_action)

        privacy_action = QAction("Apply privacy", self)
        privacy_action.triggered.connect(self._apply_privacy_manual)
        toolbar.addAction(privacy_action)

        toolbar.addSeparator()
        for label, slot in (
            ("Back", self._adb_back),
            ("Home", self._adb_home),
            ("Recents", self._adb_recents),
            ("Power key", self._adb_power),
        ):
            action = QAction(label, self)
            action.triggered.connect(slot)
            toolbar.addAction(action)

    def _build_ui(self) -> None:
        self.display = DisplayPanel()
        self.display.status_changed.connect(self._set_status)
        self.display.files_dropped.connect(self._on_files_dropped)

        phone_frame = QWidget()
        phone_frame.setObjectName("phoneFrame")
        phone_layout = QVBoxLayout(phone_frame)
        phone_layout.setContentsMargins(18, 18, 18, 18)
        phone_layout.addWidget(self.display, stretch=1)

        drop_hint = QLabel("Drop files onto the screen to send to Downloads")
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_hint.setStyleSheet("color: #6B7280; font-size: 11px;")
        phone_layout.addWidget(drop_hint)

        nav_row = QHBoxLayout()
        for text, slot in (
            ("◁ Back", self._adb_back),
            ("○ Home", self._adb_home),
            ("□ Recents", self._adb_recents),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            nav_row.addWidget(btn)
        phone_layout.addLayout(nav_row)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(180)
        self.log_view.setPlaceholderText("Emulator log output…")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(phone_frame)
        splitter.addWidget(self.log_view)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

        self.setStatusBar(QStatusBar())

        self.setStyleSheet(
            """
            QMainWindow { background: #0F172A; color: #E5E7EB; }
            #phoneFrame {
                background: #1F2937;
                border: 2px solid #374151;
                border-radius: 28px;
            }
            QPushButton {
                background: #2563EB;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 14px;
                font-weight: 600;
            }
            QPushButton:hover { background: #1D4ED8; }
            QTextEdit {
                background: #111827;
                color: #D1D5DB;
                border: 1px solid #374151;
                border-radius: 8px;
            }
            QToolBar {
                background: #111827;
                border-bottom: 1px solid #374151;
                spacing: 8px;
                padding: 6px;
            }
            """
        )

    def _append_log(self, message: str) -> None:
        self.log_view.append(message)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def _set_status(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def _open_setup_wizard(self) -> None:
        if self.emulator.is_running:
            QMessageBox.information(self, "Stop emulator first", "Power off before running setup.")
            return
        if run_setup_wizard(self.config, self, force=True):
            self.config.apply_bundled_defaults()
            self.emulator.config = self.config
            self.adb.port = self.config.adb_port
            self._append_log("Setup wizard completed.")

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.apply()
            self.config.save()
            self.emulator.config = self.config
            self.adb.port = self.config.adb_port
            self._append_log("Settings saved.")

    def _open_location(self) -> None:
        dialog = LocationDialog(self.config, self)
        dialog.exec()
        dialog.apply_options()

    def _open_instances(self) -> None:
        if self.emulator.is_running:
            QMessageBox.information(
                self,
                "Stop emulator first",
                "Power off the emulator before switching or creating instances.",
            )
            return
        dialog = InstanceManagerDialog(self._instances, self.config, self)
        dialog.exec()

    def _send_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Send files to emulator",
            "",
            "All files (*.*);;APK (*.apk)",
        )
        if paths:
            self._transfer_files(paths)

    def _on_files_dropped(self, paths: list) -> None:
        self._transfer_files(paths)

    def _transfer_files(self, paths: list) -> None:
        if not self.adb.available:
            QMessageBox.warning(self, "ADB required", "Install Android platform-tools and add adb to PATH.")
            return
        if not self.emulator.is_running:
            QMessageBox.information(self, "Emulator off", "Power on the emulator and wait for boot before sending files.")
            return
        self.adb.connect()
        for path in paths:
            p = Path(path)
            if p.suffix.lower() == ".apk":
                self.adb.install_apk(p)
            else:
                self.adb.push(p)

    def _apply_location(self) -> bool:
        if not (self.config.latitude or self.config.longitude):
            return False
        if not self.adb.connect():
            return False
        return self.adb.set_mock_location(self.config.latitude, self.config.longitude)

    def _apply_privacy_manual(self) -> None:
        if not self.emulator.is_running:
            QMessageBox.information(self, "Emulator off", "Start the emulator first.")
            return
        if self.adb.connect():
            apply_privacy_profile(self.adb, self.config.device_profile, self._append_log)

    def _post_adb_setup(self) -> None:
        if not self.adb.connect():
            return
        if self.config.apply_privacy_on_boot and self.config.privacy_mode:
            apply_privacy_profile(self.adb, self.config.device_profile, self._append_log)
        if self.config.apply_location_on_boot and (self.config.latitude or self.config.longitude):
            self._apply_location()

    def _toggle_power(self) -> None:
        if self.emulator.is_running:
            self._stop_emulator()
            return
        self._start_emulator()

    def _start_emulator(self) -> None:
        errors = self.config.validate()
        if errors:
            reply = QMessageBox.question(
                self,
                "Configuration required",
                "Before starting:\n\n• " + "\n• ".join(errors)
                + "\n\nOpen the setup wizard to download QEMU and Android automatically?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._open_setup_wizard()
            return

        try:
            self.emulator.start()
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, "Start failed", str(exc))
            return

        self._append_log("Emulator booting…")
        if self.config.privacy_mode:
            self._append_log("Privacy mode: neutral QEMU fingerprint enabled.")
        self._output_timer.start(250)
        QTimer.singleShot(4000, lambda: self.display.start(self.config.vnc_port))
        self._adb_timer.start(15000)
        self.statusBar().showMessage("Emulator running.")

    def _stop_emulator(self) -> None:
        self._output_timer.stop()
        self._adb_timer.stop()
        self.display.stop()
        self.emulator.stop()
        self.statusBar().showMessage("Emulator stopped.")

    def _poll_qemu_output(self) -> None:
        if not self.emulator.is_running:
            self._output_timer.stop()
            self._append_log("QEMU process exited.")
            self.display.stop()
            return
        while True:
            line = self.emulator.read_output_line()
            if not line:
                break
            self._append_log(line.rstrip())

    def _connect_adb(self) -> None:
        if self.emulator.is_running:
            self._post_adb_setup()

    def _adb_back(self) -> None:
        self.adb.back()

    def _adb_home(self) -> None:
        self.adb.home()

    def _adb_recents(self) -> None:
        self.adb.recent_apps()

    def _adb_power(self) -> None:
        self.adb.power()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop_emulator()
        super().closeEvent(event)


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PhoneClone")
    app.setOrganizationName("PhoneClone")
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    config = EmulatorConfig.load()
    config.apply_bundled_defaults()
    if config.needs_setup():
        run_setup_wizard(config)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
