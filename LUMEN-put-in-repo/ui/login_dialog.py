"""Optional sign-in / create account dialog."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class LoginDialog(QDialog):
    signed_in = None  # set by app after success

    def __init__(self, colors: dict, accounts, *, username_hint: str = ""):
        super().__init__()
        self.colors = colors
        self.accounts = accounts
        self._result_msg = ""
        c = colors
        jazz = c.get("jazz", c["primary"])
        self.setWindowTitle("LUMEN Account")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setStyleSheet(f"""
            QDialog {{ background: {c['bg1']}; color: {c['text']}; }}
            QLabel {{ color: {c['text']}; }}
            QLabel.sub {{ color: {c['text_muted']}; font-size: 12px; }}
            QLineEdit {{
                background: {c['bg0']}; color: {c['text']};
                border: 1px solid {c['border']}; border-radius: 8px;
                padding: 10px 12px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {c['primary']}; }}
            QPushButton.primary {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {c['primary']}, stop:1 {jazz});
                color: #fff; border: none; border-radius: 8px;
                padding: 12px; font-weight: 600;
            }}
            QPushButton.ghost {{
                background: transparent; color: {c['text_muted']};
                border: 1px solid {c['border']}; border-radius: 8px; padding: 10px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("LUMEN Account")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {c['text']};")
        sub = QLabel("Optional — sync bookmarks, settings, and saved passwords on this PC.")
        sub.setProperty("class", "sub")
        sub.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(sub)

        self.stack = QStackedWidget()
        root.addWidget(self.stack)

        self.signin_page = self._build_signin(username_hint)
        self.signup_page = self._build_signup()
        self.stack.addWidget(self.signin_page)
        self.stack.addWidget(self.signup_page)

        self.msg = QLabel("")
        self.msg.setWordWrap(True)
        self.msg.setStyleSheet(f"color: {jazz}; font-size: 12px;")
        root.addWidget(self.msg)

        skip = QPushButton("Continue without account")
        skip.setProperty("class", "ghost")
        skip.setCursor(Qt.CursorShape.PointingHandCursor)
        skip.clicked.connect(self.reject)
        root.addWidget(skip)

    def _build_signin(self, username_hint: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        self.si_user = QLineEdit()
        self.si_user.setPlaceholderText("Username")
        if username_hint:
            self.si_user.setText(username_hint)
        self.si_pass = QLineEdit()
        self.si_pass.setPlaceholderText("Password")
        self.si_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.si_pass.returnPressed.connect(self._do_signin)
        btn = QPushButton("Sign in")
        btn.setProperty("class", "primary")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._do_signin)
        swap = QPushButton("Create an account")
        swap.setProperty("class", "ghost")
        swap.setCursor(Qt.CursorShape.PointingHandCursor)
        swap.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        lay.addWidget(self.si_user)
        lay.addWidget(self.si_pass)
        lay.addWidget(btn)
        lay.addWidget(swap)
        return w

    def _build_signup(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        self.su_user = QLineEdit()
        self.su_user.setPlaceholderText("Choose username")
        self.su_email = QLineEdit()
        self.su_email.setPlaceholderText("Email (optional)")
        self.su_pass = QLineEdit()
        self.su_pass.setPlaceholderText("Password (6+ characters)")
        self.su_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.su_pass2 = QLineEdit()
        self.su_pass2.setPlaceholderText("Confirm password")
        self.su_pass2.setEchoMode(QLineEdit.EchoMode.Password)
        self.su_pass2.returnPressed.connect(self._do_signup)
        btn = QPushButton("Create account")
        btn.setProperty("class", "primary")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._do_signup)
        swap = QPushButton("Already have an account? Sign in")
        swap.setProperty("class", "ghost")
        swap.setCursor(Qt.CursorShape.PointingHandCursor)
        swap.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        lay.addWidget(self.su_user)
        lay.addWidget(self.su_email)
        lay.addWidget(self.su_pass)
        lay.addWidget(self.su_pass2)
        lay.addWidget(btn)
        lay.addWidget(swap)
        return w

    def _do_signin(self) -> None:
        ok, msg = self.accounts.login(self.si_user.text(), self.si_pass.text())
        self.msg.setText(msg)
        if ok:
            self.accept()

    def _do_signup(self) -> None:
        if self.su_pass.text() != self.su_pass2.text():
            self.msg.setText("Passwords do not match.")
            return
        ok, msg = self.accounts.register(
            self.su_user.text(), self.su_pass.text(), self.su_email.text()
        )
        self.msg.setText(msg)
        if ok:
            self.accept()
