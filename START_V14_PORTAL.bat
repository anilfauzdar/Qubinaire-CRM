@echo off
cd /d "%~dp0"
if not exist .env (
  copy .env.production.example .env >nul
  echo Created .env. Edit it and set three strong secrets before continuing.
  notepad .env
  pause
  exit /b 1
)
docker compose up -d --build
echo V14 portal: http://127.0.0.1:5001
echo Central API docs: http://127.0.0.1:8080/docs
pause
