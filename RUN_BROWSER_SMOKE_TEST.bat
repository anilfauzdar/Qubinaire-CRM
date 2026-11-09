@echo off
cd /d "%~dp0tests\browser"
if "%CRM_USERNAME%"=="" (echo Set CRM_USERNAME first. & pause & exit /b 1)
if "%CRM_PASSWORD%"=="" (echo Set CRM_PASSWORD first. & pause & exit /b 1)
where npm >nul 2>nul || (echo Install Node.js first. & pause & exit /b 1)
npm install
npx playwright install chromium
npm test
pause
