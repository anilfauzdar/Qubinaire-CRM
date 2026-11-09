@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Run setup_windows.bat first.&pause&exit /b 1)
call .venv\Scripts\activate
set CRM_HOST=127.0.0.1
set CRM_PORT=5000
python app.py
pause
