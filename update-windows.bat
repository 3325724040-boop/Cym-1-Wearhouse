@echo off
setlocal
cd /d "%~dp0"
if not exist "app.py" (
    echo Put this file in your original project folder, next to start-windows.bat.
    pause
    exit /b 1
)
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto use_py
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto use_python
echo Python 3.10 or newer is required. Install it and enable Add Python to PATH.
pause
exit /b 1

:download_tool
if exist updater.py exit /b 0
echo Downloading the update tool from your GitHub repository...
powershell -NoProfile -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/3325724040-boop/Cym-1-Wearhouse/main/updater.py' -OutFile 'updater.download'; Move-Item -Force 'updater.download' 'updater.py'"
exit /b %errorlevel%

:use_py
call :download_tool
if errorlevel 1 goto failed
py -3 updater.py
if errorlevel 1 goto failed
py -3 launch.py
goto done

:use_python
call :download_tool
if errorlevel 1 goto failed
python updater.py
if errorlevel 1 goto failed
python launch.py
goto done

:failed
echo Update did not finish. Keep the message above and your data folder.
:done
pause
