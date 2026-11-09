# Qubinaire CRM V12 — Core Module Write APIs (Development Preview)

V12 builds on V11. It adds authenticated Create and Update API endpoints for the major CRM modules, using explicit field allowlists and role/record ownership checks.

## New write endpoints
- `POST /v1/modules/activities`
- `POST /v1/modules/followups`
- `POST /v1/modules/daily_reports`
- `POST /v1/modules/courses` (admin)
- `POST /v1/modules/admissions`
- `POST /v1/modules/payments`
- `POST /v1/modules/targets` (admin/manager restrictions)
- `POST /v1/modules/attendance`
- `POST /v1/modules/leave_requests`
- `POST /v1/modules/refund_requests`
- `POST /v1/modules/incentive_payouts` (admin)
- `POST /v1/modules/incentive_settings` (admin; singleton row)
- Matching `PATCH /v1/modules/{module}/{record_id}` for supported modules.
- `GET /v1/meta/modules` lists available write modules.

All endpoints require a bearer token from `/v1/auth/login`. Lead-linked records validate access to the linked lead. Employee assignments are checked against role and direct-report relationships. Creates and updates write audit entries.

## Upgrade an existing V11 database
Schema init scripts run automatically only when the PostgreSQL data volume is first created. For an existing V11 database, apply the additive schema manually:
`docker compose exec db psql -U qubinaire -d qubinaire -f /docker-entrypoint-initdb.d/001-schema.sql`
The schema uses `CREATE TABLE IF NOT EXISTS`, so this does not drop existing tables.

## Test
1. Run Docker/API using the V11 instructions in `README_V11.md`.
2. Open `http://127.0.0.1:8080/docs`.
3. Login with `POST /v1/auth/login`, copy `access_token`, click Authorize and enter `Bearer YOUR_TOKEN`.
4. Use `GET /v1/meta/modules`, then create a test record with dummy data.
5. Verify the result through `GET /v1/modules/{module}` and audit table in PostgreSQL.

## Boundaries / safety
- V12 does not yet connect the old Flask UI to PostgreSQL. The old UI continues to use its SQLite database.
- No automatic bi-directional sync from legacy UI to the API.
- API does not implement full delete/restore workflow, approvals UI, per-field conflict resolution, or nested manager hierarchy.
- No native Android/Windows app, offline durable queue, Docker live integration test, security audit, or load test was completed here.
- Use only dummy data until staging and security tests pass. Keep the API bound to localhost; do not expose it publicly.
