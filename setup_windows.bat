@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (echo Install Python 3.11+ from python.org and enable PATH.&pause&exit /b 1)
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist data mkdir data
echo Setup complete. Run run_windows.bat
pause
