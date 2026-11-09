# Qubinaire CRM V11 — Full CRM Data Migration + Module API (Development Preview)

## V11 additions
- PostgreSQL schema now covers all major legacy CRM tables: users, leads, activities, followups, daily reports, courses, admissions, payments, targets, attendance, incentives, leave, refunds, sync events and audit logs.
- SQLite migration utility imports those tables in foreign-key-safe order, preserves IDs and manager relationships, converts dates/timestamps and resets identity sequences.
- Migration reads SQLite in read-only mode and refuses to import if the PostgreSQL target already contains users. It does not merge databases.
- API now exposes role-scoped module listing at `/v1/modules/{module}` and a role-scoped summary at `/v1/dashboard/summary`.
- Existing V10 login, user session, lead create/update, optimistic version check and audit trail remain.

## Migration steps (Windows)
1. Make a separate copy of your SQLite database. Do not use the only copy.
2. Start Docker with `START_V9_API.bat`; set strong secrets in `.env`.
3. The PostgreSQL port is bound only to `127.0.0.1:5432`.
4. On the same PC, install Python 3.12 and run:
   `py -m pip install SQLAlchemy psycopg[binary]`
5. In Command Prompt, set the DB connection:
   `set DATABASE_URL=postgresql+psycopg://qubinaire:YOUR_POSTGRES_PASSWORD@127.0.0.1:5432/qubinaire`
6. Run:
   `py server\migrate_sqlite_to_postgres.py "C:\path\to\data\qubinaire_crm.db"`
7. Review the printed per-table row counts. Keep the original SQLite file and its backup unchanged.
8. API docs: `http://127.0.0.1:8080/docs`.

## API endpoints
- `POST /v1/auth/login` — username/password from migrated CRM users; returns 12-hour bearer token.
- `GET /v1/me`
- `GET /v1/leads`, `POST /v1/leads`, `PATCH /v1/leads/{lead_id}`
- `GET /v1/modules/{module}` — activities, followups, daily_reports, courses, admissions, payments, attendance, leave_requests, refund_requests, incentive_payouts, targets.
- `GET /v1/dashboard/summary`
- `POST /v1/devices/register`, `POST /v1/sync/push`, `GET /v1/sync/pull`.

## Important limitations
- The old Flask web UI still reads and writes SQLite; V11 does not yet switch the UI to PostgreSQL. Do not enter the same records into both systems.
- Module list endpoints are read-only. Write endpoints for all modules, end-to-end UI integration and automatic background migration are future work.
- Sync endpoints remain an event relay; events are not yet materialized into CRM tables and conflict resolution across offline devices is not implemented.
- API role scoping is an initial implementation, not a completed security audit. Manager hierarchy currently means direct reports only.
- No Docker build, live PostgreSQL integration, full HTTP integration, load test, penetration test, or production certification has been run in this environment.
- Keep API bound to localhost; do not expose it publicly or use real student/customer data until full testing and security hardening.
