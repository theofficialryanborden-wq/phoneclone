from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent, QPixmap, QWheelEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from phoneclone.vnc import VncClient


class DisplayPanel(QWidget):
    """Touch/mouse forwarding display backed by a VNC stream."""

    status_changed = Signal(str)
    files_dropped = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._vnc = VncClient()
        self._vnc.frame_ready.connect(self._on_frame)
        self._vnc.status_changed.connect(self.status_changed.emit)
        self._vnc.connection_lost.connect(lambda: self.status_changed.emit("VNC disconnected."))

        self._label = QLabel("Power on the emulator to see Android here.")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._label.setMinimumSize(320, 568)
        self._label.setStyleSheet(
            "background-color: #111827; color: #9CA3AF; border-radius: 12px; padding: 16px;"
        )
        self._label.setMouseTracking(True)
        self._label.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

        self._scale_x = 1.0
        self._scale_y = 1.0
        self._button_mask = 0

    def start(self, port: int) -> None:
        self.stop()
        self._vnc.port = port
        self._vnc.start()

    def stop(self) -> None:
        self._vnc.stop()
        self._label.setText("Emulator stopped.")
        self._label.setPixmap(QPixmap())

    def _on_frame(self, pixmap: QPixmap) -> None:
        if not isinstance(pixmap, QPixmap):
            return
        scaled = pixmap.scaled(
            self._label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._scale_x = pixmap.width() / max(scaled.width(), 1)
        self._scale_y = pixmap.height() / max(scaled.height(), 1)
        self._label.setPixmap(scaled)

    def _map_coords(self, pos) -> tuple[int, int]:
        pixmap = self._label.pixmap()
        if not pixmap or pixmap.isNull():
            return 0, 0
        label_w = self._label.width()
        label_h = self._label.height()
        px_w = pixmap.width()
        px_h = pixmap.height()
        offset_x = (label_w - px_w) // 2
        offset_y = (label_h - px_h) // 2
        x = int((pos.x() - offset_x) * self._scale_x)
        y = int((pos.y() - offset_y) * self._scale_y)
        return max(x, 0), max(y, 0)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is not self._label:
            return super().eventFilter(obj, event)

        if isinstance(event, QMouseEvent):
            if event.type() == event.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._button_mask = 1
                x, y = self._map_coords(event.position().toPoint())
                self._vnc.send_pointer(x, y, self._button_mask)
            elif event.type() == event.Type.MouseButtonRelease:
                x, y = self._map_coords(event.position().toPoint())
                self._button_mask = 0
                self._vnc.send_pointer(x, y, 0)
            elif event.type() == event.Type.MouseMove and self._button_mask:
                x, y = self._map_coords(event.position().toPoint())
                self._vnc.send_pointer(x, y, self._button_mask)
        elif isinstance(event, QWheelEvent):
            # Scroll as mouse wheel buttons 4/5 via key events is unreliable; ignore for now.
            pass
        return super().eventFilter(obj, event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                paths.append(url.toLocalFile())
        if paths:
            self.files_dropped.emit(paths)
        event.acceptProposedAction()
