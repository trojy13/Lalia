@echo off
rem Starts Lalia without a console window. Run setup.ps1 once first.
start "" "%~dp0.venv\Scripts\pythonw.exe" -m lalia %*
