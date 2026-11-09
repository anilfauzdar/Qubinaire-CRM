# Qubinaire CRM – Detailed Source Audit

Audit date: 2026-11-09
Package audited: Qubinaire_CRM_AUDITED_GITHUB_READY.zip
Result package: Qubinaire_CRM_FINAL_REVIEW_GITHUB_READY.zip

## Confirmed defect found and fixed
**Critical – normal lead creation failed.** The API `/v1/leads` handler referenced
`body.source_url`, but the `LeadCreate` request model has no such field. It also
attempted to insert every ordinary lead into `lead_hunter_candidates`, whose
`source_url` column is required. This would cause normal lead creation to fail
with a server error and roll back the transaction. The unrelated candidate-table
insert was removed. Lead Hunter imports still use their dedicated endpoints.

A regression test was added so standard lead creation does not depend on
`source_url`.

## Documentation corrections
`ONE_TIME_SETUP.md` previously said offline sync covered leads only, although
the current Flutter source and API include leads plus 12 writable modules and a
read-only employee directory. It now reflects the implemented source and limits.
`FINAL_PRODUCT_SCOPE.md` was replaced because it contained obsolete claims that
sync was only an event relay and not implemented.

## Checks run
- ZIP extraction and integrity: PASS.
- Python syntax parsing: PASS for project Python source.
- Pytest before patch: 1 passed.
- Static security script: PASS (limited heuristic checks only).
- Offline sync static contract: PASS.
- 23 Jinja templates parsed in the earlier package audit: PASS.
- Docker Compose and GitHub Actions YAML parsing: PASS in the earlier package audit.
- Post-fix regression suite: run at package-generation time.

## Open risks / checks not completed
1. Docker image builds and live PostgreSQL schema/migration execution were not run.
2. Browser login, lead create/edit, admissions/payments/refunds and role permissions
   were not exercised end-to-end against a live database.
3. Flutter `analyze`, dependency resolution, Android APK build, Windows build and
   physical-device tests were not run (Flutter SDK unavailable here).
4. Offline sync has static contract coverage only; true two-device concurrency,
   conflict resolution, reconnect/retry and pagination need live staging tests.
5. Local SQLite is not SQLCipher encrypted. Do not store sensitive real student/
   employee data on unmanaged devices.
6. API login has no explicit rate limiter/lockout. Add reverse-proxy rate limiting
   and monitoring before any wider deployment.
7. Portal sessions are held in process memory; Compose uses one Gunicorn worker.
   Restarting the portal logs users out.
8. Generic Flutter module editor is JSON-based, not a polished staff UI.
9. Offline deletes, attachments and Android background sync after force-close
   are not implemented.
10. k6, Playwright and security checklist files are test assets, not proof that
    those tests have passed.

## Deployment decision
**Not production-ready.** Use only for controlled technical staging/private pilot
with dummy or non-sensitive test data after configuring secrets. Never commit real
credentials, `.env`, database files, backups, logs or personal data to public GitHub.

## Canonical docs
Start with `README.md`, `ONE_TIME_SETUP.md`, `PROJECT_STATUS.md`,
`FINAL_PRODUCT_SCOPE.md` and `SECURITY_REVIEW_CHECKLIST.md`.
Version-labelled README files are historical references.
