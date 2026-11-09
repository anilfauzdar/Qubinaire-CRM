@echo off
cd /d "%~dp0"
echo DEMO ONLY: Do not expose this starter to public internet or use with sensitive live data.
if not exist .venv\Scripts\python.exe (echo Run setup_windows.bat first.&pause&exit /b 1)
call .venv\Scripts\activate
set CRM_HOST=0.0.0.0
set CRM_PORT=5000
python app.py
pause
