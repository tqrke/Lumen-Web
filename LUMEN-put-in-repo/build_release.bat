@echo off
REM Build LUMEN Browser for distribution (Windows)
cd /d "%~dp0"

echo === Installing build dependencies ===
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo === Building release ZIP ===
python build_exe.py --zip
if errorlevel 1 exit /b 1

echo.
echo Done. Upload to GitHub Releases:
echo   dist\LUMEN-Browser-5.0.0-win64.zip
echo.
echo Optional single installer (install Inno Setup first):
echo   python build_exe.py --installer
pause
