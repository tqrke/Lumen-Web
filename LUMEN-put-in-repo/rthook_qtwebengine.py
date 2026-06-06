"""PyInstaller runtime hook — Qt WebEngine needs explicit paths when frozen."""

import os
import sys

if getattr(sys, "frozen", False):
    base = getattr(sys, "_MEIPASS", "")
    if base:
        qt6 = os.path.join(base, "PyQt6", "Qt6")
        proc = os.path.join(qt6, "bin", "QtWebEngineProcess.exe")
        if os.path.isfile(proc):
            os.environ.setdefault("QTWEBENGINEPROCESS_PATH", proc)
        resources = os.path.join(qt6, "resources")
        if os.path.isdir(resources):
            os.environ.setdefault("QTWEBENGINE_RESOURCES_PATH", resources)
        locales = os.path.join(qt6, "translations", "qtwebengine_locales")
        if not os.path.isdir(locales):
            locales = os.path.join(qt6, "resources", "locales")
        if os.path.isdir(locales):
            os.environ.setdefault("QTWEBENGINE_LOCALES_PATH", locales)
        bin_dir = os.path.join(qt6, "bin")
        if os.path.isdir(bin_dir):
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
