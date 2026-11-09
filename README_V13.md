# Qubinaire CRM V13 — Central Web Portal (Development Preview)

## What V13 adds
A new browser portal (`portal/`) that authenticates against the PostgreSQL Central API. It does not read the old SQLite database.
- Login using migrated CRM user credentials.
- Dashboard metrics from `/v1/dashboard/summary`.
- Leads list and lead creation through the central API.
- Read views for activities, follow-ups, reports, courses, admissions, payments, attendance, leave, refunds, incentives and targets.
- Opaque random browser session ID; API bearer token stays in the portal server's in-memory session store.
- Docker Compose service on localhost port 5001.

## Start
1. Install and start Docker Desktop.
2. Run `START_V13_PORTAL.bat` once. It creates `.env` from the example and stops.
3. Edit `.env` and set three different long random secrets: `POSTGRES_PASSWORD`, `BOOTSTRAP_KEY`, `PORTAL_SECRET`.
4. Run `START_V13_PORTAL.bat` again.
5. Central portal: `http://127.0.0.1:5001`
6. API documentation: `http://127.0.0.1:8080/docs`
7. Portal health: `http://127.0.0.1:5001/health`

## First use
- The PostgreSQL database must already be initialized.
- Migrate your SQLite database using the V11 migration instructions in `README_V11.md` (migration script retained in `server/`).
- Login with a user account that was migrated from the old CRM.
- If PostgreSQL was previously initialized with an older schema, apply the additive schema instructions in `README_V12.md` before using V13 endpoints.

## Important
- The old Flask app still runs separately and continues to use SQLite. V13 introduces a separate central portal; it does not transparently switch the old interface.
- Portal sessions are in process memory and are lost if the portal container restarts. A user signs in again.
- This is a single-node preview. Add Redis/server-side session storage, CSRF protection, TLS reverse proxy, rate limiting, stronger audit/security review and production deployment controls before internet exposure.
- The portal currently provides lead creation and module read views. Other module write APIs are available through the API docs, but their full forms/approval workflows are not yet in the portal.
- No Docker build, live API/database integration, browser test, load test or penetration test was run in this environment. Use dummy data in a private test environment only.
