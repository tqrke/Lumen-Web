"""PyInstaller runtime hook — Vosk needs its DLL folder on PATH when frozen."""

import os
import sys

if getattr(sys, "frozen", False):
    base = getattr(sys, "_MEIPASS", "")
    if base:
        for sub in ("vosk", os.path.join("vosk")):
            vosk_dir = os.path.join(base, sub)
            if os.path.isdir(vosk_dir):
                os.environ["PATH"] = vosk_dir + os.pathsep + os.environ.get("PATH", "")
                if hasattr(os, "add_dll_directory"):
                    try:
                        os.add_dll_directory(vosk_dir)
                    except OSError:
                        pass
                break
