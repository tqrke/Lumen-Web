"""Animated LUMEN Mind orb — bottom-right, grows when you speak."""

from __future__ import annotations

import math

from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, QTimer, Qt, QPoint, QRectF, pyqtProperty, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

from core.paths import ASSETS
from PyQt6.QtWidgets import QWidget


class MindBubble(QWidget):
    """Persistent LUMEN orb with query label — panel stays hidden."""

    clicked = pyqtSignal()

    ORB = 56
    GLOW = 26
    PAD = 8
    PILL_H = 38

    def __init__(self, anchor: QWidget, colors: dict):
        super().__init__(None)
        self._anchor = anchor
        self._colors = colors
        self._query = ""
        self._subtitle = ""
        self._level = 0.0
        self._scale = 1.0
        self._pulse = 0.0
        self._state = "idle"
        self._visible_query = False
        self._logo = self._load_logo()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._resize_widget()
        self.hide()

        self._scale_anim = QPropertyAnimation(self, b"orbScale", self)
        self._scale_anim.setDuration(160)
        self._scale_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._animate)
        self._tick.start(55)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._to_idle)

    @staticmethod
    def _load_logo() -> QPixmap:
        for name in ("lumen-icon.png", "lumen.ico"):
            path = ASSETS / name
            if path.is_file():
                pix = QPixmap(str(path))
                if not pix.isNull():
                    return pix
        fallback = ASSETS / "icons" / "ai.svg"
        if fallback.is_file():
            pix = QPixmap(str(fallback))
            if not pix.isNull():
                return pix
        return QPixmap()

    def _pill_metrics(self) -> tuple[int, str]:
        if not (self._visible_query and self._subtitle):
            return 0, ""
        font = QFont("Segoe UI", 10)
        fm = QFontMetrics(font)
        text = fm.elidedText(self._subtitle, Qt.TextElideMode.ElideRight, 300)
        return fm.horizontalAdvance(text) + 34, text

    def _orb_layout(self) -> tuple[int, int, int]:
        orb_r = int((self.ORB / 2) * self._scale)
        orb_cx = self.width() - self.GLOW - self.PAD - self.ORB // 2
        orb_cy = self.height() // 2
        return orb_cx, orb_cy, orb_r

    def _resize_widget(self) -> None:
        pill_w, _ = self._pill_metrics()
        orb_side = int(self.ORB * 1.35) + self.GLOW * 2
        w = self.GLOW + self.PAD + pill_w + self.PAD + orb_side + self.GLOW
        h = max(orb_side, self.PILL_H + 8) + self.GLOW * 2
        self.setFixedSize(max(w, orb_side + self.GLOW * 2), h)

    def get_orbScale(self) -> float:
        return self._scale

    def set_orbScale(self, value: float) -> None:
        self._scale = value
        self._resize_widget()
        self.sync_to_anchor()
        self.update()

    orbScale = pyqtProperty(float, get_orbScale, set_orbScale)

    def sync_to_anchor(self) -> None:
        if not self._anchor:
            return

        win = self._anchor.window() or self._anchor
        screen = win.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return

        if win.isMinimized() or not win.isVisible():
            geo = screen.availableGeometry()
            x = geo.right() - self.width() - 16
            y = geo.bottom() - self.height() - 16
            self.move(x, y)
        elif self._anchor.isVisible():
            x = max(4, self._anchor.width() - self.width() - 12)
            y = max(4, self._anchor.height() - self.height() - 16)
            self.move(self._anchor.mapToGlobal(QPoint(x, y)))
        else:
            rect = win.geometry()
            x = rect.right() - self.width() - 16
            y = rect.bottom() - self.height() - 52
            self.move(x, y)

        if not self.isVisible():
            self.show()
        self.raise_()

    def show_idle(self) -> None:
        self._state = "idle"
        self._query = ""
        self._subtitle = ""
        self._visible_query = False
        self._level = 0.0
        self._resize_widget()
        self.sync_to_anchor()
        self.show()
        self.raise_()
        self._animate_scale(1.0)

    def set_voice_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, level))
        target = 1.0 + self._level * 0.55
        if self._state in ("listening", "command", "wake"):
            self._animate_scale(target)
        elif self._state == "idle" and level > 0.12:
            self._scale = 1.0 + level * 0.10
            self.update()

    def set_wake(self, name: str) -> None:
        self._state = "wake"
        self._subtitle = f"At your service, {name}"
        self._visible_query = True
        self._resize_widget()
        self.sync_to_anchor()
        self.show()
        self.raise_()
        self._animate_scale(1.12)
        self._hide_timer.start(5000)

    def set_listening(self) -> None:
        self._state = "listening"
        self._visible_query = False
        self._subtitle = "Listening…"
        self._visible_query = True
        self._resize_widget()
        self.sync_to_anchor()
        self.show()
        self.raise_()
        self._animate_scale(1.06)

    def set_processing(self) -> None:
        self._state = "processing"
        self._subtitle = "Thinking…"
        self._visible_query = True
        self._resize_widget()
        self.sync_to_anchor()
        self.show()
        self.raise_()
        self._animate_scale(1.04)

    def set_speaking(self) -> None:
        self._state = "speaking"
        self._subtitle = "Speaking…"
        self._visible_query = True
        self._resize_widget()
        self.sync_to_anchor()
        self.show()
        self.raise_()
        self._animate_scale(1.08)

    def set_partial(self, text: str) -> None:
        t = text.strip()[:72]
        if not t or self._state not in ("listening", "command", "processing"):
            return
        self._subtitle = t
        self._visible_query = True
        self._state = "listening"
        if not self.isVisible():
            self.show()
        self.update()

    def set_query(self, text: str, *, subtitle: str = "") -> None:
        self._query = text.strip()[:72]
        self._subtitle = (subtitle or text).strip()[:72]
        self._visible_query = True
        self._state = "command"
        self._resize_widget()
        self.sync_to_anchor()
        self.show()
        self.raise_()
        self._animate_scale(1.10)
        self._hide_timer.start(7000)

    def _to_idle(self) -> None:
        if self._state in ("command", "wake"):
            self.show_idle()

    def _animate_scale(self, target: float) -> None:
        self._scale_anim.stop()
        self._scale_anim.setStartValue(self._scale)
        self._scale_anim.setEndValue(target)
        self._scale_anim.start()

    def _animate(self) -> None:
        if not self.isVisible():
            return
        self._pulse += 0.08
        if self._state == "idle":
            breathe = 1.0 + math.sin(self._pulse) * 0.03
            self._scale = self._scale * 0.92 + breathe * 0.08
        elif self._state in ("listening", "processing", "speaking"):
            pulse = 1.0 + math.sin(self._pulse * 1.4) * 0.025
            self._scale = self._scale * 0.94 + pulse * 0.06
        self.update()

    def _draw_logo(self, p: QPainter, orb_cx: int, orb_cy: int, orb_r: int) -> None:
        c = self._colors
        jazz = QColor(c.get("jazz", c["primary"]))
        if self._state == "processing":
            jazz = QColor(c.get("warning", "#e6a817"))
        elif self._state == "speaking":
            jazz = QColor(c.get("success", "#2ecc71"))
        primary = QColor(c["primary"])

        glow = max(6, int(8 + self._level * 18))
        for i in range(3, 0, -1):
            g = QColor(jazz)
            g.setAlpha(16 + i * 7)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            r = orb_r + i * glow // 3
            p.drawEllipse(orb_cx - r, orb_cy - r, r * 2, r * 2)

        ring = QPainterPath()
        ring.addEllipse(orb_cx - orb_r, orb_cy - orb_r, orb_r * 2, orb_r * 2)
        p.setClipPath(ring)

        if not self._logo.isNull():
            size = orb_r * 2
            scaled = self._logo.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = orb_cx - scaled.width() // 2
            y = orb_cy - scaled.height() // 2
            p.drawPixmap(x, y, scaled)
        else:
            grad = QLinearGradient(
                orb_cx - orb_r, orb_cy - orb_r, orb_cx + orb_r, orb_cy + orb_r
            )
            grad.setColorAt(0.0, jazz.lighter(125))
            grad.setColorAt(0.55, primary)
            grad.setColorAt(1.0, jazz.darker(115))
            p.setBrush(grad)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(orb_cx - orb_r, orb_cy - orb_r, orb_r * 2, orb_r * 2)

        p.setClipping(False)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(jazz.lighter(130), 2))
        p.drawEllipse(orb_cx - orb_r, orb_cy - orb_r, orb_r * 2, orb_r * 2)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = self._colors
        jazz = QColor(c.get("jazz", c["primary"]))

        orb_cx, orb_cy, orb_r = self._orb_layout()

        pill_w, pill_text = self._pill_metrics()
        if pill_w > 0 and pill_text:
            pill_x = max(self.GLOW, orb_cx - orb_r - 14 - pill_w)
            pill_y = orb_cy - self.PILL_H // 2
            pr = QRectF(pill_x, pill_y, pill_w, self.PILL_H)
            bg = QColor(c["bg2"])
            bg.setAlpha(245)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(pr, self.PILL_H // 2, self.PILL_H // 2)
            p.setPen(QPen(jazz, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(pr, self.PILL_H // 2, self.PILL_H // 2)
            p.setPen(QColor(c["text"]))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(
                int(pr.x() + 16),
                int(pr.y() + self.PILL_H * 0.68),
                pill_text,
            )

        self._draw_logo(p, orb_cx, orb_cy, orb_r)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)
