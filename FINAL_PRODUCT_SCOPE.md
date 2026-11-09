# Qubinaire CRM – Current Consolidated Product Scope

This document describes the source actually present in this repository. It is a
private pilot foundation, not a certified production release.

## Included source
- FastAPI central API backed by PostgreSQL, with authentication, roles, lead
  management, employee administration, audit records and core module APIs.
- Flask browser portal using the central API.
- Core modules: leads, activities, follow-ups, daily reports, courses, admissions,
  payments, targets, attendance, leave requests, refund requests, incentive
  payouts and incentive settings.
- Flutter Android/Windows shared client source with per-user SQLite cache/outbox:
  leads and 12 writable modules; employee directory is read-only.
- Device registration/revocation, event pull/push, role-scoped snapshots,
  idempotency, local-to-server ID mapping and conflict checks.
- Exa public-web Lead Hunter and optional scheduled worker. Imports remain
  `review_required`; no WhatsApp or outbound messaging is included.
- Docker Compose deployment foundation, bootstrap, SQLite-to-PostgreSQL import,
  PostgreSQL backup/restore scripts, GitHub Actions client build workflow,
  n8n template and test assets.

## Known limitations
- Offline deletes and attachments are disabled.
- Android background sync after force-close is not implemented.
- Generic module editor is JSON-based and needs UX refinement.
- Local SQLite is not SQLCipher-encrypted.
- No signed APK or Windows installer is included in the source package.
- Docker/PostgreSQL live integration, browser E2E, Flutter builds/device tests,
  multi-device conflict tests, penetration testing and 5,000-user load testing
  have not been completed in this environment.
- College partnership pipeline, placement/interview workflow, franchise
  management and WhatsApp provider integration are not implemented here.

## Release acceptance checklist
Do not use real student/employee data until all items pass in a private staging
environment:
- [ ] Docker images build and Compose starts cleanly.
- [ ] Fresh schema, migration 002 and legacy SQLite import are reconciled.
- [ ] Admin, manager and sales permission tests pass for every endpoint/module.
- [ ] Lead, admission, payment, refund and incentive workflows pass end-to-end.
- [ ] Offline create/edit, retries, duplicate delivery and conflict resolution pass.
- [ ] Android APK and Windows app build, install, update and pass device tests.
- [ ] TLS, CSRF, rate limiting, secrets, audit logging and backup restore are reviewed.
- [ ] Off-host backups and disaster-recovery restore drill succeed.
- [ ] Performance/load targets are tested on representative staging infrastructure.
