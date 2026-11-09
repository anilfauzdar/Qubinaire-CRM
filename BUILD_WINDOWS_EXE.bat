@echo off
setlocal
cd /d "%~dp0clients\flutter"
where flutter >nul 2>nul || (echo Flutter SDK not found. Install Flutter and Visual Studio C++ Desktop workload. & pause & exit /b 1)
flutter create --org com.qubinaire --platforms=windows .
if errorlevel 1 exit /b 1
flutter pub get
if errorlevel 1 exit /b 1
flutter build windows --release
if errorlevel 1 exit /b 1
where ISCC >nul 2>nul || (echo Inno Setup 6 (ISCC.exe) is required to create the installer. & exit /b 1)
ISCC "%~dp0installer\QubinaireCRM.iss"
if errorlevel 1 exit /b 1
echo Installer: clients\flutter\build\windows\installer\QubinaireCRM-Setup.exe
pause
