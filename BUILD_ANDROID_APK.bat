@echo off
setlocal
cd /d "%~dp0clients\flutter"
where flutter >nul 2>nul || (echo Flutter SDK not found. Install Flutter and Android SDK first. & pause & exit /b 1)
flutter create --org com.qubinaire --platforms=android .
if errorlevel 1 exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='android/app/src/main/AndroidManifest.xml';$s=Get-Content $p -Raw;$perm='<uses-permission android:name=\"android.permission.INTERNET\"/>' ;if($s -notmatch 'android.permission.INTERNET'){$s=$s -replace '<application',($perm+[Environment]::NewLine+'    <application');Set-Content $p $s}"
flutter pub get
if errorlevel 1 exit /b 1
flutter build apk --release
if errorlevel 1 exit /b 1
echo APK: build\app\outputs\flutter-apk\app-release.apk
pause
