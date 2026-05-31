from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from phoneclone.config import EmulatorConfig
from phoneclone.downloads import (
    bundled_android_ready,
    bundled_qemu_ready,
    create_android_disk,
    download_android_iso,
    download_qemu,
    launch_android_installer,
)
from phoneclone.paths import PhoneClonePaths
from phoneclone.qemu import QemuEmulator


class _Worker(QThread):
    progress = Signal(int, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args, **kwargs) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            result = self._fn(
                *self._args,
                progress=lambda pct, msg: self.progress.emit(pct, msg),
                **self._kwargs,
            )
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001 - show in UI
            self.failed.emit(str(exc))


class WelcomePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Welcome to PhoneClone")
        self.setSubTitle(
            "This wizard downloads QEMU and Android-x86, creates a disk image, "
            "and tunes performance. You can rerun it anytime from the toolbar."
        )
        body = QLabel(
            "<p>PhoneClone needs two components:</p>"
            "<ul>"
            "<li><b>QEMU</b> — the virtual machine engine (~100 MB download)</li>"
            "<li><b>Android-x86</b> — a disk image with Android installed (~1.2 GB ISO, then one-time install)</li>"
            "</ul>"
            "<p>Everything is stored under <code>%USERPROFILE%\\.phoneclone</code>.</p>"
        )
        body.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(body)


class QemuPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Download QEMU")
        self.setSubTitle("PhoneClone can download a portable QEMU build automatically.")
        self._worker: _Worker | None = None

        self.status = QLabel("QEMU is not installed yet.")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.download_btn = QPushButton("Download QEMU")
        self.download_btn.clicked.connect(self._start_download)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.progress)
        layout.addWidget(self.download_btn)
        self._refresh_status()

    def _refresh_status(self) -> None:
        if bundled_qemu_ready():
            exe = PhoneClonePaths().qemu_exe
            self.status.setText(f"QEMU ready: {exe}")
            self.progress.setValue(100)
            self.download_btn.setEnabled(False)
            self.completeChanged.emit()
        elif QemuEmulator.find_qemu():
            self.status.setText(f"Using system QEMU: {QemuEmulator.find_qemu()}")
            self.progress.setValue(100)
            self.download_btn.setEnabled(True)
            self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802
        return bool(QemuEmulator.find_qemu() or bundled_qemu_ready())

    def _start_download(self) -> None:
        self.download_btn.setEnabled(False)
        self.progress.setValue(0)
        self._worker = _Worker(download_qemu)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_progress(self, pct: int, msg: str) -> None:
        self.progress.setValue(pct)
        self.status.setText(msg)

    def _on_done(self, exe: Path) -> None:
        self.status.setText(f"QEMU ready: {exe}")
        self.progress.setValue(100)
        self.completeChanged.emit()

    def _on_fail(self, message: str) -> None:
        self.download_btn.setEnabled(True)
        QMessageBox.warning(self, "QEMU download failed", message)


class AndroidPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Android-x86 Image")
        self.setSubTitle("Download the Android-x86 ISO, create a disk, then run the one-time installer.")
        self._worker: _Worker | None = None
        self._iso_ready = False
        self._disk_ready = False

        self.status = QLabel("")
        self.progress = QProgressBar()
        self.iso_btn = QPushButton("1. Download Android-x86 ISO")
        self.iso_btn.clicked.connect(self._download_iso)
        self.disk_btn = QPushButton("2. Create 16 GB disk image")
        self.disk_btn.clicked.connect(self._create_disk)
        self.install_btn = QPushButton("3. Run Android installer (opens separate window)")
        self.install_btn.clicked.connect(self._run_installer)
        self.install_hint = QLabel(
            "In the installer window: choose <b>Installation</b> → <b>Install Android-x86 to harddisk</b> "
            "→ select the virtio disk → ext4 → Yes (GRUB) → Reboot."
        )
        self.install_hint.setWordWrap(True)

        row = QHBoxLayout()
        row.addWidget(self.iso_btn)
        row.addWidget(self.disk_btn)
        row.addWidget(self.install_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.progress)
        layout.addLayout(row)
        layout.addWidget(self.install_hint)
        self._refresh()

    def _refresh(self) -> None:
        paths = PhoneClonePaths()
        self._iso_ready = paths.android_iso.is_file() and paths.android_iso.stat().st_size > 50 * 1024 * 1024
        self._disk_ready = paths.android_disk.is_file()
        if bundled_android_ready():
            self.status.setText(f"Android disk ready: {paths.android_disk}")
            self.progress.setValue(100)
        elif self._disk_ready:
            self.status.setText(
                f"Disk created ({paths.android_disk}). Run the installer if Android is not installed yet."
            )
        elif self._iso_ready:
            self.status.setText(f"ISO downloaded: {paths.android_iso}")
        else:
            self.status.setText("Download the ISO to continue.")
        self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802
        return bundled_android_ready() or self._disk_ready

    def _download_iso(self) -> None:
        self.iso_btn.setEnabled(False)
        self.progress.setValue(0)
        self._worker = _Worker(download_android_iso)
        self._worker.progress.connect(lambda p, m: (self.progress.setValue(p), self.status.setText(m)))
        self._worker.finished_ok.connect(lambda _p: (self.iso_btn.setEnabled(True), self._refresh()))
        self._worker.failed.connect(lambda e: (self.iso_btn.setEnabled(True), QMessageBox.warning(self, "ISO download failed", e)))
        self._worker.start()

    def _create_disk(self) -> None:
        qemu_img = QemuEmulator.find_qemu_img()
        if not qemu_img:
            QMessageBox.warning(self, "qemu-img missing", "Download QEMU first — qemu-img.exe was not found.")
            return
        self.disk_btn.setEnabled(False)
        self.progress.setValue(0)
        self._worker = _Worker(create_android_disk, qemu_img)
        self._worker.progress.connect(lambda p, m: (self.progress.setValue(p), self.status.setText(m)))
        self._worker.finished_ok.connect(lambda _p: (self.disk_btn.setEnabled(True), self._refresh()))
        self._worker.failed.connect(lambda e: (self.disk_btn.setEnabled(True), QMessageBox.warning(self, "Disk creation failed", e)))
        self._worker.start()

    def _run_installer(self) -> None:
        qemu = QemuEmulator.find_qemu()
        paths = PhoneClonePaths()
        if not qemu:
            QMessageBox.warning(self, "QEMU missing", "Download QEMU first.")
            return
        if not paths.android_iso.is_file():
            QMessageBox.warning(self, "ISO missing", "Download the Android-x86 ISO first.")
            return
        if not paths.android_disk.is_file():
            QMessageBox.warning(self, "Disk missing", "Create the disk image first.")
            return
        try:
            launch_android_installer(qemu, str(paths.android_iso), str(paths.android_disk))
        except OSError as exc:
            QMessageBox.critical(self, "Installer failed", str(exc))
            return
        QMessageBox.information(
            self,
            "Installer started",
            "A separate QEMU window opened for Android installation.\n\n"
            "When installation finishes and the VM reboots into Android, close that window and click Finish.",
        )


