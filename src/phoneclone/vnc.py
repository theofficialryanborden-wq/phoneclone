from __future__ import annotations

import socket
import struct
import threading
from typing import Callable

from PIL import Image
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QPixmap


class VncClient(QObject):
    """Minimal RFB 3.8 client for QEMU VNC display."""

    frame_ready = Signal(QPixmap)
    status_changed = Signal(str)
    connection_lost = Signal()

    def __init__(self, host: str = "127.0.0.1", port: int = 5900) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._width = 0
        self._height = 0
        self._frame: Image.Image | None = None

    def start(self) -> None:
        self.stop()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None
        self._frame = None

    def send_pointer(self, x: int, y: int, button_mask: int = 0) -> None:
        if not self._sock:
            return
        try:
            self._sock.sendall(struct.pack("!BBHH", 5, button_mask, x, y))
        except OSError:
            pass

    def send_key(self, keysym: int, down: bool) -> None:
        if not self._sock:
            return
        try:
            self._sock.sendall(struct.pack("!BBII", 4, int(down), keysym, 0))
        except OSError:
            pass

    def _recv_exact(self, size: int) -> bytes:
        assert self._sock is not None
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            chunk = self._sock.recv(remaining)
            if not chunk:
                raise ConnectionError("VNC connection closed.")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _emit_frame(self) -> None:
        if not self._frame:
            return
        w, h = self._frame.size
        qimage = QImage(self._frame.tobytes("raw", "RGBA"), w, h, QImage.Format.Format_RGBA8888)
        self.frame_ready.emit(QPixmap.fromImage(qimage.copy()))

    def _run(self) -> None:
        try:
            # #region agent log
            from phoneclone._agent_debug import agent_log

            agent_log(
                "vnc.py:_run",
                "connecting",
                data={"host": self.host, "port": self.port},
                hypothesis_id="H2",
            )
            # #endregion
            self.status_changed.emit(f"Connecting to VNC {self.host}:{self.port}…")
            self._sock = socket.create_connection((self.host, self.port), timeout=10)
            self._sock.settimeout(0.5)
            self._handshake()
            # #region agent log
            agent_log(
                "vnc.py:_run",
                "handshake ok",
                data={"width": self._width, "height": self._height},
                hypothesis_id="H2",
            )
            # #endregion
            self.status_changed.emit("VNC connected.")
            while not self._stop.is_set():
                self._request_frame()
                self._read_server_messages()
        except Exception as exc:  # noqa: BLE001 - surface to UI
            # #region agent log
            from phoneclone._agent_debug import agent_log

            agent_log(
                "vnc.py:_run",
                "vnc failed",
                data={"error": str(exc), "stopped": self._stop.is_set()},
                hypothesis_id="H2",
            )
            # #endregion
            if not self._stop.is_set():
                self.status_changed.emit(f"VNC error: {exc}")
                self.connection_lost.emit()
        finally:
            if self._sock:
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None

    def _handshake(self) -> None:
        assert self._sock is not None
        banner = self._recv_exact(12)
        if not banner.startswith(b"RFB"):
            raise ConnectionError("Invalid VNC server banner.")

        self._sock.sendall(b"RFB 003.008\n")
        count = struct.unpack("!B", self._recv_exact(1))[0]
        if count == 0:
            reason_len = struct.unpack("!I", self._recv_exact(4))[0]
            reason = self._recv_exact(reason_len).decode("utf-8", errors="replace")
            raise ConnectionError(reason)

        security_types = self._recv_exact(count)
        if 1 not in security_types:
            raise ConnectionError("VNC server requires unsupported authentication.")
        self._sock.sendall(b"\x01")
        if struct.unpack("!I", self._recv_exact(4))[0] != 0:
            raise ConnectionError("VNC authentication failed.")

        self._sock.sendall(b"\x01")  # shared desktop
        self._width, self._height = struct.unpack("!HH", self._recv_exact(4))
        self._recv_exact(16)  # pixel format
        name_len = struct.unpack("!I", self._recv_exact(4))[0]
        self._recv_exact(name_len)

        self._frame = Image.new("RGBA", (self._width, self._height))

        self._sock.sendall(b"\x01")  # SetEncodings
        self._sock.sendall(struct.pack("!H", 1))
        self._sock.sendall(struct.pack("!i", 0))  # Raw encoding

    def _request_frame(self) -> None:
        assert self._sock is not None
        self._sock.sendall(
            struct.pack("!BBHHHH", 2, 0, 0, 0, self._width, self._height)
        )

    def _read_server_messages(self) -> None:
        assert self._sock is not None
        try:
            header = self._recv_exact(1)
        except socket.timeout:
            return
        msg_type = header[0]
        if msg_type == 0:  # FramebufferUpdate
            self._recv_exact(1)
            count = struct.unpack("!H", self._recv_exact(2))[0]
            updated = False
            for _ in range(count):
                x, y, w, h = struct.unpack("!HHHH", self._recv_exact(8))
                encoding = struct.unpack("!i", self._recv_exact(4))[0]
                if encoding != 0:
                    raise ConnectionError(f"Unsupported VNC encoding {encoding}.")
                pixel_bytes = self._recv_exact(w * h * 4)
                tile = Image.frombytes("RGBA", (w, h), pixel_bytes, "raw", "BGRA")
                if self._frame:
                    self._frame.paste(tile, (x, y))
                    updated = True
            if updated:
                self._emit_frame()
        elif msg_type == 1:
            self._recv_exact(19)
        elif msg_type == 2:
            self._recv_exact(3)
