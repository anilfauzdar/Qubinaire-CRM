@echo off
cd /d "%~dp0"
echo This applies integration schema changes to the existing database.
echo Take a PostgreSQL backup before continuing.
set /p CONFIRM=Type APPLY to continue:
if not "%CONFIRM%"=="APPLY" exit /b 1
docker compose exec -T db psql -U qubinaire -d qubinaire < server\migrations\002_integrations.sql
if errorlevel 1 (echo Migration failed. Inspect DB and backup before retry.) else (echo Migration 002 applied.)
pause
