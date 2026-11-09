@echo off
cd /d "%~dp0"
if not exist .env (echo First run START_COMPLETE_PILOT.bat and configure .env. & pause & exit /b 1)
docker compose --profile lead-hunter up -d --build
if errorlevel 1 (echo Lead Hunter failed to start. Check API, EXA_API_KEY and service account settings. & pause & exit /b 1)
echo Lead Hunter worker started. Logs: docker compose logs -f lead-hunter-worker
pause
