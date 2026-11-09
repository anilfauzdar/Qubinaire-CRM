# Qubinaire CRM – Integrated Build

This is the consolidated Qubinaire CRM package. Start with:
- `README_COMPLETE.md` – product scope and limitations
- `ONE_TIME_SETUP.md` – central PostgreSQL/API/portal deployment
- `PROJECT_STATUS.md` – what was implemented and what was not tested
- `SECURITY_REVIEW_CHECKLIST.md` – production release gate

## Start central CRM on Windows
1. Install Docker Desktop.
2. Run `START_COMPLETE_PILOT.bat`.
3. On first run, it copies `.env.production.example` to `.env` and opens it.
   Replace the PostgreSQL password and portal secret with long random values.
4. Run `START_COMPLETE_PILOT.bat` again.
5. Open portal `http://127.0.0.1:5001` and API docs `http://127.0.0.1:8080/docs`.

For an empty database, create the first admin using the bootstrap command in
`ONE_TIME_SETUP.md`. For an existing V14 database, back up first and apply
`APPLY_MIGRATIONS_002.bat` before using mobile device sync.

## Optional AI Lead Hunter
Set `EXA_API_KEY` and a dedicated manager service account in `.env`, then run
`START_LEAD_HUNTER.bat`. Imported leads remain `review_required`.

## Offline CRM coverage
The Android/Windows Flutter source now caches leads plus all 12 writable core modules
(activities, follow-ups, daily reports, courses, admissions, payments, targets,
attendance, leave requests, refund requests, incentive payouts and incentive settings).
The employee directory is cached read-only. Local creates/edits queue for sync when
connectivity returns. Deletes, attachments and Android sync while force-closed are
not implemented; module forms are currently JSON-based. SQLite is not SQLCipher
encrypted, so keep the build in private pilot until the security checklist is closed.

## Mobile/Windows builds
- `BUILD_ANDROID_APK.bat` requires Flutter and Android SDK.
- `BUILD_WINDOWS_EXE.bat` requires Flutter, Visual Studio C++ desktop workload,
  and Inno Setup 6 for the installer. See `BUILD_CLIENTS_ON_GITHUB.md` for hosted builds.
- GitHub Actions build workflow: `.github/workflows/build-clients.yml`.

WhatsApp integration is intentionally excluded. Android/Windows binaries,
live integration tests, independent security audit and 5,000-VU benchmark are
not included as completed results; see `PROJECT_STATUS.md`.
