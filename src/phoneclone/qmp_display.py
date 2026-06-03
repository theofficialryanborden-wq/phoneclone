from __future__ import annotations

import json
import socket
import threading
import time

from PIL import Image
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QPixmap

from phoneclone.paths import PhoneClonePaths


class QmpDisplayClient(QObject):
    """Polls QEMU via QMP screendump (reliable on Windows; VNC FB requests often hang)."""

    frame_ready = Signal(QPixmap)
    status_changed = Signal(str)
    connection_lost = Signal()

    def __init__(self, host: str = "127.0.0.1", port: int = 4444) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ppm_path = PhoneClonePaths().cache_dir / "frame.ppm"
        self._connected_once = False

    def start(self) -> None:
        self.stop()
        self._stop.clear()
        self._connected_once = False
        PhoneClonePaths().ensure()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def send_pointer(self, x: int, y: int, button_mask: int = 0) -> None:
        down = bool(button_mask & 1)
        try:
            self._qmp(
                {
                    "execute": "input-send-event",
                    "arguments": {
                        "events": [
                            {"type": "abs", "data": {"axis": "x", "value": x}},
                            {"type": "abs", "data": {"axis": "y", "value": y}},
                            {"type": "btn", "data": {"down": down, "button": "left"}},
                        ]
                    },
                },
                timeout=2,
            )
        except OSError:
            pass

    def _qmp(self, command: dict, timeout: float = 5) -> dict:
        sock = socket.create_connection((self.host, self.port), timeout=timeout)
        try:
            sock.settimeout(timeout)
            sock.recv(4096)
            sock.sendall(json.dumps({"execute": "qmp_capabilities"}).encode() + b"\n")
            sock.recv(4096)
            sock.sendall(json.dumps(command).encode() + b"\n")
            chunks: list[bytes] = []
            while True:
                part = sock.recv(8192)
                if not part:
                    break
                chunks.append(part)
                if b"\n" in part:
                    break
            raw = b"".join(chunks).decode("utf-8", errors="replace").strip()
            line = raw.splitlines()[0] if raw else "{}"
            return json.loads(line)
        finally:
            sock.close()

    def _run(self) -> None:
        try:
            # #region agent log
            from phoneclone._agent_debug import agent_log

            agent_log(
                "qmp_display.py:_run",
                "starting",
                data={"host": self.host, "port": self.port},
                hypothesis_id="H9",
                run_id="post-fix",
            )
            # #endregion
            self.status_changed.emit("Connecting to emulator display…")
            while not self._stop.is_set():
                try:
                    result = self._qmp(
                        {
                            "execute": "screendump",
                            "arguments": {"filename": str(self._ppm_path)},
                        },
                        timeout=8,
                    )
                    if "error" in result:
                        raise RuntimeError(str(result["error"]))
                    if not self._ppm_path.is_file():
                        raise RuntimeError("Screendump file missing.")
                    image = Image.open(self._ppm_path).convert("RGBA")
                    w, h = image.size
                    qimage = QImage(image.tobytes("raw", "RGBA"), w, h, QImage.Format.Format_RGBA8888)
                    self.frame_ready.emit(QPixmap.fromImage(qimage.copy()))
                    if not self._connected_once:
                        self._connected_once = True
                        self.status_changed.emit("Display connected.")
                        # #region agent log
                        agent_log(
                            "qmp_display.py:_run",
                            "first frame",
                            data={"width": w, "height": h},
                            hypothesis_id="H9",
                            run_id="post-fix",
                        )
                        # #endregion
                except OSError as exc:
                    if not self._stop.is_set():
                        self.status_changed.emit(f"Display error: {exc}")
                        self.connection_lost.emit()
                    time.sleep(1.5)
                    continue
                except Exception as exc:  # noqa: BLE001
                    if not self._stop.is_set():
                        self.status_changed.emit(f"Display error: {exc}")
                    time.sleep(1.5)
                    continue
                time.sleep(0.35)
        except Exception as exc:  # noqa: BLE001
            if not self._stop.is_set():
                self.status_changed.emit(f"Display error: {exc}")
                self.connection_lost.emit()
