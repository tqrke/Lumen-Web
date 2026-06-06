"""Toolbar icons — drawn natively (no SVG dependency)."""

from __future__ import annotations

import math
from functools import lru_cache

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QPushButton


def _pen() -> QPen:
    return QPen(QColor("#b4b4b4"), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


@lru_cache(maxsize=32)
def icon(name: str, size: int = 20) -> QIcon:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(_pen())
    s = size
    m = s * 0.22

    if name == "back":
        p.drawLine(int(s * 0.62), int(m), int(m), int(s / 2))
        p.drawLine(int(m), int(s / 2), int(s * 0.62), int(s - m))
    elif name == "forward":
        p.drawLine(int(m), int(m), int(s * 0.68), int(s / 2))
        p.drawLine(int(s * 0.68), int(s / 2), int(m), int(s - m))
    elif name == "reload":
        p.drawArc(int(m), int(m), int(s - 2 * m), int(s - 2 * m), 45 * 16, 270 * 16)
        p.drawLine(int(s * 0.55), int(m), int(s * 0.72), int(m * 0.8))
        p.drawLine(int(s * 0.55), int(m), int(s * 0.68), int(m * 1.5))
    elif name == "stop":
        p.drawRect(int(m * 1.2), int(m * 1.2), int(s - 2.4 * m), int(s - 2.4 * m))
    elif name == "plus":
        p.drawLine(int(s / 2), int(m), int(s / 2), int(s - m))
        p.drawLine(int(m), int(s / 2), int(s - m), int(s / 2))
    elif name == "bookmark":
        p.drawLine(int(m), int(m), int(s / 2), int(s * 0.38))
        p.drawLine(int(s / 2), int(s * 0.38), int(s - m), int(m))
        p.drawLine(int(m), int(m), int(m), int(s - m))
        p.drawLine(int(s - m), int(m), int(s - m), int(s - m))
        p.drawLine(int(m), int(s - m), int(s / 2), int(s * 0.72))
        p.drawLine(int(s - m), int(s - m), int(s / 2), int(s * 0.72))
    elif name == "settings":
        p.drawEllipse(int(s / 2 - 2), int(s / 2 - 2), 4, 4)
        for i in range(8):
            a = math.radians(i * 45)
            x1 = s / 2 + 5 * math.cos(a)
            y1 = s / 2 + 5 * math.sin(a)
            x2 = s / 2 + 8 * math.cos(a)
            y2 = s / 2 + 8 * math.sin(a)
            p.drawLine(int(x1), int(y1), int(x2), int(y2))
    elif name == "ai":
        p.drawEllipse(int(m * 1.1), int(m * 1.1), int(s - 2.2 * m), int(s - 2.2 * m))
        p.drawLine(int(s * 0.35), int(s * 0.55), int(s * 0.65), int(s * 0.55))
        p.drawLine(int(s / 2), int(s * 0.35), int(s / 2), int(s * 0.75))
    elif name == "inspect":
        p.drawRect(int(m), int(m), int(s - 2 * m), int(s - 2 * m))
        p.drawLine(int(m * 1.5), int(s - m * 1.5), int(s - m * 1.5), int(m * 1.5))
    elif name == "mic":
        p.drawEllipse(int(s * 0.34), int(m * 0.8), int(s * 0.32), int(s * 0.42))
        p.drawLine(int(s / 2), int(s * 0.72), int(s / 2), int(s - m))
        p.drawLine(int(s * 0.32), int(s - m * 0.6), int(s * 0.68), int(s - m * 0.6))
    elif name == "user":
        p.drawEllipse(int(s * 0.34), int(m * 0.7), int(s * 0.32), int(s * 0.32))
        p.drawArc(int(m * 1.1), int(s * 0.52), int(s - 2.2 * m), int(s * 0.42), 0, -180 * 16)
    p.end()
    return QIcon(px)


class IconButton(QPushButton):
    def __init__(self, icon_name: str, tooltip: str, colors: dict, size: int = 32):
        super().__init__()
        self._icon_name = icon_name
        self.setToolTip(tooltip)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(icon(icon_name, 18))
        self.setIconSize(QSize(18, 18))
        self.apply_colors(colors)

    def apply_colors(self, colors: dict) -> None:
        self.setIcon(icon(self._icon_name, 18))
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: 4px;
            }}
            QPushButton:hover {{ background: {colors['bg3']}; }}
            QPushButton:pressed {{ background: {colors['bg2']}; }}
            QPushButton:disabled {{ opacity: 0.35; }}
        """)

    def set_icon_name(self, name: str) -> None:
        self._icon_name = name
        self.setIcon(icon(name, 18))
