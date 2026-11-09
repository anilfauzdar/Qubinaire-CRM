# Qubinaire CRM – Consolidated build

This package consolidates the prior V2–V14 source history and the central
PostgreSQL API + portal foundation. It also includes employee/team management,
lead editing, schema-driven module forms, approval metadata, bootstrap admin,
backup/restore scripts, Flutter client source and n8n workflow template.

## Start the private pilot
Read `ONE_TIME_SETUP.md` first. Requirements:
- Windows 10/11 or Ubuntu host with Docker Desktop / Docker Engine and Compose.
- Strong secrets in `.env` (copy `.env.production.example`).
- First admin created with `server/bootstrap_admin.py` on a clean database, or
  existing users migrated with `server/migrate_sqlite_to_postgres.py`.
- Portal: `http://127.0.0.1:5001`
- API health/docs: `http://127.0.0.1:8080/health` and `/docs`

## Current functional central features
- Login with migrated/bootstrap user credentials and 12-hour API bearer session.
- Admin employee creation/update/deactivation; manager team visibility.
- Student/college lead create, list, edit, role-scoped assignment and audit.
- Dashboard summary for leads, admissions, collections and pending follow-ups.
- Create/edit forms for activities, follow-ups, daily reports, courses, admissions,
  payments, attendance, leave, refunds, incentive payouts, targets and incentive settings.
- Manager-scoped employee records and server-side approval reviewer timestamps.
- PostgreSQL database backup/restore scripts.

## Still not complete / not verified
- No built Android APK or Windows EXE; Flutter platform scaffolding must be generated
  with `flutter create --platforms=android,windows .` and then built/tested.
- Flutter currently stores leads locally in SQLite and an outbox. Automatic
  multi-device sync, canonical server writes, conflict resolution and retry engine
  are not implemented.
- No AI lead discovery crawler, WhatsApp Business API integration, payment gateway,
  placement/interview workflow, college partnership contract pipeline or franchise
  management workflow.
- Docker is not installed in the build environment; live Compose/PostgreSQL/browser
  end-to-end tests were not possible.
- No penetration test, TLS reverse proxy deployment, external backup drill or
  300/5,000-user load test. Do not expose the pilot to the public internet.

## Integrated mobile/desktop, sync and lead discovery
- Flutter Android/Windows source: `clients/flutter/`.
- Login registers a user-bound device; per-user local cache/outbox covers leads,
  activities, followups, daily reports, courses, admissions, payments, targets,
  attendance, leave requests, refund requests, incentive payouts and incentive settings.
  Employee directory is cached read-only. Sync retries every 30 seconds while open,
  on connectivity restoration and on app resume.
- Server enforces role/record scope, idempotency, foreign-key ID mapping for offline
  creates, and base-snapshot conflict checks. Deletes and attachments are not synced;
  the generic module editor is currently JSON-based and needs UX refinement.
- Android build: run `BUILD_ANDROID_APK.bat` on a machine with Flutter + Android SDK.
- Windows build: run `BUILD_WINDOWS_EXE.bat` on Windows with Flutter + Visual Studio
  C++ desktop workload; install Inno Setup to create `QubinaireCRM-Setup.exe`.
- GitHub Actions workflow `.github/workflows/build-clients.yml` builds artifacts
  when run in a GitHub repository with Actions enabled.
- AI Lead Hunter uses Exa public-web search when `EXA_API_KEY` is configured.
  It produces review-required candidates; no private phone scraping or auto-contact.
- WhatsApp integration is intentionally excluded from this build per instruction.

## Verification tools
- `SMOKE_TEST.ps1`: live API/portal health and OpenAPI route checks.
- `tests/browser/smoke.mjs`: Playwright login/dashboard/leads browser smoke test.
- `SECURITY_STATIC_AUDIT.py`: limited static configuration checks.
- `tests/load/k6_5000_users.js`: staged 5,000-VU login + lead-read benchmark.
  Run only on staging with a dedicated test account; this test has not been run here.

- Admin-only device inventory and device-token revocation endpoints.

- Optional scheduled Lead Hunter worker: `docker compose --profile lead-hunter up -d --build`.
  It searches configured public-web queries, deduplicates by source URL and
  creates review-required leads; it does not auto-contact prospects.
