# Qubinaire CRM V10 — PostgreSQL User & Lead API (Development Preview)

## What is added
- Central API login against migrated CRM users using the existing PBKDF2 password hashes.
- 12-hour bearer sessions stored as SHA-256 token hashes.
- `/v1/me`, role-scoped `/v1/leads` listing, lead creation and optimistic-concurrency lead updates.
- Access scope: admin sees all; manager sees own leads and direct reports' leads; sales sees only owned leads.
- Audit entries for API login and lead create/update.
- SQLite-to-PostgreSQL migration script for users and leads (source is read-only; target must have zero users).

## Setup
1. Install Docker Desktop.
2. Run `START_V9_API.bat` once, edit `.env` with strong different secrets, run it again.
3. Confirm API health at `http://127.0.0.1:8080/health`.
4. Find your legacy SQLite database, normally `data/qubinaire_crm.db`.
5. From the extracted V10 folder, open terminal and run:
   `docker compose exec -T api python -c "print('Use the migration script from a Python environment with SQLAlchemy installed')"`
   Recommended safe migration command on a machine with Python, SQLAlchemy and psycopg installed:
   `set DATABASE_URL=postgresql+psycopg://qubinaire:YOUR_PASSWORD@localhost:5432/qubinaire`
   `pip install SQLAlchemy psycopg[binary]`
   `python server/migrate_sqlite_to_postgres.py "PATH_TO\qubinaire_crm.db"`
   The migration refuses to run if target already contains users. Take a separate backup first.
6. API docs: `http://127.0.0.1:8080/docs`.

## Important limitations
- The legacy Flask UI still reads/writes SQLite. V10 does NOT silently switch it to PostgreSQL.
- Migration currently covers users and leads only. Activities, followups, daily reports, courses, admissions, payments, targets, attendance, leave, refunds, and incentive records remain in SQLite.
- Manager scope is direct reports only; nested hierarchy is not yet supported.
- No mobile/Windows client, offline queue, conflict-resolution UI, token revocation UI, TLS reverse proxy, production secrets manager, security audit, or load test yet.
- Do not expose API publicly or use real student data until security and integration testing are completed.
