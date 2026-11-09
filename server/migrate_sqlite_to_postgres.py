import os, sys, sqlite3
from datetime import date, datetime, timezone
from sqlalchemy import create_engine, text

TABLES = {
 "users": ["id","username","full_name","password_hash","role","active","manager_id","created_at"],
 "leads": ["id","lead_type","name","phone","email","institution","course_interest","city","district","state","source","status","owner_id","notes","created_at","updated_at"],
 "courses": ["id","name","fee","active"],
 "activities": ["id","lead_id","employee_id","activity_type","notes","outcome","occurred_at"],
 "followups": ["id","lead_id","employee_id","due_at","status","notes","created_at"],
 "daily_reports": ["id","user_id","report_date","calls","connected_calls","whatsapp_followups","new_leads","meetings","college_visits","admissions","remarks","submitted_at"],
 "targets": ["id","user_id","period","start_date","end_date","leads_target","admissions_target","created_by"],
 "admissions": ["id","lead_id","course_id","admission_no","total_fee","status","admission_date","created_by","created_at"],
 "payments": ["id","admission_id","amount","mode","reference","status","payment_date","created_by"],
 "attendance": ["id","user_id","work_date","check_in","check_out","note"],
 "incentive_settings": ["id","collection_rate","admission_bonus","updated_at"],
 "leave_requests": ["id","user_id","leave_type","start_date","end_date","reason","status","reviewed_by","reviewed_at","review_note","created_at"],
 "refund_requests": ["id","payment_id","requested_amount","reason","status","requested_by","reviewed_by","reviewed_at","review_note","created_at"],
 "incentive_payouts": ["id","user_id","period_start","period_end","estimated_amount","approved_amount","status","approved_by","approved_at","note","created_at"],
 "sync_events": ["id","device_id","record_id","entity","status","details","created_at"],
 "audit_logs": ["id","actor_id","action","entity","entity_id","details","created_at"],
}
BOOL_COLS = {("users","active"),("courses","active")}
SEQUENCE_TABLES = ["users","courses","targets","sync_events","attendance","leave_requests","refund_requests","incentive_payouts","audit_logs"]

if len(sys.argv)<2:
    raise SystemExit("Usage: python migrate_sqlite_to_postgres.py PATH_TO_qubinaire_crm.db")
source=sys.argv[1]
if not os.path.isfile(source): raise SystemExit(f"SQLite database not found: {source}")
url=os.environ.get("DATABASE_URL")
if not url: raise SystemExit("Set DATABASE_URL before running this migration.")
src=sqlite3.connect(f"file:{os.path.abspath(source)}?mode=ro",uri=True)
src.row_factory=sqlite3.Row
integrity=src.execute("PRAGMA integrity_check").fetchone()[0]
if integrity!="ok": raise SystemExit(f"SQLite integrity check failed: {integrity}")
available={r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
if not {"users","leads"}.issubset(available): raise SystemExit("Source must contain users and leads tables.")
counts={}
engine=create_engine(url,pool_pre_ping=True)
with engine.begin() as dst:
    existing=dst.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
    if existing: raise SystemExit("Target PostgreSQL already has users. Migration stopped; do not overwrite or merge.")
    # Import in FK-safe order. Tables absent in older versions are skipped.
    order=["users","leads","courses","activities","followups","daily_reports","targets","admissions","payments",
           "attendance","incentive_settings","leave_requests","refund_requests","incentive_payouts","sync_events","audit_logs"]
    for table in order:
        if table not in available: continue
        cols={r[1] for r in src.execute(f"PRAGMA table_info({table})")}
        fields=[c for c in TABLES[table] if c in cols]
        rows=src.execute(f"SELECT {','.join(fields)} FROM {table}").fetchall()
        if not rows: counts[table]=0; continue
        # Users are inserted before hierarchy pointers to support arbitrary row order.
        if table=="users" and "manager_id" in fields:
            for row in rows:
                d=dict(row); d["manager_id"]=None
                d["active"]=bool(d["active"])
                names=[c for c in fields if c!="manager_id"]
                sql=f"INSERT INTO users ({','.join(names)},manager_id) VALUES ({','.join(':'+c for c in names)},NULL)"
                dst.execute(text(sql),{c:d[c] for c in names})
            for row in rows:
                d=dict(row)
                if d.get("manager_id") is not None:
                    dst.execute(text("UPDATE users SET manager_id=:m WHERE id=:i"),{"m":d["manager_id"],"i":d["id"]})
        else:
            for row in rows:
                d=dict(row)
                date_cols={"report_date","start_date","end_date","admission_date","payment_date","work_date","period_start","period_end"}
                timestamp_cols={"created_at","updated_at","submitted_at","occurred_at","due_at","check_in","check_out","reviewed_at","approved_at"}
                for c in fields:
                    if (table,c) in BOOL_COLS and d[c] is not None:
                        d[c]=bool(d[c])
                    elif d[c] is not None and c in date_cols and isinstance(d[c],str):
                        d[c]=date.fromisoformat(d[c][:10])
                    elif d[c] is not None and c in timestamp_cols and isinstance(d[c],str):
                        val=d[c].replace("Z","+00:00")
                        parsed=datetime.fromisoformat(val)
                        d[c]=parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
                names=",".join(fields)
                params=",".join(":"+c for c in fields)
                dst.execute(text(f"INSERT INTO {table} ({names}) VALUES ({params})"),d)
        counts[table]=len(rows)
    for table in SEQUENCE_TABLES:
        if table in available:
            dst.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}','id'), COALESCE((SELECT MAX(id) FROM {table}),1), true)"))
print("Migration completed. Imported row counts:")
for table,count in counts.items(): print(f"  {table}: {count}")
print("Source SQLite was opened read-only and was not modified.")
print("API sessions and registered devices are intentionally NOT migrated; users must sign in again and re-register devices.")
