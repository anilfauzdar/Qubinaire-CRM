# Qubinaire CRM V14 – Central Portal CRUD Preview

V14 extends V13 with browser workflows to create and edit records for:
activities, followups, daily_reports, courses, admissions, payments, attendance,
leave_requests, refund_requests, incentive_payouts and targets.

## Start
1. Extract the ZIP on the office Windows PC with Docker Desktop installed.
2. Open `.env` and set strong unique values for `POSTGRES_PASSWORD`, `BOOTSTRAP_KEY`,
   and `PORTAL_SECRET`.
3. Run `START_V14_PORTAL.bat`.
4. Open `http://127.0.0.1:5001`. API docs: `http://127.0.0.1:8080/docs`.

## Create/edit records
Open Modules, choose a module, then use New record or Edit. The portal accepts a
JSON object. Required fields and permissions are enforced by the Central API.
Dates use YYYY-MM-DD; timestamps should be ISO-8601. Related IDs (lead, admission,
payment, employee) must already exist and be visible to the logged-in user.

## Important limitations
- This is a development preview, not production-ready software.
- Module create/edit uses JSON payloads, not polished business forms.
- The portal still has in-process server sessions; a portal restart logs users out.
- No CSRF protection, rate limiting, TLS reverse proxy, security audit or load test.
- The API and PostgreSQL stack have not been live-integrated or load-tested here.
- The old Flask/SQLite interface remains separate and is not connected to this portal.
- No native Android APK, Windows EXE, or verified offline-first device sync yet.
- Keep access bound to localhost/private test network and use dummy data until a
  proper security review and deployment validation are completed.
- Backups from earlier versions are retained in ARCHIVE; this package does not
  contain your live office database unless you separately provide it.

## Version continuity
`ARCHIVE/Qubinaire_CRM_V13_MASTER.zip` preserves the V13 master package.
Earlier source snapshots and ZIP archives from V2 onward are retained from V13.
