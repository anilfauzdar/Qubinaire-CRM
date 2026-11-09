@echo off
if "%TEST_USERNAME%"=="" (echo Set TEST_USERNAME to a dedicated load-test account. & pause & exit /b 1)
if "%TEST_PASSWORD%"=="" (echo Set TEST_PASSWORD to the dedicated test account password. & pause & exit /b 1)
if "%API_BASE%"=="" set API_BASE=http://127.0.0.1:8080
where k6 >nul 2>nul || (echo Install k6 first: https://k6.io/docs/get-started/installation/ & pause & exit /b 1)
echo WARNING: This ramps to 5,000 virtual users and may overload the host. Run only in staging.
set /p CONFIRM=Type RUN to continue:
if not "%CONFIRM%"=="RUN" exit /b 1
k6 run -e API_BASE=%API_BASE% -e TEST_USERNAME=%TEST_USERNAME% -e TEST_PASSWORD=%TEST_PASSWORD% tests\load\k6_5000_users.js
pause
