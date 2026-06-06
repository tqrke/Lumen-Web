"""Build LUMEN Browser as a standalone Windows app (PyInstaller onedir).

Qt WebEngine needs helper DLLs — ship the whole ``dist/LUMEN-Browser`` folder,
or the release ZIP / installer this script can create.

Usage:
    python build_exe.py              # dist/LUMEN-Browser/LUMEN-Browser.exe
    python build_exe.py --zip        # also dist/LUMEN-Browser-5.0.0-win64.zip
    python build_exe.py --installer  # also dist/LUMEN-Browser-Setup.exe (needs Inno Setup)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Keep in sync with app.py
APP_VERSION = "5.0.0"
APP_NAME = "LUMEN-Browser"

HIDDEN_IMPORTS = [
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebChannel",
    "core.accounts",
    "core.edge_session",
    "core.retail_loader",
    "core.browser_identity",
    "core.perf",
    "ui.command_sanitize",
    "ui.command_router",
    "ui.conversation_session",
    "ui.intent_engine",
    "ui.scroll_control",
    "ui.grocery_control",
    "ui.media_control",
    "ui.login_dialog",
    "ui.assistant",
    "ui.assistant_worker",
    "ui.memory",
    "ui.knowledge",
    "ui.ai_panel",
    "ui.gx_panel",
    "ui.icons",
    "ui.theme_manager",
    "ui.title_bar",
    "ui.edge_tab",
    "ui.mind_bubble",
    "ui.accessibility_voice",
    "shields.engine",
    "shields.interceptor",
    "vpn.tunnel",
    "ui.voice_engine",
    "ui.stt_engine",
    "ui.wake_words",
    "ui.speech_result",
    "speech_recognition",
    "sounddevice",
    "numpy",
    "vosk",
    "edge_tts",
    "pyttsx3",
    "playsound3",
    "websocket",
]

COLLECT_ALL = [
    "vosk",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets",
]


def _post_build(dist_dir: Path) -> None:
    """Copy WebEngine helper next to EXE — Qt looks there on Windows."""
    internal = dist_dir / "_internal" / "PyQt6" / "Qt6" / "bin"
    helper_src = internal / "QtWebEngineProcess.exe"
    if helper_src.is_file():
        shutil.copy2(helper_src, dist_dir / "QtWebEngineProcess.exe")
        print("Copied QtWebEngineProcess.exe next to main EXE")

    readme = dist_dir / "README.txt"
    readme.write_text(
        f"""LUMEN Browser {APP_VERSION}
=====================

1. Double-click {APP_NAME}.exe
2. Allow microphone access when Windows asks
3. Say "Lumen" or click the floating orb

Do NOT move {APP_NAME}.exe out of this folder — it needs the _internal folder
and QtWebEngineProcess.exe beside it.

Settings and voice logs: %USERPROFILE%\\.lumen\\
First run may download a small offline voice model (~40 MB).

