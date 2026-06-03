from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from phoneclone.downloads import download_android_runtime, download_qemu, runtime_ready
from phoneclone.paths import PhoneClonePaths


class RuntimeWorker(QThread):
    progress = Signal(int, str)
    finished_ok = Signal()
    failed = Signal(str)

    def run(self) -> None:
        try:
            paths = PhoneClonePaths()
            paths.ensure()
            if not paths.qemu_exe.is_file():
                self.progress.emit(5, "Downloading emulator engine…")
                download_qemu(lambda pct, msg: self.progress.emit(min(pct // 2, 45), msg))
            if not runtime_ready() or not paths.android_disk.is_file():
                self.progress.emit(50, "Downloading Android (ready to play)…")
                download_android_runtime(
                    lambda pct, msg: self.progress.emit(50 + pct // 2, msg)
                )
            self.progress.emit(100, "All set!")
            self.finished_ok.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class RuntimeManager(QObject):
    """BlueStacks-style one-click Android runtime (engine + pre-installed Android)."""

    progress = Signal(int, str)
    ready = Signal()
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._worker: RuntimeWorker | None = None

    @staticmethod
    def is_ready() -> bool:
        return runtime_ready()

    def ensure(self) -> None:
        if self.is_ready():
            self.ready.emit()
            return
        if self._worker and self._worker.isRunning():
            return
        self._worker = RuntimeWorker()
        self._worker.progress.connect(self.progress.emit)
        self._worker.finished_ok.connect(self.ready.emit)
        self._worker.failed.connect(self.failed.emit)
        self._worker.start()
