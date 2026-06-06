@echo off
cd /d "%~dp0"
echo Installing dependencies...
python -m pip install -r requirements.txt -q
echo Building icon...
python build_icon.py
echo.
echo Choose:
echo   1. Run browser (python app.py)
echo   2. Build EXE (python build_exe.py)
echo.
set /p choice="Enter 1 or 2: "
if "%choice%"=="2" (
    python build_exe.py
    echo.
    echo EXE location: dist\LUMEN-Browser\LUMEN-Browser.exe
    pause
) else (
    python app.py
)
