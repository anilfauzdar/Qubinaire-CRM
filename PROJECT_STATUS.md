Qubinaire CRM Consolidated Build – Development/Pilot Foundation

Implemented in this package:
- PostgreSQL schema and FastAPI authentication, role-scoped leads, dashboard,
  module CRUD APIs, device event relay, employee management and audit records.
- Flask central portal with login, dashboard, student/college leads, lead edit,
  employee/team management, schema-driven module forms and approvals.
- CSRF token checks for POST forms; single Gunicorn worker because browser sessions
  currently live in process memory.
- First-admin bootstrap, SQLite-to-PostgreSQL import utility, PostgreSQL backup/restore.
- Flutter shared Android/Windows client source with per-user SQLite cache and outbox for leads and all writable core CRM modules; employee directory is read-only cached.
- n8n daily summary workflow template.
- Previous V2–V14 source archives retained.

Checks performed:
- Python syntax compilation passed for API, portal, migration and bootstrap scripts.
- Jinja parsing passed for all 23 portal templates.
- Docker Compose YAML parsed; services db/api/portal confirmed.
- API write-config columns matched PostgreSQL schema table columns.
- Portal module form fields matched API allowlists.
- ZIP integrity checked after packaging.

Not tested:
- Docker image builds, live PostgreSQL migration, HTTP/browser integration, Flutter
  compilation, Android/Windows installation, real offline sync, security audit or load.
- Environment did not have Docker, Flutter, Flask or psycopg runtime installed.
Therefore this is not a certified production release. Use dummy data in a private
staging environment until all release acceptance checks pass.

Additional integrated engineering work:
- User-bound device registration and multi-module offline sync for leads, activities,
  followups, daily reports, courses, admissions, payments, targets, attendance,
  leave requests, refund requests, incentive payouts and incentive settings. Includes
  role-scoped snapshots/pull, durable idempotency, local-to-server ID mapping,
  optimistic conflict checks, automatic retry and ordered event commit locking.
- Exa public-web Lead Hunter API + portal UI, human-reviewed import flow.
- Flutter secure token storage, per-user local cache, offline relaunch, 30-second
  foreground sync, connectivity-restoration sync and resume sync.
- Android/Windows build scripts, GitHub Actions build workflow and Inno Setup
  Windows installer definition.
- Live smoke, Playwright browser smoke, static security review and 5k-VU k6
  test assets prepared. None of the live, browser, security or load tests have
  been executed in this environment.
- WhatsApp integration intentionally excluded.

Further integration:
- Optional Docker-profile scheduled Lead Hunter worker reads configured query
  strings, uses a dedicated manager/admin service account, deduplicates public
  source URLs, and auto-imports review_required records. No outreach is sent.
- Lead Hunter candidate/run tables added to fresh schema and migration 002.
- Initial mobile sync bootstrap and per-user local database partitioning added.
- Offline cache now covers all current writable core modules and read-only users.
  Delete sync and attachments are intentionally disabled; generic module editor is JSON-based.
- Admin device inventory/revocation API added.
- Optional private VPN/LAN bind address is configurable; loopback remains default.
