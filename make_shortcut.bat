@echo off
rem Puts an "FLL Timer" shortcut (with the BIOGLOW icon) on your Desktop.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\make_shortcut.ps1"
pause