class PerformancePage(QWizardPage):
    def __init__(self, config: EmulatorConfig) -> None:
        super().__init__()
        self.setTitle("Performance & GPU")
        self.setSubTitle("Tune acceleration for your PC. You can change these later in Settings.")
        self._config = config

        whpx_note = "WHPX (Windows Hypervisor): available" if QemuEmulator.whpx_available() else (
            "WHPX not detected — enable Windows Hypervisor Platform in Windows Features for best speed."
        )

        self.whp_check = QCheckBox("Use Windows Hypervisor (WHPX)")
        self.whp_check.setChecked(config.use_whp)
        self.cpu_pm_check = QCheckBox("Enable CPU power-management hints (recommended with WHPX)")
        self.cpu_pm_check.setChecked(config.enable_cpu_pm)

        self.gpu_combo = QComboBox()
        for key, label in QemuEmulator.GPU_MODES.items():
            self.gpu_combo.addItem(label, key)
        idx = self.gpu_combo.findData(config.gpu_mode)
        if idx >= 0:
            self.gpu_combo.setCurrentIndex(idx)

        self.cpu_combo = QComboBox()
        for key, label in QemuEmulator.CPU_MODES.items():
            self.cpu_combo.addItem(label, key)
        idx = self.cpu_combo.findData(config.cpu_mode)
        if idx >= 0:
            self.cpu_combo.setCurrentIndex(idx)

        self.ram_spin = QSpinBox()
        self.ram_spin.setRange(1024, 16384)
        self.ram_spin.setSuffix(" MB")
        self.ram_spin.setValue(max(config.ram_mb, 2048))

        self.cpu_spin = QSpinBox()
        self.cpu_spin.setRange(1, 16)
        self.cpu_spin.setValue(config.cpu_cores)

        self.vram_spin = QSpinBox()
        self.vram_spin.setRange(16, 512)
        self.vram_spin.setSuffix(" MB")
        self.vram_spin.setValue(config.video_memory_mb)

        form = QFormLayout()
        form.addRow("", QLabel(whpx_note))
        form.addRow("", self.whp_check)
        form.addRow("", self.cpu_pm_check)
        form.addRow("GPU adapter", self.gpu_combo)
        form.addRow("Video memory (QXL)", self.vram_spin)
        form.addRow("CPU model", self.cpu_combo)
        form.addRow("RAM", self.ram_spin)
        form.addRow("CPU cores", self.cpu_spin)

        layout = QVBoxLayout(self)
        layout.addLayout(form)

    def apply(self, config: EmulatorConfig) -> None:
        config.use_whp = self.whp_check.isChecked()
        config.enable_cpu_pm = self.cpu_pm_check.isChecked()
        config.gpu_mode = self.gpu_combo.currentData()
        config.cpu_mode = self.cpu_combo.currentData()
        config.ram_mb = self.ram_spin.value()
        config.cpu_cores = self.cpu_spin.value()
        config.video_memory_mb = self.vram_spin.value()


class CompletePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Setup Complete")
        self.setSubTitle("PhoneClone is ready to boot.")
        body = QLabel(
            "Click <b>Finish</b> to save settings and open the emulator.\n\n"
            "If you ran the Android installer, make sure Android booted successfully before finishing."
        )
        body.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(body)


class SetupWizard(QWizard):
    def __init__(self, config: EmulatorConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PhoneClone Setup")
        self.setMinimumSize(560, 480)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self._config = config

        self._welcome = WelcomePage()
        self._qemu = QemuPage()
        self._android = AndroidPage()
        self._performance = PerformancePage(config)
        self._complete = CompletePage()

        self.addPage(self._welcome)
        self.addPage(self._qemu)
        self.addPage(self._android)
        self.addPage(self._performance)
        self.addPage(self._complete)

        self.setButtonText(QWizard.WizardButton.FinishButton, "Finish")
        self.finished.connect(self._on_finished)

    def _on_finished(self, result: int) -> None:
        if result != QWizard.DialogCode.Accepted:
            return
        self._performance.apply(self._config)
        self._config.apply_bundled_defaults()
        if not self._config.qemu_path:
            self._config.qemu_path = QemuEmulator.find_qemu()
        paths = PhoneClonePaths()
        if not self._config.system_image and paths.android_disk.is_file():
            self._config.system_image = str(paths.android_disk)
        self._config.setup_complete = True
        self._config.save()


def run_setup_wizard(config: EmulatorConfig, parent=None, *, force: bool = False) -> bool:
    if not force and not config.needs_setup():
        config.apply_bundled_defaults()
        return False
    wizard = SetupWizard(config, parent)
    return wizard.exec() == QWizard.DialogCode.Accepted
