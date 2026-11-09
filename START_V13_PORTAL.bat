@echo off
cd /d %~dp0
if not exist .env (copy .env.production.example .env & echo Edit .env and set three strong secrets, then run again. & pause & exit /b 1)
docker compose up -d --build api db portal
if errorlevel 1 (echo Startup failed. Check Docker Desktop and .env. & pause & exit /b 1)
echo Central CRM Portal: http://127.0.0.1:5001
echo API docs: http://127.0.0.1:8080/docs
pause
