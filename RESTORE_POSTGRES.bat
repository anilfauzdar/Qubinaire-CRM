@echo off
cd /d "%~dp0"
if "%~1"=="" (echo Usage: RESTORE_POSTGRES.bat backups\file.dump & pause & exit /b 1)
echo WARNING: This replaces data in the current Qubinaire database.
set /p CONFIRM=Type RESTORE to continue:
if not "%CONFIRM%"=="RESTORE" exit /b 1
docker compose exec -T db pg_restore -U qubinaire -d qubinaire --clean --if-exists < "%~1"
if errorlevel 1 (echo Restore returned an error. Inspect database before use.) else (echo Restore command completed.)
pause
