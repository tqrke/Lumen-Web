@echo off
cd /d "%~dp0"
python build_release.py
if errorlevel 1 exit /b 1
echo.
echo Chromebook release: ..\dist\LUMEN-Chromebook-1.0.0.zip
pause
