"""LUMEN design tokens and global Qt stylesheet."""

LUMEN = {
    "bg0": "#0b0f19",
    "bg1": "#12151f",
    "bg2": "#1a2030",
    "bg3": "#242b3d",
    "border": "#2a3348",
    "border_active": "#6366f1",
    "text": "#f1f5f9",
    "text_muted": "#8b9cb3",
    "primary": "#6366f1",
    "accent": "#00d4ff",
    "success": "#10b981",
    "vpn_bg": "#0a2e24",
    "vpn_text": "#34d399",
    "titlebar": "#0b0f19",
    "tab_active": "#0b0f19",
    "tab_inactive": "#181c28",
    "omnibox": "#0f1420",
}


def global_stylesheet() -> str:
    c = LUMEN
    return f"""
    * {{
        font-family: "Segoe UI Variable", "Segoe UI", system-ui, sans-serif;
    }}

    QMainWindow {{
        background: {c["bg0"]};
    }}

    QMenuBar {{
        background: {c["bg1"]};
        color: {c["text"]};
        border-bottom: 1px solid {c["border"]};
        padding: 2px 0;
        font-size: 13px;
    }}
    QMenuBar::item {{
        padding: 6px 12px;
        background: transparent;
        border-radius: 6px;
    }}
    QMenuBar::item:selected {{
        background: {c["bg3"]};
    }}
    QMenu {{
        background: {c["bg2"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 8px 28px 8px 16px;
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background: {c["primary"]};
    }}

    QStatusBar {{
        background: {c["bg1"]};
        color: {c["text_muted"]};
        border-top: 1px solid {c["border"]};
        font-size: 12px;
        padding: 2px 8px;
    }}

    QTabBar {{
        background: {c["bg1"]};
        qproperty-drawBase: 0;
    }}
    QTabBar::tab {{
        background: {c["tab_inactive"]};
        color: {c["text_muted"]};
        padding: 10px 20px;
        min-width: 100px;
        max-width: 220px;
        border: 1px solid {c["border"]};
        border-bottom: none;
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
        margin-right: -1px;
        font-size: 12px;
    }}
    QTabBar::tab:selected {{
        background: {c["tab_active"]};
        color: {c["text"]};
        border-bottom: 2px solid {c["primary"]};
    }}
    QTabBar::tab:hover:!selected {{
        background: {c["bg2"]};
        color: {c["text"]};
    }}
    QTabBar::close-button {{
        subcontrol-position: right;
        border-radius: 4px;
        margin: 4px;
    }}
    QTabBar::close-button:hover {{
        background: rgba(239, 68, 68, 0.3);
    }}

    QTabWidget::pane {{
        border: none;
        background: {c["bg0"]};
        top: -1px;
    }}

    QTabBar {{
        background: {c["bg1"]};
        qproperty-drawBase: 0;
    }}
    QTabBar::tab {{
        background: {c["tab_inactive"]};
        color: {c["text_muted"]};
        padding: 10px 20px;
        min-width: 120px;
        max-width: 240px;
        border: 1px solid {c["border"]};
        border-bottom: none;
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
        margin-right: -1px;
        font-size: 12px;
    }}
    QTabBar::tab:selected {{
        background: {c["tab_active"]};
        color: {c["text"]};
        border-color: {c["border"]};
        border-bottom: 2px solid {c["primary"]};
    }}
    QTabBar::tab:hover:!selected {{
        background: {c["bg2"]};
        color: {c["text"]};
    }}
    QTabBar::close-button {{
        image: none;
        subcontrol-origin: padding;
        subcontrol-position: right;
        width: 16px;
        height: 16px;
        border-radius: 4px;
        margin: 4px;
    }}
    QTabBar::close-button:hover {{
        background: rgba(239, 68, 68, 0.25);
    }}

    QToolTip {{
        background: {c["bg2"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        padding: 6px 10px;
        border-radius: 6px;
    }}

    QInputDialog, QMessageBox {{
        background: {c["bg1"]};
    }}
    """
