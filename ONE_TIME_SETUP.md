# One-time setup (pilot)

1. Install Docker Desktop on the office Windows PC, or Docker Engine on Ubuntu.
2. Copy `.env.production.example` to `.env`; set unique strong values for PostgreSQL and portal secrets.
3. Review `docker-compose.yml` and firewall rules. Keep API and portal private.
   For Android/Windows devices over an office VPN, set `CRM_BIND_ADDRESS=0.0.0.0`
   only when the host firewall restricts access to that private VPN/subnet; do not
   expose plain HTTP endpoints to the public internet.
4. Run `docker compose up -d --build`.
5. Check `http://127.0.0.1:8080/health` and `http://127.0.0.1:5001`.
6. Import the legacy database only after making a separate copy and reviewing the migration report.
7. Create/verify admin user credentials in the central database using the documented migration/bootstrap procedure.
8. For Flutter client builds, install Flutter SDK and follow `clients/flutter/README.md`.
9. Import n8n workflow only after configuring API credentials and a notification node/channel.

Do not expose the portal/API directly to the public internet. Configure TLS reverse
proxy, firewall allowlists, CSRF, rate limits, external backups and monitoring
before production.

## First administrator (only on a clean database)
After `docker compose up -d --build`, create the first admin only if the
PostgreSQL users table is empty:
- `docker compose exec -e CRM_ADMIN_USERNAME=admin -e CRM_ADMIN_NAME="Qubinaire Admin" -e CRM_ADMIN_PASSWORD="YOUR_LONG_UNIQUE_PASSWORD" api python bootstrap_admin.py`
- Use that username/password at the portal login.
If you are migrating an existing CRM database, do not create a new admin first;
migrate users and verify the admin account instead. The bootstrap refuses to
run when users already exist.

## Database backup / restore
- Run `BACKUP_POSTGRES.bat` for a PostgreSQL custom-format dump.
- Restore only after stopping writes and taking a fresh backup:
  `RESTORE_POSTGRES.bat backups\\your-file.dump`
- Copy backups to a separate drive or secure cloud storage. A backup on the same
  office PC is not protection against disk failure.

## Import an existing SQLite CRM database
Only migrate after the PostgreSQL database is clean and a separate copy of the
SQLite file exists. First copy the source DB into the running API container:
- `docker compose cp C:\\path\\to\\qubinaire_crm.db api:/tmp/qubinaire_crm.db`
Then run:
- `docker compose exec api python migrate_sqlite_to_postgres.py /tmp/qubinaire_crm.db`
The script refuses to import if PostgreSQL already has users, imports known
legacy tables in dependency order, and opens the source read-only. Review row
counts and reconcile them before staff login. Do not run bootstrap_admin.py
after migrating users.

## AI Lead Hunter (WhatsApp intentionally excluded)
- Add `EXA_API_KEY=...` to `.env` to enable Exa public-web search.
- Rebuild/restart: `docker compose up -d --build`.
- Sign in as admin/manager, open AI Lead Hunter, search public sources and
  import only candidates you have reviewed. The workflow does not scrape
  private phone numbers or auto-message prospects.
- Existing V14 PostgreSQL installs: back up first, then run
  `APPLY_MIGRATIONS_002.bat` to add user-bound devices and Lead Hunter run logs.
  Fresh databases get the latest `server/schema.sql` automatically.

## Mobile/Windows sync pilot
- Build the APK/Windows installer with the provided scripts or GitHub Actions.
- Set the central API URL to a secure office/VPN endpoint on the device.
- The first sync bootstraps permitted leads, all 12 writable core modules, and
  the read-only employee directory. Queued creates/edits sync while the app is
  open (30-second interval), on connectivity restoration, and on app resume.
- Offline deletes, attachments, and Android background sync after force-close
  are not implemented. The general module editor is JSON-based and local SQLite
  is not SQLCipher-encrypted. Use dummy/pilot data until release gates are closed.

## Optional scheduled AI Lead Hunter worker
1. Set `EXA_API_KEY` in `.env`.
2. In CRM, create a dedicated Manager service account with a long unique password.
3. Set `LEAD_HUNTER_USERNAME`, `LEAD_HUNTER_PASSWORD`, and
   `LEAD_HUNTER_QUERIES` in `.env`. Query format:
   `college:engineering colleges in Madhya Pradesh||student:public student portfolio profiles`
4. Start the worker: `docker compose --profile lead-hunter up -d --build`.
5. View worker logs: `docker compose logs -f lead-hunter-worker`.

The worker runs each configured query on the interval in `.env`, deduplicates
by public source URL, and imports only review_required leads. It does not
extract private phone numbers, send WhatsApp/SMS/email, or contact prospects.
Use query volumes consistent with your Exa plan and manually verify all leads.
