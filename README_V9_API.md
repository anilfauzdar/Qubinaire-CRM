# Qubinaire CRM V9 — Central API Foundation (Preview)

V9 retains the V8 CRM application and archives V2–V8. It adds a separate FastAPI + PostgreSQL service foundation for future Android/Windows clients.

## Start (Windows)
1. Install Docker Desktop and start it.
2. Run `START_V9_API.bat` once; it creates `.env` from the example and stops for configuration.
3. Edit `.env`: set two different long random secrets for `POSTGRES_PASSWORD` and `BOOTSTRAP_KEY`.
4. Run `START_V9_API.bat` again.
5. Open `http://127.0.0.1:8080/docs`; health: `http://127.0.0.1:8080/health`.
6. Existing V8 web CRM runs separately with `START_QUBINAIRE_V8.bat`.

## API outline
- `POST /v1/devices/register` — requires `X-Bootstrap-Key`; returns a one-time device bearer token.
- `POST /v1/sync/push` — authenticated device submits up to 200 change events. `change_id` is idempotent.
- `GET /v1/sync/pull?since=<ISO timestamp>` — authenticated device receives other devices' events.
- `GET /health` — database connectivity check.

## Important scope boundary
This is a foundation, NOT production-ready multi-device synchronization. Events are persisted and relayed, but V9 does not yet apply them to the legacy CRM's lead/admission tables, perform field-level conflict resolution, encrypt device storage, provide user-level API authorization, offer token rotation/revocation UI, or run 300-user load/security tests. Pull currently returns events from other devices, not a per-device acknowledged cursor. Do not expose port 8080 publicly or enter real personal/student data. Use only dummy data on a trusted local test machine.

The legacy Flask CRM remains SQLite and is not automatically connected to PostgreSQL in this version. PostgreSQL is the new API event store, not yet the authoritative CRM database.
