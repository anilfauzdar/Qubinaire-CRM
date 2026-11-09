import os, uuid, hashlib, secrets, hmac, json, urllib.request, urllib.error
from datetime import date, datetime, timezone, timedelta
from typing import Any
from fastapi import FastAPI, Header, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://qubinaire:change-me@db:5432/qubinaire")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=8, max_overflow=5, pool_recycle=1800)
app = FastAPI(title="Qubinaire CRM Central API", version="1.3.0")

def utcnow(): return datetime.now(timezone.utc)
def token_hash(token: str) -> str: return hashlib.sha256(token.encode()).hexdigest()

def hash_password(password: str) -> str:
    salt=secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,310000).hex()
    return salt.hex()+"$"+digest

def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, expected = stored.split("$", 1)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 310000).hex()
        return hmac.compare_digest(actual, expected)
    except Exception: return False

class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)

class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=14, max_length=256)
    role: str = Field(pattern="^(admin|manager|sales)$")
    manager_id: int | None = None
    active: bool = True

class UserPatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    password: str | None = Field(default=None, min_length=14, max_length=256)
    role: str | None = Field(default=None, pattern="^(admin|manager|sales)$")
    manager_id: int | None = None
    active: bool | None = None

class DeviceRegistration(BaseModel):
    device_name: str = Field(min_length=2, max_length=120)
    platform: str = Field(pattern="^(android|windows|web)$")

class LeadCreate(BaseModel):
    id: str | None = None
    lead_type: str = Field(pattern="^(student|college)$")
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = None
    email: str | None = None
    institution: str | None = None
    course_interest: str | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = None
    source: str | None = None
    status: str = "new"
    owner_id: int | None = None
    notes: str | None = None

class LeadPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = None
    email: str | None = None
    institution: str | None = None
    course_interest: str | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = None
    source: str | None = None
    status: str | None = None
    owner_id: int | None = None
    notes: str | None = None
    expected_version: int

class SyncChange(BaseModel):
    change_id: str = Field(min_length=8, max_length=80)
    entity: str = Field(pattern="^(lead|activities|followups|daily_reports|courses|admissions|payments|targets|attendance|leave_requests|refund_requests|incentive_payouts|incentive_settings)$")
    record_id: str = Field(min_length=1, max_length=100)
    operation: str = Field(pattern="^(upsert|delete)$")
    payload: dict[str, Any] = Field(default_factory=dict)
    client_updated_at: datetime | None = None

class SyncPush(BaseModel):
    device_id: str
    changes: list[SyncChange] = Field(max_length=200)

class LeadHunterRequest(BaseModel):
    query: str = Field(min_length=4, max_length=500)
    target_type: str = Field(default="college", pattern="^(student|college)$")
    num_results: int = Field(default=10, ge=1, le=20)
    auto_import: bool = False

class LeadHunterImport(BaseModel):
    lead_type: str = Field(pattern="^(student|college)$")
    name: str = Field(min_length=2, max_length=200)
    institution: str | None = None
    city: str | None = None
    state: str | None = None
    source_url: str = Field(min_length=8, max_length=2000)
    notes: str | None = None

def current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "User bearer token required")
    raw = authorization[7:].strip()
    with engine.begin() as conn:
        row = conn.execute(text("""SELECT u.id,u.username,u.full_name,u.role,u.manager_id
            FROM api_sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=:h AND s.expires_at>:now AND u.active=TRUE"""),
            {"h":token_hash(raw),"now":utcnow()}).mappings().first()
    if not row: raise HTTPException(401, "Session expired or invalid")
    return dict(row)

