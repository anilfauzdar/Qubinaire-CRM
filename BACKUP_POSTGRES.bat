@echo off
cd /d "%~dp0"
if not exist backups mkdir backups
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
docker compose exec -T db sh -c "pg_dump -U qubinaire -d qubinaire -Fc" > "backups\qubinaire_%TS%.dump"
if errorlevel 1 (echo Backup failed & pause & exit /b 1)
echo Backup saved to backups\qubinaire_%TS%.dump
pause
