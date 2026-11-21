@echo off
rem Starts FLL Timer (creates the virtual environment and installs PySide6 on first run).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 (
    echo Python 3.10+ is required. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
    pause
    exit /b 1
  )
)
if not exist ".venv\.deps_installed" (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || (pause & exit /b 1)
  echo ok> ".venv\.deps_installed"
)
start "" ".venv\Scripts\pythonw.exe" -m fll_timer
