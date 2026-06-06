"""Minimal title bar — Edge-inspired, no decorative gradients."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ui.theme_manager import DEFAULT


class TitleBar(QWidget):
    HEIGHT = 36

    def __init__(self, window: QWidget, title: str = "LUMEN", colors: dict | None = None):
        super().__init__(window)
        self._window = window
        self._drag: QPoint | None = None
        self._colors = colors or DEFAULT
        self.setFixedHeight(self.HEIGHT)
        self.setObjectName("titleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 0, 0)
        layout.setSpacing(10)

        self.brand = QLabel("LUMEN")
        self.brand.setObjectName("brand")
        layout.addWidget(self.brand)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("titleLabel")
        layout.addWidget(self.title_label)
        layout.addStretch()

        self.min_btn = QPushButton("—")
        self.min_btn.setObjectName("winBtn")
        self.min_btn.clicked.connect(window.showMinimized)

        self.max_btn = QPushButton("□")
        self.max_btn.setObjectName("winBtn")
        self.max_btn.clicked.connect(self._toggle_maximize)

        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("closeBtn")
        self.close_btn.clicked.connect(window.close)

        for btn in (self.min_btn, self.max_btn, self.close_btn):
            layout.addWidget(btn)

        self._apply_styles()

    def set_colors(self, colors: dict) -> None:
        self._colors = colors
        self._apply_styles()

    def _apply_styles(self) -> None:
        c = self._colors
        self.setStyleSheet(f"""
            #titleBar {{
                background: {c['titlebar']};
                border-bottom: 1px solid {c['border']};
            }}
            QLabel#brand {{
                color: {c.get('jazz', c['primary'])};
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 2px;
            }}
            QLabel#titleLabel {{
                color: {c['text_muted']};
                font-size: 12px;
                font-weight: 400;
            }}
            QPushButton#winBtn {{
                background: transparent;
                color: {c['text_muted']};
                border: none;
                min-width: 44px;
                max-width: 44px;
                height: {self.HEIGHT}px;
                font-size: 13px;
            }}
            QPushButton#winBtn:hover {{
                background: {c['bg3']};
                color: {c['text']};
            }}
            QPushButton#closeBtn {{
                background: transparent;
                color: {c['text_muted']};
                border: none;
                min-width: 44px;
                max-width: 44px;
                height: {self.HEIGHT}px;
                font-size: 15px;
            }}
            QPushButton#closeBtn:hover {{
                background: #c42b1c;
                color: #ffffff;
            }}
        """)

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)

    def _toggle_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
            self.max_btn.setText("□")
        else:
            self._window.showMaximized()
            self.max_btn.setText("❐")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if self._window.isMaximized():
                self._window.showNormal()
                self.max_btn.setText("□")
            self._window.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event) -> None:
        self._drag = None

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
