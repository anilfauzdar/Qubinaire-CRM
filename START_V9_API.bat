@echo off
cd /d %~dp0
if not exist .env (copy .env.production.example .env & echo Edit .env and set strong secrets, then run again. & pause & exit /b 1)
docker compose up -d --build
if errorlevel 1 (echo API startup failed. Check Docker Desktop and .env. & pause & exit /b 1)
echo API docs: http://127.0.0.1:8080/docs
echo Central CRM Portal: http://127.0.0.1:5001
pause
