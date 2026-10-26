@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 (
    py -3 launch.py
    pause
    exit /b
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 (
    python launch.py
    pause
    exit /b
)
echo Python 3.10 or newer is required.
echo Install Python from https://www.python.org/downloads/windows/
echo Enable "Add python.exe to PATH" during installation, then run this file again.
pause
exit /b 1
