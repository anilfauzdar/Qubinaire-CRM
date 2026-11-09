# Security release gate

This is a self-review checklist, not a completed independent security audit.

## Required before public/production access
- Put API and portal behind TLS reverse proxy; never expose plain HTTP login over public networks.
- Use unique strong secrets, rotate bootstrap key, remove it after setup if no longer needed.
- Restrict database to private Docker network; maintain encrypted off-site backups and restore drills.
- Replace portal in-memory session dictionary with Redis/database session store before >1 portal worker.
- Add distributed rate limiting and login lockout (Redis or gateway), alerting and session revocation UI.
- Review every API role/ownership path, especially manager reassignment and approval endpoints.
- Add CSRF protection to every state-changing browser form; ensure reverse proxy preserves secure cookies.
- Add audit retention policy, PII retention/deletion process and consent handling.
- Add SAST, dependency vulnerability scan, secret scan, DAST and independent penetration test.
- Test backup restore, disaster recovery, device revocation and sync conflict handling.
- Run 250/1k/2.5k/5k staged load test with production-like hardware and realistic data.
- Obtain legal/privacy review for public prospect research and ensure users verify source rights before CRM import.

## Current known limitations
- Portal session storage is process memory and requires one worker; restart logs portal sessions out.
- Lead Hunter requires EXA_API_KEY and returns public source candidates only; it does not verify contact accuracy.
- Flutter offline cache/outbox covers leads and all writable core CRM modules; deletes and attachments are disabled. Conflict rejection is visible locally, but assisted conflict-resolution UI is still required.
- Android/Windows builds are delegated to local SDK scripts or GitHub Actions; no signed binaries included.
- No independent security audit or 5,000-user benchmark has been performed.

- Encrypt local SQLite databases (SQLCipher or platform-backed database encryption) before storing real student PII on devices.
