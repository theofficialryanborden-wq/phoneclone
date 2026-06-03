from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from phoneclone.ui.styles import BLUESTACKS_STYLE


class WelcomeOverlay(QWidget):
    """First-run screen: one click to download engine + Android."""

    get_started = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(BLUESTACKS_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("WelcomeOverlay { background-color: rgba(1, 4, 9, 0.92); }")

        card = QFrame()
        card.setObjectName("welcomeCard")
        card.setFixedWidth(440)
        card.setStyleSheet(BLUESTACKS_STYLE)

        title = QLabel("PhoneClone")
        title.setObjectName("brand")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Play Android apps on PC")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #8b949e; font-size: 15px;")

        self.message = QLabel(
            "One-time setup downloads the emulator engine and a ready-to-play\n"
            "Android system. No ISOs, no virtual machine configuration."
        )
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setStyleSheet("color: #8b949e; padding: 8px 0;")

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)

        self.status = QLabel("")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet("color: #58a6ff; font-size: 12px;")

        self.start_btn = QPushButton("Get Started")
        self.start_btn.setObjectName("primary")
        self.start_btn.setProperty("class", "primary")
        self.start_btn.setStyleSheet(BLUESTACKS_STYLE)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(self.get_started.emit)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 36, 32, 36)
        card_layout.setSpacing(12)
        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addWidget(self.message)
        card_layout.addWidget(self.progress)
        card_layout.addWidget(self.status)
        card_layout.addWidget(self.start_btn)

        outer = QVBoxLayout(self)
        outer.addStretch()
        outer.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)
        outer.addStretch()

    def show_downloading(self) -> None:
        self.start_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.message.setText("Downloading… This only happens once.")

    def update_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        self.status.setText(message)

    def hide_overlay(self) -> None:
        self.hide()
