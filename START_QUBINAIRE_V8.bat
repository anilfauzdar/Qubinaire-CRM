@echo off
setlocal
cd /d "%~dp0"
echo ===========================================
echo       QUBINAIRE CRM V8 - MASTER
echo ===========================================
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or newer is required.
  echo Please install Python and enable "Add Python to PATH".
  start https://www.python.org/downloads/
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  echo First-time setup: installing required packages...
  python -m venv .venv
  call .venv\Scripts\activate
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  if errorlevel 1 (echo Dependency installation failed.&pause&exit /b 1)
) else (
  call .venv\Scripts\activate
)
if not exist data mkdir data
echo Searching for existing Qubinaire CRM databases...
python migrate_legacy.py
if errorlevel 1 (
  echo Migration could not be completed safely. Existing source data was not deleted.
  pause
  exit /b 2
)
echo Starting Qubinaire CRM V8...
set CRM_HOST=127.0.0.1
set CRM_PORT=5000
python app.py
pause
