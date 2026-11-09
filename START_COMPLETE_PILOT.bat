@echo off
cd /d "%~dp0"
if not exist .env (
  copy .env.production.example .env >nul
  echo Created .env. Set strong unique secrets before starting.
  notepad .env
  pause
  exit /b 1
)
docker compose up -d --build
echo Portal: http://127.0.0.1:5001
echo API health: http://127.0.0.1:8080/health
echo API docs: http://127.0.0.1:8080/docs
pause