Microsoft Edge (for Tesco grocery) must be installed separately — it is not
bundled. Say "open Tesco" to use your system Edge.
""",
        encoding="utf-8",
    )
    print(f"Wrote {readme.name}")


def _zip_release(dist_dir: Path) -> Path:
    zip_path = ROOT / "dist" / f"{APP_NAME}-{APP_VERSION}-win64.zip"
    tmp_path = zip_path.with_suffix(".zip.part")
    if tmp_path.exists():
        tmp_path.unlink()
    print(f"Zipping {dist_dir.name} -> {zip_path.name} ...")
    file_count = 0
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(dist_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(dist_dir.parent))
                file_count += 1
    # Verify before replacing — avoids broken ZIPs if the process was interrupted.
    with zipfile.ZipFile(tmp_path, "r") as zf:
        bad = zf.testzip()
        if bad:
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(f"ZIP verify failed at: {bad}")
        if not zf.namelist():
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError("ZIP is empty")
    if zip_path.exists():
        zip_path.unlink()
    tmp_path.replace(zip_path)
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"Release ZIP: {zip_path} ({size_mb:.1f} MB, {file_count} files)")
    return zip_path


def _build_installer(dist_dir: Path) -> Path | None:
    """Build single Setup.exe with Inno Setup (https://jrsoftware.org/isinfo.php)."""
    iss = ROOT / "installer" / "lumen_browser.iss"
    if not iss.is_file():
        print(f"Missing {iss}")
        return None
    iscc = shutil.which("ISCC") or shutil.which("iscc")
    if not iscc:
        for candidate in (
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe",
        ):
            if Path(candidate).is_file():
                iscc = candidate
                break
    if not iscc:
        print(
            "Inno Setup not found. Install from https://jrsoftware.org/isdl.php\n"
            "Then re-run: python build_exe.py --installer"
        )
        return None
    env = {**dict(**__import__("os").environ), "LUMEN_DIST": str(dist_dir), "LUMEN_VERSION": APP_VERSION}
    subprocess.run([iscc, str(iss)], check=True, env=env, cwd=ROOT)
    setup = ROOT / "dist" / f"{APP_NAME}-Setup.exe"
    if setup.is_file():
        print(f"Installer: {setup}")
        return setup
    print("Installer build finished but Setup.exe not found in dist/")
    return None


def build_pyinstaller() -> int:
    subprocess.run([sys.executable, str(ROOT / "build_icon.py")], check=True)

    icon = ROOT / "assets" / "lumen.ico"
    if not icon.exists():
        print("Missing assets/lumen.ico — run build_icon.py first")
        return 1

    sep = ";" if sys.platform == "win32" else ":"
    dist_dir = ROOT / "dist" / APP_NAME
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(ROOT / "app.py"),
        f"--name={APP_NAME}",
        "--onedir",
        "--windowed",
        f"--icon={icon}",
        f"--runtime-hook={ROOT / 'rthook_qtwebengine.py'}",
        f"--runtime-hook={ROOT / 'rthook_vosk.py'}",
        f"--add-data={ROOT / 'assets'}{sep}assets",
        f"--add-data={ROOT / 'themes'}{sep}themes",
        f"--add-data={ROOT / 'filters'}{sep}filters",
        "--noconfirm",
        f"--distpath={ROOT / 'dist'}",
        f"--workpath={ROOT / 'build'}",
        f"--specpath={ROOT / 'build'}",
    ]
    for mod in HIDDEN_IMPORTS:
        cmd.append(f"--hidden-import={mod}")
    for pkg in COLLECT_ALL:
        cmd.append(f"--collect-all={pkg}")

    print(f"Building {APP_NAME} {APP_VERSION} (onedir) ...")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        return result.returncode
    _post_build(dist_dir)
    exe = dist_dir / f"{APP_NAME}.exe"
    print(f"\nBuilt: {exe}")
    print("Run: dist\\LUMEN-Browser\\LUMEN-Browser.exe")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build LUMEN Browser for Windows release")
    parser.add_argument(
        "--zip",
        action="store_true",
        help="After build, create dist/LUMEN-Browser-VERSION-win64.zip (one download for users)",
    )
    parser.add_argument(
        "--installer",
        action="store_true",
        help="After build, create dist/LUMEN-Browser-Setup.exe via Inno Setup",
    )
    parser.add_argument(
        "--package-only",
        action="store_true",
        help="Skip PyInstaller; only zip/installer from existing dist folder",
    )
    args = parser.parse_args()

    dist_dir = ROOT / "dist" / APP_NAME
    if not args.package_only:
        code = build_pyinstaller()
        if code != 0:
            return code

    if not dist_dir.is_dir() or not (dist_dir / f"{APP_NAME}.exe").is_file():
        print(f"Build output missing: {dist_dir}")
        return 1

    if args.zip:
        _zip_release(dist_dir)
    if args.installer:
        _build_installer(dist_dir)

    if not args.zip and not args.installer:
        print("\nTip: python build_exe.py --zip        -> one ZIP for GitHub/releases")
        print("     python build_exe.py --installer -> one Setup.exe (install Inno Setup first)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
