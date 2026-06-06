"""Package LUMEN Chrome extension for Chromebook distribution."""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXT = ROOT / "lumen-extension"
DIST = ROOT.parent / "dist"
VERSION = "1.0.0"
ZIP_NAME = f"LUMEN-Chromebook-{VERSION}.zip"


def main() -> int:
    subprocess.run([sys.executable, str(ROOT / "build_icons.py")], check=True)

    required = ["manifest.json", "background.js", "commands.js", "sidepanel.html", "sidepanel.js", "welcome.html"]
    for name in required:
        if not (EXT / name).is_file():
            print(f"Missing: {EXT / name}")
            return 1

    DIST.mkdir(parents=True, exist_ok=True)
    zip_path = DIST / ZIP_NAME
    if zip_path.exists():
        zip_path.unlink()

    start_here = ROOT / "START-HERE.html"
    install_txt = ROOT / "INSTALL.txt"
    install_txt.write_text(
        f"""LUMEN Mind for Chromebook ({VERSION}) — 100% FREE
================================================

OPEN START-HERE.html IN CHROME FOR PICTURED STEPS.

Quick install:
1. Unzip on your Chromebook
2. Chrome → chrome://extensions
3. Developer mode ON (top right) — free, local install only
4. Load unpacked → select the "lumen-extension" folder
5. Pin LUMEN Mind → click icon → Tap to speak

Voice: open Tesco · search milk · scroll · stop · up
Tesco opens in Chrome (not Edge). No store, no fees.
""",
        encoding="utf-8",
    )

    print(f"Creating {zip_path.name} …")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(EXT.rglob("*")):
            if path.is_file():
                zf.write(path, Path("lumen-extension") / path.relative_to(EXT))
        zf.write(install_txt, "INSTALL.txt")
        if start_here.is_file():
            zf.write(start_here, "START-HERE.html")

    install_txt.unlink()
    mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"Done: {zip_path} ({mb:.2f} MB)")
    print("Upload ZIP to Google Drive / your site — users unzip and Load unpacked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
