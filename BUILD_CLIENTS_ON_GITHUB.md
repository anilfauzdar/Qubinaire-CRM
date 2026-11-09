# Build Android APK and Windows installer with GitHub Actions

This workspace does not include Flutter/Dart, Android SDK, or a Windows compiler. The repository includes a hosted build workflow so both release artifacts can be compiled on their native runners.

1. Create a **private** GitHub repository for this Qubinaire CRM source.
2. Extract this project ZIP and push the complete project folder to the repository root (keep `.github/workflows/build-clients.yml`). Do not upload `.env`, database backups, student data, or production credentials.
3. In GitHub, open **Actions** and enable workflows if prompted.
4. Select **Build Qubinaire Android and Windows clients** and choose **Run workflow** on the intended branch.
5. Wait for both `android` and `windows` jobs to complete successfully.
6. Open the completed workflow run and download:
   - `qubinaire-android-apk` — `app-release.apk`
   - `qubinaire-windows-installer` — `QubinaireCRM-Setup.exe`
   - `qubinaire-windows-app-folder` — raw Windows release folder for troubleshooting

A successful workflow is the build proof. Install the APK on a test Android device and the Windows installer on a clean Windows test machine. Test login, first bootstrap, airplane-mode lead/module create and edit, reconnection sync, duplicate retry, role permissions, conflict rejection and user switching before distribution.