def require_device(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Device bearer token required")
    raw=authorization[7:].strip()
    with engine.begin() as conn:
        row=conn.execute(text("""SELECT d.id,d.user_id,d.active,u.role,u.manager_id
            FROM devices d JOIN users u ON u.id=d.user_id
            WHERE d.token_hash=:h AND u.active=TRUE"""),{"h":token_hash(raw)}).mappings().first()
    if not row or not row["active"]: raise HTTPException(401,"Invalid or inactive device token")
    return dict(row)

def emit_sync_change(conn, actor_id, entity, record_id, operation, payload):
    # Serialize event-producing transactions so BIGSERIAL cursors cannot skip a late commit.
    conn.execute(text("SELECT pg_advisory_xact_lock(73201401)"))
    conn.execute(text("""INSERT INTO sync_changes(change_id,device_id,entity,record_id,operation,payload,client_updated_at,received_at)
        VALUES(:cid,NULL,:entity,:rid,:op,CAST(:payload AS JSONB),NULL,:received)"""),
        {"cid":str(uuid.uuid4()),"entity":entity,"rid":str(record_id),"op":operation,
         "payload":json.dumps({**payload,"actor_id":actor_id},default=str),"received":utcnow()})

def can_view_lead(conn, user, lead):
    if user["role"]=="admin": return True
    if lead["owner_id"]==user["id"]: return True
    if user["role"]=="manager":
        return conn.execute(text("SELECT 1 FROM users WHERE id=:uid AND manager_id=:mid"),
                            {"uid":lead["owner_id"],"mid":user["id"]}).first() is not None
    return False

@app.get("/health")
def health():
    try:
        with engine.connect() as conn: conn.execute(text("SELECT 1"))
        return {"status":"ok","database":"connected","service":"qubinaire-central-api"}
    except Exception: raise HTTPException(503,"Database unavailable")

@app.post("/v1/auth/login")
def login(body: LoginBody):
    with engine.begin() as conn:
        user=conn.execute(text("SELECT id,username,full_name,password_hash,role,active,manager_id FROM users WHERE username=:u"),
                          {"u":body.username}).mappings().first()
        if not user or not user["active"] or not verify_password(body.password,user["password_hash"]):
            raise HTTPException(401,"Invalid username or password")
        raw=secrets.token_urlsafe(48)
        conn.execute(text("INSERT INTO api_sessions(token_hash,user_id,created_at,expires_at) VALUES(:h,:uid,:c,:e)"),
                     {"h":token_hash(raw),"uid":user["id"],"c":utcnow(),"e":utcnow()+timedelta(hours=12)})
        conn.execute(text("INSERT INTO audit_logs(actor_id,action,entity,entity_id,details,created_at) VALUES(:a,'api_login','user',:id,'Central API login',:t)"),
                     {"a":user["id"],"id":str(user["id"]),"t":utcnow()})
    return {"access_token":raw,"token_type":"bearer","expires_in":43200,
            "user":{"id":user["id"],"username":user["username"],"full_name":user["full_name"],
                    "role":user["role"],"manager_id":user["manager_id"]}}

@app.get("/v1/users")
def list_users(limit:int=Query(200,ge=1,le=500),offset:int=Query(0,ge=0),user=Depends(current_user)):
    with engine.begin() as conn:
        if user["role"]=="admin":
            rows=conn.execute(text("""SELECT id,username,full_name,role,active,manager_id,created_at
                FROM users ORDER BY id LIMIT :l OFFSET :o"""),{"l":limit,"o":offset}).mappings().all()
        elif user["role"]=="manager":
            rows=conn.execute(text("""SELECT id,username,full_name,role,active,manager_id,created_at
                FROM users WHERE id=:uid OR manager_id=:uid ORDER BY id LIMIT :l OFFSET :o"""),
                {"uid":user["id"],"l":limit,"o":offset}).mappings().all()
        else:
            rows=conn.execute(text("""SELECT id,username,full_name,role,active,manager_id,created_at
                FROM users WHERE id=:uid"""),{"uid":user["id"]}).mappings().all()
    return {"items":[dict(r) for r in rows],"limit":limit,"offset":offset}

@app.post("/v1/users",status_code=201)
def create_user(body:UserCreate,user=Depends(current_user)):
    if user["role"]!="admin": raise HTTPException(403,"Only admin can create employees")
    if body.manager_id is not None:
        if body.role!="sales": raise HTTPException(422,"Only sales employees can be assigned to a manager")
        with engine.begin() as conn:
            manager=conn.execute(text("SELECT id,role,active FROM users WHERE id=:id"),{"id":body.manager_id}).mappings().first()
            if not manager or manager["role"]!="manager" or not manager["active"]:
                raise HTTPException(422,"manager_id must refer to an active manager")
            try:
                uid=conn.execute(text("""INSERT INTO users(username,full_name,password_hash,role,active,manager_id,created_at)
                    VALUES(:u,:n,:p,:r,:a,:m,:t) RETURNING id"""),
                    {"u":body.username,"n":body.full_name,"p":hash_password(body.password),"r":body.role,
                     "a":body.active,"m":body.manager_id,"t":utcnow()}).scalar_one()
            except IntegrityError as e: raise HTTPException(409,"Username already exists") from e
            _audit(conn,user,"create_employee","user",uid,body.role)
    else:
        with engine.begin() as conn:
            try:
                uid=conn.execute(text("""INSERT INTO users(username,full_name,password_hash,role,active,manager_id,created_at)
                    VALUES(:u,:n,:p,:r,:a,NULL,:t) RETURNING id"""),
                    {"u":body.username,"n":body.full_name,"p":hash_password(body.password),"r":body.role,
                     "a":body.active,"t":utcnow()}).scalar_one()
            except IntegrityError as e: raise HTTPException(409,"Username already exists") from e
            _audit(conn,user,"create_employee","user",uid,body.role)
    return {"id":uid,"created":True}

@app.patch("/v1/users/{user_id}")
def update_user(user_id:int,body:UserPatch,user=Depends(current_user)):
    if user["role"]!="admin": raise HTTPException(403,"Only admin can update employee accounts")
    changes=body.model_dump(exclude_unset=True)
    if not changes: raise HTTPException(400,"No update fields supplied")
    if "password" in changes:
        changes["password_hash"]=hash_password(changes.pop("password"))
    with engine.begin() as conn:
        target=conn.execute(text("SELECT role FROM users WHERE id=:id"),{"id":user_id}).mappings().first()
        if not target: raise HTTPException(404,"Employee not found")
        target_role=changes.get("role",target["role"])
        if changes.get("manager_id") is not None:
            if target_role!="sales": raise HTTPException(422,"Only sales employees can be assigned to a manager")
            if int(changes["manager_id"])==user_id: raise HTTPException(422,"Employee cannot be their own manager")
            manager=conn.execute(text("SELECT id,role,active FROM users WHERE id=:id"),{"id":changes["manager_id"]}).mappings().first()
            if not manager or manager["role"]!="manager" or not manager["active"]:
                raise HTTPException(422,"manager_id must refer to an active manager")
        if target["role"]=="manager" and (target_role!="manager" or changes.get("active") is False):
            reports=conn.execute(text("SELECT COUNT(*) FROM users WHERE manager_id=:id AND active=TRUE"),{"id":user_id}).scalar_one()
            if reports: raise HTTPException(409,"Reassign or deactivate direct reports before changing this manager")
    allowed={"full_name","password_hash","role","manager_id","active"}
    if set(changes)-allowed: raise HTTPException(422,"Unsupported fields")
    with engine.begin() as conn:
        if not conn.execute(text("SELECT 1 FROM users WHERE id=:id"),{"id":user_id}).first():
            raise HTTPException(404,"Employee not found")
        sets=",".join(f"{k}=:{k}" for k in changes)
        params=dict(changes); params["id"]=user_id
        conn.execute(text(f"UPDATE users SET {sets} WHERE id=:id"),params)
        _audit(conn,user,"update_employee","user",user_id,",".join(changes))
    return {"id":user_id,"updated":True}

@app.get("/v1/me")
def me(user=Depends(current_user)):
    return user

@app.get("/v1/leads")
def list_leads(limit:int=Query(100,ge=1,le=500), offset:int=Query(0,ge=0), user=Depends(current_user)):
    with engine.begin() as conn:
        if user["role"]=="admin":
            rows=conn.execute(text("SELECT * FROM leads ORDER BY updated_at DESC LIMIT :l OFFSET :o"),{"l":limit,"o":offset}).mappings().all()
        elif user["role"]=="manager":
            rows=conn.execute(text("""SELECT l.* FROM leads l LEFT JOIN users u ON u.id=l.owner_id
                WHERE l.owner_id=:uid OR u.manager_id=:uid ORDER BY l.updated_at DESC LIMIT :l OFFSET :o"""),
                {"uid":user["id"],"l":limit,"o":offset}).mappings().all()
        else:
            rows=conn.execute(text("SELECT * FROM leads WHERE owner_id=:uid ORDER BY updated_at DESC LIMIT :l OFFSET :o"),
                              {"uid":user["id"],"l":limit,"o":offset}).mappings().all()
    return {"items":[dict(r) for r in rows],"limit":limit,"offset":offset}

@app.post("/v1/leads", status_code=201)
def create_lead(body:LeadCreate,user=Depends(current_user)):
    lead_id=body.id or str(uuid.uuid4())
    owner=body.owner_id if user["role"] in ("admin","manager") and body.owner_id is not None else user["id"]
    with engine.begin() as conn:
        if user["role"]=="manager" and owner!=user["id"]:
            allowed=conn.execute(text("SELECT 1 FROM users WHERE id=:id AND manager_id=:mid AND active=TRUE"),
                                 {"id":owner,"mid":user["id"]}).first()
            if not allowed: raise HTTPException(403,"Managers can assign only to their direct reports")
        elif user["role"]=="admin":
            allowed=conn.execute(text("SELECT 1 FROM users WHERE id=:id AND active=TRUE"),{"id":owner}).first()
            if not allowed: raise HTTPException(422,"Lead owner must be an active employee")
        if user["role"]=="sales" and body.owner_id not in (None,user["id"]):
            raise HTTPException(403,"Sales users cannot assign leads to other employees")
        stamp=utcnow()
        try:
            conn.execute(text("""INSERT INTO leads(id,lead_type,name,phone,email,institution,course_interest,city,district,state,source,status,owner_id,notes,created_at,updated_at,version)
                VALUES(:id,:typ,:name,:phone,:email,:institution,:course,:city,:district,:state,:source,:status,:owner,:notes,:c,:u,1)"""),
                {"id":lead_id,"typ":body.lead_type,"name":body.name,"phone":body.phone,"email":body.email,
                 "institution":body.institution,"course":body.course_interest,"city":body.city,"district":body.district,
                 "state":body.state,"source":body.source,"status":body.status,"owner":owner,"notes":body.notes,"c":stamp,"u":stamp})
        except IntegrityError: raise HTTPException(409,"Lead ID already exists")
        conn.execute(text("INSERT INTO audit_logs(actor_id,action,entity,entity_id,details,created_at) VALUES(:a,'api_create','lead',:id,'Lead created through central API',:t)"),
                     {"a":user["id"],"id":lead_id,"t":stamp})

        emit_sync_change(conn,user["id"],"lead",lead_id,"upsert",{"id":lead_id,"lead_type":body.lead_type,"name":body.name,
            "phone":body.phone,"email":body.email,"institution":body.institution,"course_interest":body.course_interest,
            "city":body.city,"district":body.district,"state":body.state,"source":body.source,"status":body.status,
            "owner_id":owner,"notes":body.notes,"version":1})
    return {"id":lead_id,"owner_id":owner,"version":1}

@app.patch("/v1/leads/{lead_id}")
def update_lead(lead_id:str,body:LeadPatch,user=Depends(current_user)):
    changes=body.model_dump(exclude={"expected_version"},exclude_unset=True)
    if not changes: raise HTTPException(400,"No fields supplied")
    with engine.begin() as conn:
        lead=conn.execute(text("SELECT * FROM leads WHERE id=:id"),{"id":lead_id}).mappings().first()
        if not lead: raise HTTPException(404,"Lead not found")
        if not can_view_lead(conn,user,lead): raise HTTPException(403,"You cannot access this lead")
        if "owner_id" in changes:
            if user["role"]=="sales": raise HTTPException(403,"Sales users cannot reassign leads")
            if changes["owner_id"] is not None and user["role"]=="admin":
                ok=conn.execute(text("SELECT 1 FROM users WHERE id=:id AND active=TRUE"),{"id":changes["owner_id"]}).first()
                if not ok: raise HTTPException(422,"Lead owner must be an active employee")
            if user["role"]=="manager" and changes["owner_id"] not in (None,user["id"]):
                ok=conn.execute(text("SELECT 1 FROM users WHERE id=:id AND manager_id=:mid AND active=TRUE"),
                                {"id":changes["owner_id"],"mid":user["id"]}).first()
                if not ok: raise HTTPException(403,"Manager can assign only to direct reports")
        sets=", ".join(f"{k}=:{k}" for k in changes)
        params=dict(changes); params.update({"id":lead_id,"version":body.expected_version,"updated":utcnow()})
        result=conn.execute(text(f"UPDATE leads SET {sets}, version=version+1, updated_at=:updated WHERE id=:id AND version=:version"),params)
        if result.rowcount==0: raise HTTPException(409,"Lead changed by another user; refresh before retrying")
        conn.execute(text("INSERT INTO audit_logs(actor_id,action,entity,entity_id,details,created_at) VALUES(:a,'api_update','lead',:id,:d,:t)"),
                     {"a":user["id"],"id":lead_id,"d":json.dumps(list(changes.keys())),"t":utcnow()})
        new_version=body.expected_version+1
        current=conn.execute(text("SELECT * FROM leads WHERE id=:id"),{"id":lead_id}).mappings().first()
        emit_sync_change(conn,user["id"],"lead",lead_id,"upsert",dict(current))
    return {"id":lead_id,"version":new_version,"updated":True}



# Core module read APIs. Results are scoped by employee ownership and manager hierarchy.
MODULE_TABLES = {
 "activities": ("activities","occurred_at"),
 "followups": ("followups","due_at"),
 "daily_reports": ("daily_reports","submitted_at"),
 "courses": ("courses","name"),
 "admissions": ("admissions","admission_date"),
 "payments": ("payments","payment_date"),
 "attendance": ("attendance","work_date"),
 "leave_requests": ("leave_requests","created_at"),
 "refund_requests": ("refund_requests","created_at"),
 "incentive_payouts": ("incentive_payouts","created_at"),
 "targets": ("targets","start_date"),
 "incentive_settings": ("incentive_settings","updated_at"),
}
@app.get("/v1/modules/{module}")
def list_module(module:str, limit:int=Query(100,ge=1,le=500), offset:int=Query(0,ge=0), user=Depends(current_user)):
    if module not in MODULE_TABLES: raise HTTPException(404,"Unknown module")
    table, order_col=MODULE_TABLES[module]
    with engine.begin() as conn:
        if module=="courses" or user["role"]=="admin":
            rows=conn.execute(text(f"SELECT * FROM {table} ORDER BY {order_col} DESC LIMIT :l OFFSET :o"),
                              {"l":limit,"o":offset}).mappings().all()
        elif module=="targets":
            if user["role"]=="manager":
                rows=conn.execute(text("""SELECT * FROM targets WHERE user_id=:uid OR user_id IS NULL
                    OR user_id IN (SELECT id FROM users WHERE manager_id=:uid)
                    ORDER BY start_date DESC LIMIT :l OFFSET :o"""),{"uid":user["id"],"l":limit,"o":offset}).mappings().all()
            else:
                rows=conn.execute(text("""SELECT * FROM targets WHERE user_id=:uid OR user_id IS NULL
                    ORDER BY start_date DESC LIMIT :l OFFSET :o"""),{"uid":user["id"],"l":limit,"o":offset}).mappings().all()
        elif module in ("daily_reports","attendance","leave_requests","incentive_payouts"):
            if user["role"]=="manager":
                rows=conn.execute(text(f"""SELECT * FROM {table} WHERE user_id=:uid
                    OR user_id IN (SELECT id FROM users WHERE manager_id=:uid)
                    ORDER BY {order_col} DESC LIMIT :l OFFSET :o"""),
                    {"uid":user["id"],"l":limit,"o":offset}).mappings().all()
            else:
                rows=conn.execute(text(f"SELECT * FROM {table} WHERE user_id=:uid ORDER BY {order_col} DESC LIMIT :l OFFSET :o"),
                                  {"uid":user["id"],"l":limit,"o":offset}).mappings().all()
        elif module=="activities":
            rows=conn.execute(text("""SELECT a.* FROM activities a JOIN leads l ON l.id=a.lead_id
                LEFT JOIN users u ON u.id=l.owner_id WHERE l.owner_id=:uid OR u.manager_id=:uid
                ORDER BY a.occurred_at DESC LIMIT :l OFFSET :o"""),{"uid":user["id"],"l":limit,"o":offset}).mappings().all()
        elif module=="followups":
            if user["role"]=="manager":
                rows=conn.execute(text("""SELECT f.* FROM followups f JOIN users u ON u.id=f.employee_id
                    WHERE f.employee_id=:uid OR u.manager_id=:uid
                    ORDER BY f.due_at DESC LIMIT :l OFFSET :o"""),{"uid":user["id"],"l":limit,"o":offset}).mappings().all()
            else:
                rows=conn.execute(text("""SELECT * FROM followups WHERE employee_id=:uid
                    ORDER BY due_at DESC LIMIT :l OFFSET :o"""),{"uid":user["id"],"l":limit,"o":offset}).mappings().all()
        elif module=="admissions":
            rows=conn.execute(text("""SELECT a.* FROM admissions a JOIN leads l ON l.id=a.lead_id
                LEFT JOIN users u ON u.id=l.owner_id WHERE l.owner_id=:uid OR u.manager_id=:uid
                ORDER BY a.admission_date DESC LIMIT :l OFFSET :o"""),{"uid":user["id"],"l":limit,"o":offset}).mappings().all()
        elif module=="payments":
            rows=conn.execute(text("""SELECT p.* FROM payments p JOIN admissions a ON a.id=p.admission_id
                JOIN leads l ON l.id=a.lead_id LEFT JOIN users u ON u.id=l.owner_id
                WHERE l.owner_id=:uid OR u.manager_id=:uid
                ORDER BY p.payment_date DESC LIMIT :l OFFSET :o"""),{"uid":user["id"],"l":limit,"o":offset}).mappings().all()
        elif module=="refund_requests":
            rows=conn.execute(text("""SELECT r.* FROM refund_requests r JOIN payments p ON p.id=r.payment_id
                JOIN admissions a ON a.id=p.admission_id JOIN leads l ON l.id=a.lead_id
                LEFT JOIN users u ON u.id=l.owner_id
                WHERE r.requested_by=:uid OR l.owner_id=:uid OR u.manager_id=:uid
                ORDER BY r.created_at DESC LIMIT :l OFFSET :o"""),
                {"uid":user["id"],"l":limit,"o":offset}).mappings().all()
        else:
            rows=[]
    return {"module":module,"items":[dict(r) for r in rows],"limit":limit,"offset":offset}

@app.get("/v1/dashboard/summary")
def dashboard_summary(user=Depends(current_user)):
    with engine.begin() as conn:
        if user["role"]=="admin":
            scope="TRUE"; params={}
        elif user["role"]=="manager":
            scope="(l.owner_id=:uid OR EXISTS (SELECT 1 FROM users su WHERE su.id=l.owner_id AND su.manager_id=:uid))"
            params={"uid":user["id"]}
        else:
            scope="l.owner_id=:uid"; params={"uid":user["id"]}
        leads=conn.execute(text(f"SELECT COUNT(*) FROM leads l WHERE {scope}"),params).scalar_one()
        admissions=conn.execute(text(f"SELECT COUNT(*) FROM admissions a JOIN leads l ON l.id=a.lead_id WHERE {scope}"),params).scalar_one()
        collections=conn.execute(text(f"""SELECT COALESCE(SUM(p.amount),0) FROM payments p
            JOIN admissions a ON a.id=p.admission_id JOIN leads l ON l.id=a.lead_id
            WHERE p.status='received' AND {scope}"""),params).scalar_one()
        pending=conn.execute(text(f"""SELECT COUNT(*) FROM followups f JOIN leads l ON l.id=f.lead_id
            WHERE f.status='pending' AND {scope}"""),params).scalar_one()
    return {"leads":leads,"admissions":admissions,"collections":float(collections),"pending_followups":pending}



# V12 write APIs: explicit allowlists prevent arbitrary SQL columns or table access.
WRITE_CONFIG = {
 "activities": {"table":"activities","id":"id","kind":"text","fields":{"lead_id","employee_id","activity_type","notes","outcome","occurred_at"},"required":{"lead_id","activity_type","occurred_at"}},
 "followups": {"table":"followups","id":"id","kind":"text","fields":{"lead_id","employee_id","due_at","status","notes","created_at"},"required":{"lead_id","due_at"}},
 "daily_reports": {"table":"daily_reports","id":"id","kind":"text","fields":{"user_id","report_date","calls","connected_calls","whatsapp_followups","new_leads","meetings","college_visits","admissions","remarks","submitted_at"},"required":{"report_date"}},
 "courses": {"table":"courses","id":"id","kind":"number","fields":{"name","fee","active"},"required":{"name","fee"},"admin":True},
 "admissions": {"table":"admissions","id":"id","kind":"text","fields":{"lead_id","course_id","admission_no","total_fee","status","admission_date","created_by","created_at"},"required":{"lead_id","admission_no","total_fee","admission_date"}},
 "payments": {"table":"payments","id":"id","kind":"text","fields":{"admission_id","amount","mode","reference","status","payment_date","created_by"},"required":{"admission_id","amount","payment_date"}},
 "targets": {"table":"targets","id":"id","kind":"number","fields":{"user_id","period","start_date","end_date","leads_target","admissions_target","created_by"},"required":{"period","start_date","end_date"},"admin":True},
 "attendance": {"table":"attendance","id":"id","kind":"number","fields":{"user_id","work_date","check_in","check_out","note"},"required":{"work_date","check_in"}},
 "leave_requests": {"table":"leave_requests","id":"id","kind":"number","fields":{"user_id","leave_type","start_date","end_date","reason","status","reviewed_by","reviewed_at","review_note","created_at"},"required":{"leave_type","start_date","end_date"}},
 "refund_requests": {"table":"refund_requests","id":"id","kind":"number","fields":{"payment_id","requested_amount","reason","status","requested_by","reviewed_by","reviewed_at","review_note","created_at"},"required":{"payment_id","requested_amount","reason"}},
 "incentive_payouts": {"table":"incentive_payouts","id":"id","kind":"number","fields":{"user_id","period_start","period_end","estimated_amount","approved_amount","status","approved_by","approved_at","note","created_at"},"required":{"user_id","period_start","period_end","estimated_amount"},"admin":True},
  "incentive_settings": {"table":"incentive_settings","id":"id","kind":"singleton","fields":{"collection_rate","admission_bonus","updated_at"},"required":{"collection_rate","admission_bonus"},"admin":True},
}
ADMIN_ONLY_PATCH = {"courses","targets","incentive_settings"}
MANAGER_ADMIN = {"leave_requests","refund_requests","incentive_payouts","targets"}

def _audit(conn, user, action, entity, entity_id, details=""):
    conn.execute(text("""INSERT INTO audit_logs(actor_id,action,entity,entity_id,details,created_at)
        VALUES(:a,:act,:e,:id,:d,:t)"""),
        {"a":user["id"],"act":action,"e":entity,"id":str(entity_id),"d":details,"t":utcnow()})

def _lead_access_for_id(conn, user, lead_id):
    lead=conn.execute(text("SELECT * FROM leads WHERE id=:id"),{"id":lead_id}).mappings().first()
    if not lead or not can_view_lead(conn,user,lead):
        raise HTTPException(403,"You cannot access the linked lead")
    return lead

def _record_access(conn, user, module, row):
    if user["role"]=="admin": return
    if module in ("activities","followups"):
        _lead_access_for_id(conn,user,row["lead_id"])
        if module=="followups" and row.get("employee_id") not in (None,user["id"]) and user["role"]=="sales":
            raise HTTPException(403,"You cannot access this follow-up")
    elif module in ("daily_reports","attendance","leave_requests","incentive_payouts"):
        target=row.get("user_id")
        if target != user["id"]:
            if user["role"]!="manager":
                raise HTTPException(403,"You cannot access this employee record")
            direct=conn.execute(text("SELECT 1 FROM users WHERE id=:id AND manager_id=:mid"),
                                {"id":target,"mid":user["id"]}).first()
            if not direct:
                raise HTTPException(403,"Managers can access only their direct reports")
    elif module=="admissions":
        _lead_access_for_id(conn,user,row["lead_id"])
    elif module=="payments":
        parent=conn.execute(text("""SELECT a.lead_id FROM admissions a WHERE a.id=:id"""),
                            {"id":row["admission_id"]}).mappings().first()
        if not parent: raise HTTPException(404,"Admission not found")
        _lead_access_for_id(conn,user,parent["lead_id"])
    elif module=="refund_requests":
        if user["role"]=="admin":
            return
        if user["role"]=="manager":
            parent=conn.execute(text("""SELECT l.owner_id FROM refund_requests r
                JOIN payments p ON p.id=r.payment_id JOIN admissions a ON a.id=p.admission_id
                JOIN leads l ON l.id=a.lead_id WHERE r.id=:id"""),{"id":row["id"]}).mappings().first()
            if not parent or (parent["owner_id"]!=user["id"] and not conn.execute(
                text("SELECT 1 FROM users WHERE id=:id AND manager_id=:mid"),
                {"id":parent["owner_id"],"mid":user["id"]}).first()):
                raise HTTPException(403,"You cannot access this team's refund request")
        elif row.get("requested_by")!=user["id"]:
            raise HTTPException(403,"You cannot access this refund request")
    elif module=="targets":
        if user["role"]!="manager" or row.get("user_id") not in (None,user["id"]):
            raise HTTPException(403,"Only admins or managers can access this target")
    elif module=="courses":
        return

def _prepare_module_payload(conn, user, module, data, creating):
    cfg=WRITE_CONFIG[module]
    unknown=set(data)-cfg["fields"]
    if unknown: raise HTTPException(422, f"Unsupported fields: {', '.join(sorted(unknown))}")
    missing=cfg["required"]-set(data)
    if creating and missing: raise HTTPException(422,f"Missing required fields: {', '.join(sorted(missing))}")
    result=dict(data)
    if cfg.get("admin") and user["role"]!="admin":
        raise HTTPException(403,"Only admin can modify this module")
    if module in ("activities","followups","admissions"):
        if "lead_id" in result or creating:
            _lead_access_for_id(conn,user,result.get("lead_id"))
    if module in ("activities","followups"):
        # Default records to the signed-in employee; managers/admins may explicitly
        # assign only within their permitted scope.
        if "employee_id" not in result or user["role"]=="sales":
            result["employee_id"]=user["id"]
        else:
            emp=conn.execute(text("SELECT id,manager_id FROM users WHERE id=:id AND active=TRUE"),{"id":result["employee_id"]}).mappings().first()
            if not emp or (user["role"]=="manager" and emp["manager_id"]!=user["id"] and emp["id"]!=user["id"]):
                raise HTTPException(403,"Invalid employee assignment")
    if module in ("daily_reports","attendance","leave_requests"):
        result["user_id"]=user["id"] if user["role"]!="admin" else result.get("user_id",user["id"])
    if module=="admissions":
        result["created_by"]=user["id"]
    if module=="payments":
        parent=conn.execute(text("SELECT lead_id FROM admissions WHERE id=:id"),{"id":result.get("admission_id")}).mappings().first()
        if not parent: raise HTTPException(404,"Admission not found")
        _lead_access_for_id(conn,user,parent["lead_id"])
        result["created_by"]=user["id"]
    if module=="refund_requests":
        parent=conn.execute(text("""SELECT a.lead_id,p.amount,p.status FROM payments p
            JOIN admissions a ON a.id=p.admission_id WHERE p.id=:id"""),
                            {"id":result.get("payment_id")}).mappings().first()
        if not parent: raise HTTPException(404,"Payment not found")
        _lead_access_for_id(conn,user,parent["lead_id"])
        if float(result.get("requested_amount",0))>float(parent["amount"]):
            raise HTTPException(422,"Requested refund cannot exceed the payment amount")
        result["requested_by"]=user["id"]
        result["status"]="pending"; result["reviewed_by"]=None; result["reviewed_at"]=None; result["review_note"]=None
    if module=="leave_requests":
        result["status"]="pending"; result["reviewed_by"]=None; result["reviewed_at"]=None; result["review_note"]=None
    if module=="incentive_payouts":
        result["status"]="pending"; result["approved_amount"]=None; result["approved_by"]=None; result["approved_at"]=None
    if module=="targets":
        if user["role"]=="manager" and result.get("user_id") not in (None,user["id"]):
            emp=conn.execute(text("SELECT 1 FROM users WHERE id=:id AND manager_id=:mid"),{"id":result["user_id"],"mid":user["id"]}).first()
            if not emp: raise HTTPException(403,"Managers can target only their direct reports")
        result["created_by"]=user["id"]
    if module=="incentive_payouts":
        result["created_at"]=result.get("created_at") or utcnow()
    if module=="incentive_settings":
        result["updated_at"]=utcnow()
    return result

@app.post("/v1/modules/{module}",status_code=201)
def create_module_record(module:str, payload:dict[str,Any], user=Depends(current_user)):
    if module not in WRITE_CONFIG: raise HTTPException(404,"Unknown or read-only module")
    cfg=WRITE_CONFIG[module]
    with engine.begin() as conn:
        data=_prepare_module_payload(conn,user,module,payload,True)
        if module=="daily_reports": data["submitted_at"]=data.get("submitted_at") or utcnow()
        if module in ("activities","followups") and module=="activities":
            data["occurred_at"]=data.get("occurred_at") or utcnow()
        if module in ("followups","leave_requests","refund_requests","admissions") and "created_at" in cfg["fields"]:
            data["created_at"]=data.get("created_at") or utcnow()
        if cfg["kind"]=="text":
            rid=str(uuid.uuid4())
        elif cfg["kind"]=="singleton":
            rid=1
        else:
            rid=None
        cols=list(data)
        if cols:
            names=",".join(cols); vals=",".join(":"+c for c in cols)
            if rid is not None:
                names=cfg["id"]+","+names; vals=":rid,"+vals
            stmt=f"INSERT INTO {cfg['table']} ({names}) VALUES ({vals}) RETURNING {cfg['id']}"
            params=dict(data)
            if rid is not None: params["rid"]=rid
        else:
            stmt=f"INSERT INTO {cfg['table']} DEFAULT VALUES RETURNING {cfg['id']}"; params={}
        try:
            record_id=conn.execute(text(stmt),params).scalar_one()
        except IntegrityError as e:
            raise HTTPException(409,"Duplicate record or invalid related record") from e
        _audit(conn,user,"api_create",module,record_id)
        emit_sync_change(conn,user["id"],module,record_id,"upsert",{**data,"id":record_id})
    return {"module":module,"id":record_id,"created":True}

@app.patch("/v1/modules/{module}/{record_id}")
def update_module_record(module:str,record_id:str,payload:dict[str,Any],user=Depends(current_user)):
    if module not in WRITE_CONFIG: raise HTTPException(404,"Unknown or read-only module")
    cfg=WRITE_CONFIG[module]
    if module in ADMIN_ONLY_PATCH and user["role"]!="admin":
        raise HTTPException(403,"Only admin can update this module")
    if cfg["kind"] in ("number","singleton"):
        try: record_id=int(record_id)
        except (TypeError,ValueError): raise HTTPException(422,"Record ID must be numeric")
    data=dict(payload)
    if not data: raise HTTPException(400,"No update fields supplied")
    if set(data)-cfg["fields"]: raise HTTPException(422,"Unsupported update fields")
    # Reviewer identities/timestamps are server-controlled, never client supplied.
    if module in ("leave_requests","refund_requests"):
        data.pop("reviewed_by",None); data.pop("reviewed_at",None)
    if module=="incentive_payouts":
        data.pop("approved_by",None); data.pop("approved_at",None)
    if module in ("daily_reports","attendance","leave_requests") and user["role"]!="admin":
        data.pop("user_id",None)
    if module in ("activities","followups") and user["role"]=="sales":
        data.pop("employee_id",None)
    with engine.begin() as conn:
        row=conn.execute(text(f"SELECT * FROM {cfg['table']} WHERE {cfg['id']}=:id"),{"id":record_id}).mappings().first()
        if not row: raise HTTPException(404,"Record not found")
        _record_access(conn,user,module,dict(row))
        merged=dict(row); merged.update(data)
        # Stamp approval metadata server-side; never trust a browser-supplied reviewer identity.
        if module in ("leave_requests","refund_requests") and "status" in data:
            if data["status"] in ("approved","rejected"):
                data["reviewed_by"]=user["id"]; data["reviewed_at"]=utcnow()
            else:
                data["reviewed_by"]=None; data["reviewed_at"]=None
        if module=="incentive_payouts" and "status" in data:
            if data["status"] in ("approved","rejected","paid"):
                data["approved_by"]=user["id"]; data["approved_at"]=utcnow()
            else:
                data["approved_by"]=None; data["approved_at"]=None
        if module in ("activities","followups","admissions") and "lead_id" in data:
            _lead_access_for_id(conn,user,data["lead_id"])
        if module=="payments" and "admission_id" in data:
            parent=conn.execute(text("SELECT lead_id FROM admissions WHERE id=:id"),{"id":data["admission_id"]}).mappings().first()
            if not parent: raise HTTPException(404,"Admission not found")
            _lead_access_for_id(conn,user,parent["lead_id"])
        if module=="refund_requests" and user["role"] not in ("admin","manager"):
            raise HTTPException(403,"Only managers/admins can review refund requests")
        if module in ("leave_requests","incentive_payouts") and user["role"]=="sales":
            raise HTTPException(403,"Only managers/admins can update approvals")
        if module=="targets" and user["role"]=="manager":
            if merged.get("user_id") not in (None,user["id"]):
                emp=conn.execute(text("SELECT 1 FROM users WHERE id=:id AND manager_id=:mid"),{"id":merged["user_id"],"mid":user["id"]}).first()
                if not emp: raise HTTPException(403,"Cannot change target outside your team")
        sets=",".join(f"{k}=:{k}" for k in data)
        if not sets: raise HTTPException(400,"No permitted fields to update")
        params=dict(data); params["id"]=record_id
        try:
            conn.execute(text(f"UPDATE {cfg['table']} SET {sets} WHERE {cfg['id']}=:id"),params)
        except IntegrityError as e:
            raise HTTPException(409,"Update conflicts with a database constraint") from e
        _audit(conn,user,"api_update",module,record_id,",".join(data))
        emit_sync_change(conn,user["id"],module,record_id,"upsert",{**dict(merged),**data,"id":record_id})
    return {"module":module,"id":record_id,"updated":True}

@app.get("/v1/meta/modules")
def module_metadata(user=Depends(current_user)):
    return {"modules":sorted(WRITE_CONFIG.keys()),"read_only":["sync_events","audit_logs"],
            "version":"1.3.0","note":"Role access checks apply; validate in staging before production."}

@app.post("/v1/lead-hunter/search")
def lead_hunter_search(body:LeadHunterRequest,user=Depends(current_user)):
    if user["role"] not in ("admin","manager"):
        raise HTTPException(403,"Only admin/manager can run lead discovery")
    api_key=os.getenv("EXA_API_KEY","")
    if not api_key: raise HTTPException(503,"Set EXA_API_KEY in the server environment to enable public-web discovery")
    payload={"query":body.query,"type":"auto","numResults":body.num_results,
             "contents":{"text":{"maxCharacters":1800}}}
    req=urllib.request.Request("https://api.exa.ai/search",data=json.dumps(payload).encode(),
        headers={"x-api-key":api_key,"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=25) as response:
            result=json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail=exc.read().decode(errors="replace")[:600]
        raise HTTPException(502,f"Exa search failed: {detail}")
    except Exception as exc:
        raise HTTPException(502,f"Public-web search unavailable: {type(exc).__name__}")
    candidates=[]
    for item in result.get("results",[]):
        url=item.get("url")
        if not isinstance(url,str) or not url.startswith(("https://","http://")): continue
        description=item.get("text") or ""
        if not description and isinstance(item.get("highlights"),list):
            description=" ".join(str(x) for x in item["highlights"])
        candidates.append({"title":item.get("title") or "Untitled public result",
            "url":url,"published_date":item.get("publishedDate"),"description":description[:1800]})
    imported_count=0
    with engine.begin() as conn:
        run_id=conn.execute(text("""INSERT INTO lead_hunter_runs(requested_by,query,provider,results_count,imported_count,status,details,created_at)
            VALUES(:uid,:q,'exa',:n,0,'review_required',CAST(:d AS JSONB),:t) RETURNING id"""),
            {"uid":user["id"],"q":body.query,"n":len(candidates),"d":json.dumps({"target_type":body.target_type,"auto_import":body.auto_import,"candidate_urls":[c["url"] for c in candidates]}),"t":utcnow()}).scalar_one()
        for candidate in candidates:
            cid=conn.execute(text("""INSERT INTO lead_hunter_candidates(run_id,source_url,title,description,status,created_at)
                VALUES(:run,:url,:title,:description,'new',:t)
                ON CONFLICT(source_url) DO NOTHING RETURNING id"""),
                {"run":run_id,"url":candidate["url"],"title":candidate["title"],"description":candidate["description"],"t":utcnow()}).scalar()
            candidate["candidate_id"]=cid
            candidate["duplicate"]=cid is None
            if body.auto_import and cid is not None:
                lead_id=str(uuid.uuid4()); stamp=utcnow()
                conn.execute(text("""INSERT INTO leads(id,lead_type,name,institution,source,status,owner_id,notes,created_at,updated_at,version)
                    VALUES(:id,:typ,:name,:inst,'AI Lead Hunter','review_required',:owner,:notes,:t,:t,1)"""),
                    {"id":lead_id,"typ":body.target_type,"name":candidate["title"],
                     "inst":candidate["title"] if body.target_type=="college" else None,
                     "owner":user["id"],"notes":"Public source: "+candidate["url"]+"\n"+candidate["description"],"t":stamp})
                conn.execute(text("UPDATE lead_hunter_candidates SET status='imported',lead_id=:lead WHERE id=:id"),
                    {"lead":lead_id,"id":cid})
                emit_sync_change(conn,user["id"],"lead",lead_id,"upsert",{"id":lead_id,"lead_type":body.target_type,
                    "name":candidate["title"],"institution":candidate["title"] if body.target_type=="college" else None,
                    "source":"AI Lead Hunter","status":"review_required","owner_id":user["id"],
                    "notes":"Public source: "+candidate["url"]})
                _audit(conn,user,"lead_hunter_auto_import","lead",lead_id,candidate["url"])
                candidate["lead_id"]=lead_id; candidate["imported"]=True; imported_count+=1
        conn.execute(text("UPDATE lead_hunter_runs SET imported_count=:n WHERE id=:id"),{"n":imported_count,"id":run_id})
        _audit(conn,user,"lead_hunter_search","lead_hunter_run",run_id,body.query)
    return {"run_id":run_id,"target_type":body.target_type,"results":candidates,"imported_count":imported_count,
            "notice":"Public-source candidates only. Imported records remain review_required; verify source and contact permissions before outreach."}

@app.post("/v1/lead-hunter/import",status_code=201)
def lead_hunter_import(body:LeadHunterImport,user=Depends(current_user)):
    if user["role"] not in ("admin","manager"):
        raise HTTPException(403,"Only admin/manager can import discovered leads")
    if not body.source_url.startswith(("https://","http://")):
        raise HTTPException(422,"A valid public source URL is required")
    lead_id=str(uuid.uuid4()); stamp=utcnow()
    with engine.begin() as conn:
        existing=conn.execute(text("SELECT lead_id FROM lead_hunter_candidates WHERE source_url=:url"),{"url":body.source_url}).mappings().first()
        if existing and existing["lead_id"]:
            raise HTTPException(409,"This public source has already been imported")
        conn.execute(text("""INSERT INTO leads(id,lead_type,name,institution,city,state,source,status,owner_id,notes,created_at,updated_at,version)
            VALUES(:id,:typ,:name,:inst,:city,:state,'AI Lead Hunter','review_required',:owner,:notes,:t,:t,1)"""),
            {"id":lead_id,"typ":body.lead_type,"name":body.name,"inst":body.institution,"city":body.city,
             "state":body.state,"owner":user["id"],"notes":(body.notes or "")+"\nPublic source: "+body.source_url,"t":stamp})
        emit_sync_change(conn,user["id"],"lead",lead_id,"upsert",{"id":lead_id,"lead_type":body.lead_type,"name":body.name,
            "institution":body.institution,"city":body.city,"state":body.state,"source":"AI Lead Hunter",
            "status":"review_required","owner_id":user["id"],"notes":body.notes})
        _audit(conn,user,"lead_hunter_import","lead",lead_id,body.source_url)
    return {"id":lead_id,"status":"review_required"}

@app.post("/v1/devices/register")
def register_device(body:DeviceRegistration,user=Depends(current_user)):
    did=str(uuid.uuid4()); token=secrets.token_urlsafe(40)
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO devices(id,user_id,device_name,platform,token_hash,created_at)
            VALUES(:id,:uid,:n,:p,:h,:t)"""),
            {"id":did,"uid":user["id"],"n":body.device_name,"p":body.platform,"h":token_hash(token),"t":utcnow()})
        _audit(conn,user,"register_device","device",did,body.platform)
    return {"device_id":did,"device_token":token,"warning":"Store securely; shown only once."}

@app.get("/v1/devices")
def list_devices(user=Depends(current_user)):
    if user["role"]!="admin": raise HTTPException(403,"Only admin can view registered devices")
    with engine.begin() as conn:
        rows=conn.execute(text("""SELECT d.id,d.user_id,u.username,u.full_name,d.device_name,d.platform,
            d.active,d.created_at FROM devices d JOIN users u ON u.id=d.user_id ORDER BY d.created_at DESC""")).mappings().all()
    return {"items":[dict(r) for r in rows]}

@app.post("/v1/devices/{device_id}/revoke")
def revoke_device(device_id:str,user=Depends(current_user)):
    if user["role"]!="admin": raise HTTPException(403,"Only admin can revoke devices")
    with engine.begin() as conn:
        result=conn.execute(text("UPDATE devices SET active=FALSE WHERE id=:id"),{"id":device_id})
        if not result.rowcount: raise HTTPException(404,"Device not found")
        _audit(conn,user,"revoke_device","device",device_id,"Device token revoked")
    return {"id":device_id,"revoked":True}

@app.get("/v1/sync/bootstrap")
def sync_bootstrap(after_id:str|None=None,limit:int=Query(500,ge=1,le=500),authorization:str|None=Header(default=None)):
    device=require_device(authorization)
    with engine.begin() as conn:
        if device["role"]=="admin":
            where="TRUE"; params={"lim":limit,"after_id":after_id}
        elif device["role"]=="manager":
            where="(owner_id=:uid OR owner_id IN (SELECT id FROM users WHERE manager_id=:uid))"
            params={"uid":device["user_id"],"lim":limit,"after_id":after_id}
        else:
            where="owner_id=:uid"; params={"uid":device["user_id"],"lim":limit,"after_id":after_id}
        max_seq=conn.execute(text("SELECT COALESCE(MAX(seq),0) FROM sync_changes")).scalar_one()
        rows=conn.execute(text(f"SELECT * FROM leads WHERE {where} AND (:after_id IS NULL OR id>:after_id) ORDER BY id LIMIT :lim"),params).mappings().all()
    return {"items":[dict(r) for r in rows],"limit":limit,
            "next_after_id":rows[-1]["id"] if len(rows)==limit else None,"max_seq":max_seq}

@app.get("/v1/sync/snapshot/{module}")
def sync_module_snapshot(module:str, offset:int=Query(0,ge=0), limit:int=Query(1,le=500), authorization:str|None=Header(default=None)):
    device=require_device(authorization)
    sync_user={"id":device["user_id"],"role":device["role"]}
    if module=="users":
        with engine.begin() as conn:
            if device["role"]=="admin": rows=conn.execute(text("SELECT id,username,full_name,role,active,manager_id,created_at FROM users ORDER BY id LIMIT :l OFFSET :o"),{"l":limit,"o":offset}).mappings().all()
            elif device["role"]=="manager": rows=conn.execute(text("SELECT id,username,full_name,role,active,manager_id,created_at FROM users WHERE id=:uid OR manager_id=:uid ORDER BY id LIMIT :l OFFSET :o"),{"uid":device["user_id"],"l":limit,"o":offset}).mappings().all()
            else: rows=conn.execute(text("SELECT id,username,full_name,role,active,manager_id,created_at FROM users WHERE id=:uid ORDER BY id LIMIT :l OFFSET :o"),{"uid":device["user_id"],"l":limit,"o":offset}).mappings().all()
        return {"module":module,"items":[dict(r) for r in rows],"next_offset":offset+len(rows) if len(rows)==limit else None}
    if module=="leads":
        with engine.begin() as conn:
            if device["role"]=="admin": where="TRUE"; params={"l":limit,"o":offset}
            elif device["role"]=="manager": where="(owner_id=:uid OR owner_id IN (SELECT id FROM users WHERE manager_id=:uid))"; params={"uid":device["user_id"],"l":limit,"o":offset}
            else: where="owner_id=:uid"; params={"uid":device["user_id"],"l":limit,"o":offset}
            rows=conn.execute(text(f"SELECT * FROM leads WHERE {where} ORDER BY id LIMIT :l OFFSET :o"),params).mappings().all()
        return {"module":module,"items":[dict(r) for r in rows],"next_offset":offset+len(rows) if len(rows)==limit else None}
    if module not in MODULE_TABLES: raise HTTPException(404,"Unknown module")
    result=list_module(module,limit=limit,offset=offset,user=sync_user)
    items=result["items"]
    return {"module":module,"items":items,"next_offset":offset+len(items) if len(items)==limit else None}

@app.post("/v1/sync/push")
def sync_push(body:SyncPush,authorization:str|None=Header(default=None)):
    device=require_device(authorization); did=str(device["id"])
    actor={"id":device["user_id"],"role":device["role"],"manager_id":device.get("manager_id")}
    if body.device_id!=did: raise HTTPException(403,"device_id does not match authenticated device")
    accepted=[]; duplicates=[]; duplicate_records=[]; rejected=[]; server_id_map={}
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(73201401)"))
        for ch in body.changes:
            savepoint=conn.begin_nested()
            inserted=conn.execute(text("""INSERT INTO sync_changes(change_id,device_id,entity,record_id,operation,payload,client_updated_at,received_at)
                VALUES(:cid,:did,:entity,:rid,:op,CAST(:payload AS JSONB),:cat,:received)
                ON CONFLICT (change_id) DO NOTHING RETURNING change_id"""),
                {"cid":ch.change_id,"did":did,"entity":ch.entity,"rid":ch.record_id,"op":ch.operation,
                 "payload":json.dumps(ch.payload,default=str),"cat":ch.client_updated_at,"received":utcnow()}).first()
            if not inserted:
                prior=conn.execute(text("SELECT record_id,payload FROM sync_changes WHERE change_id=:cid"),{"cid":ch.change_id}).mappings().first()
                if prior and isinstance(prior["payload"],dict) and (prior["payload"].get("server_id") or prior["payload"].get("server_version")):
                    duplicate_records.append({"change_id":ch.change_id,"record_id":str(prior["record_id"]),"local_record_id":ch.record_id,"server_record":dict(prior["payload"])})
                savepoint.commit(); duplicates.append(ch.change_id); continue
            try:
                if ch.operation!="upsert": raise HTTPException(422,"Delete sync is disabled; use archive/status fields")
                if ch.entity=="lead":
                    data=ch.payload
                    if not {"name","lead_type"}.issubset(data) or data.get("lead_type") not in ("student","college"):
                        raise HTTPException(422,"Invalid lead payload")
                    lead_id=str(ch.record_id); existing=conn.execute(text("SELECT * FROM leads WHERE id=:id"),{"id":lead_id}).mappings().first(); stamp=utcnow()
                    if existing:
                        if not can_view_lead(conn,actor,existing): raise HTTPException(403,"Lead outside user's scope")
                        if int(data.get("base_version",existing["version"]))!=existing["version"]: raise HTTPException(409,"version_conflict")
                        allowed=["name","lead_type","phone","email","institution","course_interest","city","district","state","source","status","notes"]
                        vals={k:data[k] for k in allowed if k in data}; vals.update({"id":lead_id,"stamp":stamp})
                        sets=",".join(f"{k}=:{k}" for k in vals if k not in ("id","stamp"))
                        conn.execute(text(f"UPDATE leads SET {sets},version=version+1,updated_at=:stamp WHERE id=:id"),vals); version=existing["version"]+1
                    else:
                        vals={k:data.get(k) for k in ["name","lead_type","phone","email","institution","course_interest","city","district","state","source","status","notes"]}
                        vals.update({"id":lead_id,"owner":device["user_id"],"stamp":stamp})
                        conn.execute(text("""INSERT INTO leads(id,lead_type,name,phone,email,institution,course_interest,city,district,state,source,status,owner_id,notes,created_at,updated_at,version)
                            VALUES(:id,:lead_type,:name,:phone,:email,:institution,:course_interest,:city,:district,:state,:source,:status,:owner,:notes,:stamp,:stamp,1)"""),vals); version=1
                    current_lead=conn.execute(text("SELECT * FROM leads WHERE id=:id"),{"id":lead_id}).mappings().first()
                    final_payload={**dict(current_lead or {}),"id":lead_id,"server_version":version,"owner_id":device["user_id"]}
                    _audit(conn,actor,"device_sync_upsert","lead",lead_id,"offline client sync")
                    server_id=lead_id
                else:
                    module=ch.entity
                    if module not in WRITE_CONFIG: raise HTTPException(422,"Module is not writable")
                    cfg=WRITE_CONFIG[module]; data={k:v for k,v in ch.payload.items() if not k.startswith("_") and k not in ("base_version","id","server_id","actor_id")}
                    for field,value in list(data.items()):
                        if field.endswith("_id") and isinstance(value,str) and value in server_id_map: data[field]=server_id_map[value]
                    if ch.record_id.startswith("local:"):
                        data=_prepare_module_payload(conn,actor,module,data,True)
                        if module=="daily_reports": data["submitted_at"]=data.get("submitted_at") or utcnow()
                        if module=="activities": data["occurred_at"]=data.get("occurred_at") or utcnow()
                        if module in ("followups","leave_requests","refund_requests","admissions") and "created_at" in cfg["fields"]: data["created_at"]=data.get("created_at") or utcnow()
                        if module=="incentive_payouts": data["created_at"]=data.get("created_at") or utcnow()
                        if module=="incentive_settings": data["updated_at"]=utcnow()
                        cols=list(data); names=",".join(cols); binds=",".join(":"+c for c in cols)
                        if cfg["kind"]=="text":
                            server_id=str(uuid.uuid4()); names=cfg["id"]+","+names; binds=":rid,"+binds; data["rid"]=server_id
                        elif cfg["kind"]=="singleton":
                            server_id="1"; names=cfg["id"]+","+names; binds=":rid,"+binds; data["rid"]=1
                        else: server_id=None
                        stmt=f"INSERT INTO {cfg['table']} ({names}) VALUES ({binds}) RETURNING {cfg['id']}" if cols else f"INSERT INTO {cfg['table']} DEFAULT VALUES RETURNING {cfg['id']}"
                        server_id=str(conn.execute(text(stmt),data).scalar_one())
                    else:
                        rid=int(ch.record_id) if cfg["kind"] in ("number","singleton") else ch.record_id
                        row=conn.execute(text(f"SELECT * FROM {cfg['table']} WHERE {cfg['id']}=:id"),{"id":rid}).mappings().first()
                        if not row: raise HTTPException(404,"Offline update target no longer exists")
                        _record_access(conn,actor,module,dict(row))
                        allowed=set(cfg["fields"])
                        if set(data)-allowed: raise HTTPException(422,"Unsupported offline fields")
                        base=ch.payload.get("_base_snapshot")
                        if isinstance(base,dict):
                            def _norm_sync_value(value):
                                if isinstance(value,datetime):
                                    return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.replace(tzinfo=timezone.utc).isoformat()
                                if isinstance(value,date): return value.isoformat()
                                if isinstance(value,str):
                                    try:
                                        if "T" in value or (" " in value and len(value)>10):
                                            parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
                                            return parsed.astimezone(timezone.utc).isoformat() if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc).isoformat()
                                        if len(value)==10: return date.fromisoformat(value).isoformat()
                                    except ValueError: pass
                                return value
                            for field in list(data):
                                if field not in base: continue
                                if _norm_sync_value(data[field])==_norm_sync_value(base[field]):
                                    data.pop(field)
                                elif _norm_sync_value(row.get(field))!=_norm_sync_value(base[field]) and _norm_sync_value(row.get(field))!=_norm_sync_value(data[field]):
                                    raise HTTPException(409,f"version_conflict:{field}")
                        if cfg.get("admin") and actor["role"]!="admin": raise HTTPException(403,"Admin role required")
                        if module in ADMIN_ONLY_PATCH and actor["role"]!="admin": raise HTTPException(403,"Admin role required")
                        # Protect approval and ownership fields from offline clients.
                        if module in ("leave_requests","refund_requests"): data.pop("reviewed_by",None); data.pop("reviewed_at",None)
                        if module=="incentive_payouts": data.pop("approved_by",None); data.pop("approved_at",None)
                        if module in ("admissions","payments","targets"): data.pop("created_by",None)
                        if module=="refund_requests": data.pop("requested_by",None)
                        if module in ("daily_reports","attendance","leave_requests") and actor["role"]!="admin": data.pop("user_id",None)
                        if module=="daily_reports": data.pop("submitted_at",None)
                        if module in ("activities","followups") and actor["role"]=="sales": data.pop("employee_id",None)
                        elif module in ("activities","followups") and actor["role"]=="manager" and "employee_id" in data:
                            target=data["employee_id"]
                            allowed_target=target==actor["id"] or conn.execute(text("SELECT 1 FROM users WHERE id=:id AND manager_id=:mid AND active=TRUE"),{"id":target,"mid":actor["id"]}).first()
                            if not allowed_target: raise HTTPException(403,"Invalid employee assignment")
                        if module in ("activities","followups","admissions") and "lead_id" in data: _lead_access_for_id(conn,actor,data["lead_id"])
                        if module=="payments" and "admission_id" in data:
                            parent=conn.execute(text("SELECT lead_id FROM admissions WHERE id=:id"),{"id":data["admission_id"]}).mappings().first()
                            if not parent: raise HTTPException(404,"Admission not found")
                            _lead_access_for_id(conn,actor,parent["lead_id"])
                        if module in ("leave_requests","refund_requests") and "status" in data:
                            if actor["role"] not in ("admin","manager"): raise HTTPException(403,"Approval permission required")
                            data["reviewed_by"]=actor["id"]; data["reviewed_at"]=utcnow()
                        if module=="incentive_payouts" and "status" in data:
                            if actor["role"]!="admin": raise HTTPException(403,"Admin approval required")
                            data["approved_by"]=actor["id"]; data["approved_at"]=utcnow()
                        if data:
                            sets=",".join(f"{k}=:{k}" for k in data); params=dict(data); params["id"]=rid
                            conn.execute(text(f"UPDATE {cfg['table']} SET {sets} WHERE {cfg['id']}=:id"),params)
                        server_id=str(rid)
                    if cfg["kind"] in ("number","singleton"): final_id=int(server_id)
                    else: final_id=server_id
                    current=conn.execute(text(f"SELECT * FROM {cfg['table']} WHERE {cfg['id']}=:id"),{"id":final_id}).mappings().first()
                    final_payload={**dict(current or {}),"id":server_id,"server_id":server_id,"actor_id":device["user_id"]}
                    server_id_map[ch.record_id]=server_id
                    _audit(conn,actor,"device_sync_upsert",module,server_id,"offline client sync")
                conn.execute(text("UPDATE sync_changes SET payload=CAST(:p AS JSONB),record_id=:rid WHERE change_id=:cid"),
                    {"p":json.dumps(final_payload,default=str),"rid":server_id,"cid":ch.change_id})
                accepted.append({"change_id":ch.change_id,"record_id":server_id,"local_record_id":ch.record_id,"server_record":final_payload})
                savepoint.commit()
            except HTTPException as exc:
                savepoint.rollback()
                rejected.append({"change_id":ch.change_id,"reason":str(exc.detail),"status":exc.status_code})
            except IntegrityError:
                savepoint.rollback()
                rejected.append({"change_id":ch.change_id,"reason":"Related record missing or duplicate constraint","status":409})
    return {"accepted":accepted,"duplicates":duplicates,"duplicate_records":duplicate_records,"rejected":rejected}

@app.get("/v1/sync/pull")
def sync_pull(since_seq:int=Query(0,ge=0),limit:int=Query(200,ge=1,le=500),authorization:str|None=Header(default=None)):
    device=require_device(authorization)
    device_id=str(device["id"])
    with engine.begin() as conn:
        if device["role"]=="admin":
            scope="TRUE"; params={"did":device_id,"since_seq":since_seq,"lim":limit}
        elif device["role"]=="manager":
            scope="(c.entity IN ('courses','incentive_settings') OR u.id=:uid OR u.manager_id=:uid OR l.owner_id=:uid OR l.owner_id IN (SELECT id FROM users WHERE manager_id=:uid) OR (c.entity IN ('activities','followups') AND ((c.payload->>'employee_id')::bigint=:uid OR (c.payload->>'employee_id')::bigint IN (SELECT id FROM users WHERE manager_id=:uid))) OR (c.entity IN ('daily_reports','attendance','leave_requests','incentive_payouts') AND ((c.payload->>'user_id')::bigint=:uid OR (c.payload->>'user_id')::bigint IN (SELECT id FROM users WHERE manager_id=:uid))) OR (c.entity='targets' AND ((c.payload->>'user_id') IS NULL OR (c.payload->>'user_id')::bigint=:uid OR (c.payload->>'user_id')::bigint IN (SELECT id FROM users WHERE manager_id=:uid))))"
            params={"did":device_id,"uid":device["user_id"],"since_seq":since_seq,"lim":limit}
        else:
            scope="(c.entity IN ('courses','incentive_settings') OR u.id=:uid OR l.owner_id=:uid OR (c.entity IN ('activities','followups') AND (c.payload->>'employee_id')::bigint=:uid) OR (c.entity IN ('daily_reports','attendance','leave_requests','incentive_payouts') AND (c.payload->>'user_id')::bigint=:uid) OR (c.entity='targets' AND ((c.payload->>'user_id') IS NULL OR (c.payload->>'user_id')::bigint=:uid)))"
            params={"did":device_id,"uid":device["user_id"],"since_seq":since_seq,"lim":limit}
        rows=conn.execute(text(f"""SELECT c.seq,c.change_id,c.entity,c.record_id,c.operation,c.payload,c.received_at
            FROM sync_changes c LEFT JOIN devices d ON d.id=c.device_id
            LEFT JOIN users u ON u.id=COALESCE(d.user_id,(c.payload->>'actor_id')::bigint)
            LEFT JOIN leads l ON c.entity='lead' AND l.id=c.record_id
            WHERE (c.device_id IS NULL OR c.device_id<>:did) AND {scope}
              AND c.seq>:since_seq
            ORDER BY c.seq ASC LIMIT :lim"""),params).mappings().all()
    return {"changes":[dict(r) for r in rows],"next_since_seq":rows[-1]["seq"] if rows else since_seq}
