import os, sqlite3, secrets, hashlib, hmac, csv, io, json
from datetime import datetime, date, timezone, timedelta
from functools import wraps
from flask import Flask, request, redirect, url_for, session, render_template, flash, Response, g, jsonify

ROOT=os.path.dirname(os.path.abspath(__file__))
DATA=os.path.join(ROOT,"data"); os.makedirs(DATA,exist_ok=True)
DB=os.environ.get("CRM_DB_PATH",os.path.join(DATA,"qubinaire_crm.db"))
app=Flask(__name__)
app.secret_key=os.environ.get("CRM_SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def conn():
    if "db" not in g:
        g.db=sqlite3.connect(DB, timeout=20)
        g.db.row_factory=sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db
@app.teardown_appcontext
def close_db(e=None):
    c=g.pop("db",None)
    if c: c.close()

def pw_hash(pw, salt=None):
    salt=salt or secrets.token_bytes(16)
    return salt.hex()+"$"+hashlib.pbkdf2_hmac("sha256",pw.encode(),salt,310000).hex()
def pw_ok(pw, stored):
    try:
        s,h=stored.split("$",1)
        return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256",pw.encode(),bytes.fromhex(s),310000).hex(),h)
    except Exception: return False


_BACKUP_DAY=None
def backup_database(force=False):
    global _BACKUP_DAY
    if not os.path.exists(DB): return None
    day=date.today().isoformat()
    if not force and _BACKUP_DAY==day: return None
    folder=os.path.join(ROOT,"backups"); os.makedirs(folder,exist_ok=True)
    stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
    target=os.path.join(folder,f"qubinaire_crm_{stamp}.db")
    src=sqlite3.connect(DB,timeout=30); dst=sqlite3.connect(target)
    try:
        src.backup(dst); dst.commit()
    finally:
        dst.close(); src.close()
    files=sorted([os.path.join(folder,n) for n in os.listdir(folder) if n.endswith(".db")],key=os.path.getmtime,reverse=True)
    for old in files[30:]:
        try: os.remove(old)
        except OSError: pass
    _BACKUP_DAY=day
    return target

def init_db():
    c=sqlite3.connect(DB)
    c.executescript("""
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
      full_name TEXT NOT NULL, password_hash TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'sales' CHECK(role IN ('admin','manager','sales')),
      active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS leads(
      id TEXT PRIMARY KEY, lead_type TEXT NOT NULL CHECK(lead_type IN ('student','college')),
      name TEXT NOT NULL, phone TEXT, email TEXT, institution TEXT, course_interest TEXT,
      city TEXT, district TEXT, state TEXT, source TEXT, status TEXT NOT NULL DEFAULT 'new',
      owner_id INTEGER, notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      FOREIGN KEY(owner_id) REFERENCES users(id)
    );
    CREATE INDEX IF NOT EXISTS idx_leads_owner ON leads(owner_id);
    CREATE INDEX IF NOT EXISTS idx_leads_updated ON leads(updated_at);
    CREATE TABLE IF NOT EXISTS activities(
      id TEXT PRIMARY KEY, lead_id TEXT NOT NULL, employee_id INTEGER NOT NULL,
      activity_type TEXT NOT NULL, notes TEXT, outcome TEXT, occurred_at TEXT NOT NULL,
      FOREIGN KEY(lead_id) REFERENCES leads(id), FOREIGN KEY(employee_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS followups(
      id TEXT PRIMARY KEY, lead_id TEXT NOT NULL, employee_id INTEGER NOT NULL,
      due_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', notes TEXT,
      created_at TEXT NOT NULL, FOREIGN KEY(lead_id) REFERENCES leads(id),
      FOREIGN KEY(employee_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS daily_reports(
      id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, report_date TEXT NOT NULL,
      calls INTEGER DEFAULT 0, connected_calls INTEGER DEFAULT 0,
      whatsapp_followups INTEGER DEFAULT 0, new_leads INTEGER DEFAULT 0,
      meetings INTEGER DEFAULT 0, college_visits INTEGER DEFAULT 0,
      admissions INTEGER DEFAULT 0, remarks TEXT, submitted_at TEXT NOT NULL,
      UNIQUE(user_id,report_date), FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS courses(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
      fee REAL NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS admissions(
      id TEXT PRIMARY KEY, lead_id TEXT NOT NULL, course_id INTEGER,
      admission_no TEXT UNIQUE NOT NULL, total_fee REAL NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending', admission_date TEXT NOT NULL,
      created_by INTEGER NOT NULL, created_at TEXT NOT NULL,
      FOREIGN KEY(lead_id) REFERENCES leads(id), FOREIGN KEY(course_id) REFERENCES courses(id),
      FOREIGN KEY(created_by) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS payments(
      id TEXT PRIMARY KEY, admission_id TEXT NOT NULL, amount REAL NOT NULL CHECK(amount>0),
      mode TEXT, reference TEXT, status TEXT NOT NULL DEFAULT 'received',
      payment_date TEXT NOT NULL, created_by INTEGER NOT NULL,
      FOREIGN KEY(admission_id) REFERENCES admissions(id), FOREIGN KEY(created_by) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS targets(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, period TEXT NOT NULL,
      start_date TEXT NOT NULL, end_date TEXT NOT NULL,
      leads_target INTEGER DEFAULT 0, admissions_target INTEGER DEFAULT 0,
      created_by INTEGER NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS sync_events(
      id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, record_id TEXT,
      entity TEXT, status TEXT, details TEXT, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS audit_logs(
      id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER, action TEXT NOT NULL,
      entity TEXT, entity_id TEXT, details TEXT, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS attendance(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, work_date TEXT NOT NULL,
      check_in TEXT NOT NULL, check_out TEXT, note TEXT,
      UNIQUE(user_id,work_date), FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS incentive_settings(
      id INTEGER PRIMARY KEY CHECK(id=1), collection_rate REAL NOT NULL DEFAULT 0,
      admission_bonus REAL NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS leave_requests(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
      leave_type TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
      reason TEXT, status TEXT NOT NULL DEFAULT 'pending',
      reviewed_by INTEGER, reviewed_at TEXT, review_note TEXT, created_at TEXT NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(reviewed_by) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS refund_requests(
      id INTEGER PRIMARY KEY AUTOINCREMENT, payment_id TEXT NOT NULL,
      requested_amount REAL NOT NULL CHECK(requested_amount>0), reason TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending', requested_by INTEGER NOT NULL,
      reviewed_by INTEGER, reviewed_at TEXT, review_note TEXT, created_at TEXT NOT NULL,
      FOREIGN KEY(payment_id) REFERENCES payments(id), FOREIGN KEY(requested_by) REFERENCES users(id),
      FOREIGN KEY(reviewed_by) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS incentive_payouts(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, period_start TEXT NOT NULL,
      period_end TEXT NOT NULL, estimated_amount REAL NOT NULL, approved_amount REAL,
      status TEXT NOT NULL DEFAULT 'pending', approved_by INTEGER, approved_at TEXT, note TEXT,
      created_at TEXT NOT NULL, UNIQUE(user_id,period_start,period_end),
      FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(approved_by) REFERENCES users(id)
    );
    INSERT OR IGNORE INTO incentive_settings(id,collection_rate,admission_bonus,updated_at)
      VALUES(1,0,0,'2026-01-01T00:00:00+00:00');
    """)
    c.commit()
    # Safe additive migration for V4 databases.
    cols=[r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
    if "manager_id" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN manager_id INTEGER REFERENCES users(id)")
    c.commit(); c.close()

@app.before_request
def boot():
    init_db()
    try: backup_database()
    except Exception: app.logger.exception('Automatic database backup failed')
def logged(fn):
    @wraps(fn)
    def w(*a,**k):
        if not session.get("uid"): return redirect(url_for("login"))
        u=conn().execute("SELECT * FROM users WHERE id=? AND active=1",(session["uid"],)).fetchone()
        if not u: session.clear(); return redirect(url_for("login"))
        return fn(*a,**k)
    return w
def admin(fn):
    @wraps(fn)
    @logged
    def w(*a,**k):
        if session.get("role")!="admin": flash("केवल Admin के लिए।","error"); return redirect(url_for("dashboard"))
        return fn(*a,**k)
    return w
@app.context_processor
def inject(): return {"current_user":session.get("name"),"current_role":session.get("role")}
@app.route("/setup",methods=["GET","POST"])
def setup():
    if conn().execute("SELECT COUNT(*) n FROM users").fetchone()["n"]:
        return redirect(url_for("login"))
    if request.method=="POST":
        name=request.form.get("name","").strip(); username=request.form.get("username","").strip()
        password=request.form.get("password","")
        if not name or not username or len(password)<12: flash("नाम/Username दें और कम से कम 12 अक्षर का मजबूत Password रखें।","error")
        else:
            conn().execute("INSERT INTO users(username,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?)",(username,name,pw_hash(password),"admin",now()))
            conn().commit(); flash("Admin account बन गया। Login करें।","success"); return redirect(url_for("login"))
    return render_template("setup.html")
@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=conn().execute("SELECT * FROM users WHERE username=? AND active=1",(request.form.get("username","").strip(),)).fetchone()
        if u and pw_ok(request.form.get("password",""),u["password_hash"]):
            session.clear(); session.update(uid=u["id"],name=u["full_name"],role=u["role"])
            return redirect(url_for("dashboard"))
        flash("गलत Login या Disabled Account।","error")
    return render_template("login.html")
@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))
@app.route("/")
@logged
def dashboard():
    c=conn(); uid=session["uid"]; role=session["role"]
    if role=="admin": cond=""; args=()
    elif role=="manager": cond=" WHERE owner_id=? OR owner_id IN (SELECT id FROM users WHERE manager_id=?)"; args=(uid,uid)
    else: cond=" WHERE owner_id=?"; args=(uid,)
    n=c.execute("SELECT COUNT(*) n FROM leads"+cond,args).fetchone()["n"]
    users=c.execute("SELECT COUNT(*) n FROM users WHERE active=1").fetchone()["n"] if role=="admin" else 1
    reports=c.execute("SELECT COUNT(*) n FROM daily_reports WHERE report_date=?",(date.today().isoformat(),)).fetchone()["n"]
    recent=c.execute("SELECT l.*,u.full_name owner FROM leads l LEFT JOIN users u ON u.id=l.owner_id"+cond+" ORDER BY l.updated_at DESC LIMIT 8",args).fetchall()
    return render_template("dashboard.html",n=n,users=users,reports=reports,recent=recent)
@app.route("/leads")
@logged
def leads():
    if session["role"]=="admin": rows=conn().execute("SELECT l.*,u.full_name owner FROM leads l LEFT JOIN users u ON u.id=l.owner_id ORDER BY l.updated_at DESC").fetchall()
    elif session["role"]=="manager": rows=conn().execute("SELECT l.*,u.full_name owner FROM leads l LEFT JOIN users u ON u.id=l.owner_id WHERE l.owner_id=? OR l.owner_id IN (SELECT id FROM users WHERE manager_id=?) ORDER BY l.updated_at DESC",(session["uid"],session["uid"])).fetchall()
    else: rows=conn().execute("SELECT l.*,u.full_name owner FROM leads l LEFT JOIN users u ON u.id=l.owner_id WHERE l.owner_id=? ORDER BY l.updated_at DESC",(session["uid"],)).fetchall()
    return render_template("leads.html",rows=rows)
@app.route("/leads/new",methods=["GET","POST"])
@logged
def lead_new():
    if request.method=="POST":
        f=request.form; name=f.get("name","").strip()
        if not name: flash("नाम आवश्यक है।","error")
        else:
            rid=secrets.token_hex(16); t=now()
            owner=int(f.get("owner_id")) if session["role"]=="admin" and f.get("owner_id") else session["uid"]
            conn().execute("""INSERT INTO leads VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
             (rid,f.get("lead_type","student"),name,f.get("phone"),f.get("email"),f.get("institution"),f.get("course_interest"),f.get("city"),f.get("district"),f.get("state"),f.get("source"),f.get("status","new"),owner,f.get("notes"),t,t))
            conn().execute("INSERT INTO audit_logs(actor_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",(session["uid"],"lead.create","lead",rid,"created via web",t))
            conn().commit(); flash("Lead सेव हो गई।","success"); return redirect(url_for("leads"))
    users=conn().execute("SELECT id,full_name FROM users WHERE active=1").fetchall() if session["role"]=="admin" else []
    return render_template("lead_form.html",users=users)
@app.route("/reports",methods=["GET","POST"])
@logged
def reports():
    if request.method=="POST":
        f=request.form; d=f.get("report_date") or date.today().isoformat()
        keys=["calls","connected_calls","whatsapp_followups","new_leads","meetings","college_visits","admissions"]
        vals=[]
        for k in keys:
            try: vals.append(max(0,int(f.get(k,0))))
            except: vals.append(0)
        rid=secrets.token_hex(16); t=now()
        conn().execute("""INSERT INTO daily_reports(id,user_id,report_date,calls,connected_calls,whatsapp_followups,new_leads,meetings,college_visits,admissions,remarks,submitted_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,report_date) DO UPDATE SET calls=excluded.calls,connected_calls=excluded.connected_calls,whatsapp_followups=excluded.whatsapp_followups,new_leads=excluded.new_leads,meetings=excluded.meetings,college_visits=excluded.college_visits,admissions=excluded.admissions,remarks=excluded.remarks,submitted_at=excluded.submitted_at""",
        (rid,session["uid"],d,*vals,f.get("remarks"),t))
        conn().commit(); flash("Report सेव हो गई।","success"); return redirect(url_for("reports"))
    if session["role"]=="admin": rows=conn().execute("SELECT r.*,u.full_name FROM daily_reports r JOIN users u ON u.id=r.user_id ORDER BY report_date DESC LIMIT 100").fetchall()
    else: rows=conn().execute("SELECT r.*,u.full_name FROM daily_reports r JOIN users u ON u.id=r.user_id WHERE user_id=? ORDER BY report_date DESC LIMIT 60",(session["uid"],)).fetchall()
    return render_template("reports.html",rows=rows,today=date.today().isoformat())
@app.route("/employees",methods=["GET","POST"])
@admin
def employees():
    if request.method=="POST":
        f=request.form; pw=f.get("password",""); role=f.get("role","sales")
        if role not in ("admin","manager","sales"): role="sales"
        try:
            manager_id=f.get("manager_id") or None
            if manager_id:
                m=conn().execute("SELECT id FROM users WHERE id=? AND role='manager' AND active=1",(manager_id,)).fetchone()
                if not m: manager_id=None
            conn().execute("INSERT INTO users(username,full_name,password_hash,role,created_at,manager_id) VALUES(?,?,?,?,?,?)",(f.get("username","").strip(),f.get("name","").strip(),pw_hash(pw),role,now(),manager_id if role=='sales' else None))
            conn().commit(); flash("User बनाया गया।","success")
        except sqlite3.IntegrityError: flash("Username मौजूद है।","error")
        return redirect(url_for("employees"))
    rows=conn().execute("SELECT u.id,u.username,u.full_name,u.role,u.active,u.manager_id,m.full_name manager_name FROM users u LEFT JOIN users m ON m.id=u.manager_id ORDER BY u.id").fetchall()
    managers=conn().execute("SELECT id,full_name FROM users WHERE role='manager' AND active=1 ORDER BY full_name").fetchall()
    return render_template("employees.html",rows=rows,managers=managers)
@app.route("/employees/<int:i>/toggle",methods=["POST"])
@admin
def toggle(i):
    if i!=session["uid"]:
        conn().execute("UPDATE users SET active=1-active WHERE id=?",(i,)); conn().commit()
    return redirect(url_for("employees"))
@app.route("/export/leads.csv")
@admin
def export():
    rows=conn().execute("SELECT l.*,u.full_name owner FROM leads l LEFT JOIN users u ON u.id=l.owner_id").fetchall()
    s=io.StringIO(); w=csv.writer(s); w.writerow(rows[0].keys() if rows else ["id","lead_type","name","phone"])
    for r in rows: w.writerow(list(r))
    return Response("\\ufeff"+s.getvalue(),mimetype="text/csv",headers={"Content-Disposition":"attachment; filename=qubinaire_leads.csv"})
@app.route("/api/sync/push",methods=["POST"])
@logged
def sync_push():
    data=request.get_json(silent=True) or {}; device=(data.get("device_id") or "web-pwa")[:100]
    accepted=[]; rejected=[]
    for item in data.get("changes",[])[:200]:
        try:
            if item.get("entity")=="lead" and item.get("operation")=="upsert":
                p=item.get("payload") or {}; rid=str(item.get("record_id") or "")
                if not rid or not p.get("name"): raise ValueError("record_id and name required")
                owner=session["uid"]
                t=now()
                existing=conn().execute("SELECT id,owner_id FROM leads WHERE id=?",(rid,)).fetchone()
                if existing and session["role"]!="admin" and existing["owner_id"]!=session["uid"]: raise PermissionError("not allowed")
                if existing:
                    conn().execute("""UPDATE leads SET name=?,phone=?,email=?,institution=?,course_interest=?,city=?,district=?,state=?,source=?,status=?,notes=?,updated_at=? WHERE id=?""",
                    (p.get("name"),p.get("phone"),p.get("email"),p.get("institution"),p.get("course_interest"),p.get("city"),p.get("district"),p.get("state"),p.get("source"),p.get("status","new"),p.get("notes"),t,rid))
                else:
                    conn().execute("""INSERT INTO leads(id,lead_type,name,phone,email,institution,course_interest,city,district,state,source,status,owner_id,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (rid,p.get("lead_type","student"),p.get("name"),p.get("phone"),p.get("email"),p.get("institution"),p.get("course_interest"),p.get("city"),p.get("district"),p.get("state"),p.get("source"),p.get("status","new"),owner,p.get("notes"),t,t))
                accepted.append({"record_id":rid,"status":"synced"})
            else: rejected.append({"record_id":item.get("record_id"),"error":"unsupported entity/operation"})
        except Exception as e: rejected.append({"record_id":item.get("record_id"),"error":str(e)})
    conn().commit()
    return jsonify({"accepted":accepted,"rejected":rejected,"accepted_count":len(accepted),"rejected_count":len(rejected)})
@app.route("/api/sync/pull")
@logged
def sync_pull():
    since=request.args.get("since","")
    if session["role"]=="admin":
        rows=conn().execute("SELECT * FROM leads WHERE updated_at>? ORDER BY updated_at LIMIT 500",(since,)).fetchall()
    else:
        rows=conn().execute("SELECT * FROM leads WHERE owner_id=? AND updated_at>? ORDER BY updated_at LIMIT 500",(session["uid"],since)).fetchall()
    return jsonify({"records":[dict(r) for r in rows],"cursor":rows[-1]["updated_at"] if rows else since})

# ---- V3 operational modules: admissions, collections, follow-ups, activities, targets ----
def visible_lead(lead_id):
    q="SELECT * FROM leads WHERE id=?"; row=conn().execute(q,(lead_id,)).fetchone()
    return row if row and (session.get('role')=='admin' or row['owner_id']==session.get('uid')) else None

@app.route('/courses',methods=['GET','POST'])
@logged
def courses():
    if request.method=='POST':
        if session['role']!='admin': flash('केवल Admin course बना सकता है।','error'); return redirect(url_for('courses'))
        name=request.form.get('name','').strip()
        try: fee=float(request.form.get('fee') or 0)
        except ValueError: fee=-1
        if not name or fee<0: flash('Course name और valid fee दें।','error')
        else:
            try:
                conn().execute('INSERT INTO courses(name,fee) VALUES(?,?)',(name,fee)); conn().commit(); flash('Course सेव हो गया।','success')
            except sqlite3.IntegrityError: flash('यह course पहले से मौजूद है।','error')
        return redirect(url_for('courses'))
    rows=conn().execute('SELECT * FROM courses ORDER BY name').fetchall()
    return render_template('courses.html',rows=rows)

@app.route('/admissions',methods=['GET','POST'])
@logged
def admissions():
    if request.method=='POST':
        f=request.form; lid=f.get('lead_id','')
        lead=visible_lead(lid)
        if not lead: flash('Lead नहीं मिली या access नहीं है।','error'); return redirect(url_for('admissions'))
        try: fee=float(f.get('total_fee') or 0)
        except ValueError: fee=0
        if fee<=0: flash('Total fee शून्य से अधिक होनी चाहिए।','error'); return redirect(url_for('admissions'))
        course_id=f.get('course_id') or None
        aid=secrets.token_hex(16); ano='QB-'+date.today().strftime('%y%m%d')+'-'+secrets.token_hex(3).upper(); t=now()
        conn().execute('INSERT INTO admissions(id,lead_id,course_id,admission_no,total_fee,status,admission_date,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(aid,lid,course_id,ano,fee,'active',f.get('admission_date') or date.today().isoformat(),session['uid'],t))
        conn().execute("UPDATE leads SET status='converted',updated_at=? WHERE id=?",(t,lid))
        conn().execute('INSERT INTO audit_logs(actor_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)',(session['uid'],'admission.create','admission',aid,ano,t))
        conn().commit(); flash('Admission बन गया: '+ano,'success'); return redirect(url_for('admission_detail',aid=aid))
    if session['role']=='admin':
        leads_rows=conn().execute("SELECT id,name,phone FROM leads WHERE lead_type='student' AND status!='converted' ORDER BY name").fetchall()
        rows=conn().execute('SELECT a.*,l.name student,c.name course,COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.admission_id=a.id AND p.status=\'received\'),0) paid FROM admissions a JOIN leads l ON l.id=a.lead_id LEFT JOIN courses c ON c.id=a.course_id ORDER BY a.created_at DESC').fetchall()
    else:
        leads_rows=conn().execute("SELECT id,name,phone FROM leads WHERE owner_id=? AND lead_type='student' AND status!='converted' ORDER BY name",(session['uid'],)).fetchall()
        rows=conn().execute("SELECT a.*,l.name student,c.name course,COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.admission_id=a.id AND p.status='received'),0) paid FROM admissions a JOIN leads l ON l.id=a.lead_id LEFT JOIN courses c ON c.id=a.course_id WHERE l.owner_id=? ORDER BY a.created_at DESC",(session['uid'],)).fetchall()
    crs=conn().execute('SELECT * FROM courses WHERE active=1 ORDER BY name').fetchall()
    return render_template('admissions.html',rows=rows,leads=leads_rows,courses=crs,today=date.today().isoformat())

@app.route('/admissions/<aid>',methods=['GET','POST'])
@logged
def admission_detail(aid):
    a=conn().execute('SELECT a.*,l.name student,l.phone,c.name course FROM admissions a JOIN leads l ON l.id=a.lead_id LEFT JOIN courses c ON c.id=a.course_id WHERE a.id=?',(aid,)).fetchone()
    if not a or (session['role']!='admin' and conn().execute('SELECT owner_id FROM leads WHERE id=?',(a['lead_id'],)).fetchone()['owner_id']!=session['uid']): return 'Not found',404
    if request.method=='POST':
        try: amount=float(request.form.get('amount') or 0)
        except ValueError: amount=0
        if amount<=0: flash('Payment amount valid होना चाहिए।','error')
        else:
            already=conn().execute("SELECT COALESCE(SUM(amount),0) paid FROM payments WHERE admission_id=? AND status='received'",(aid,)).fetchone()['paid']
            remaining=max(0,a['total_fee']-already)
            if amount>remaining+0.001:
                flash('Payment balance से अधिक है। पहले admission fee revise करें।','error')
            else:
                conn().execute('INSERT INTO payments(id,admission_id,amount,mode,reference,status,payment_date,created_by) VALUES(?,?,?,?,?,?,?,?)',(secrets.token_hex(16),aid,amount,request.form.get('mode'),request.form.get('reference'), 'received',request.form.get('payment_date') or date.today().isoformat(),session['uid']))
                conn().execute('INSERT INTO audit_logs(actor_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)',(session['uid'],'payment.received','admission',aid,str(amount),now()))
                conn().commit(); flash('Payment entry सेव हो गई।','success')
        return redirect(url_for('admission_detail',aid=aid))
    payments=conn().execute('SELECT p.*,u.full_name entered_by FROM payments p JOIN users u ON u.id=p.created_by WHERE admission_id=? ORDER BY payment_date DESC',(aid,)).fetchall()
    paid=sum(x['amount'] for x in payments if x['status']=='received')
    return render_template('admission_detail.html',a=a,payments=payments,paid=paid,balance=max(0,a['total_fee']-paid),today=date.today().isoformat())

@app.route('/followups',methods=['GET','POST'])
@logged
def followups():
    if request.method=='POST':
        f=request.form; lid=f.get('lead_id','')
        if not visible_lead(lid): flash('Lead access नहीं है।','error')
        else:
            conn().execute('INSERT INTO followups(id,lead_id,employee_id,due_at,status,notes,created_at) VALUES(?,?,?,?,?,?,?)',(secrets.token_hex(16),lid,session['uid'],f.get('due_at'), 'pending',f.get('notes'),now())); conn().commit(); flash('Follow-up schedule हो गया।','success')
        return redirect(url_for('followups'))
    if session['role']=='admin':
        leads_rows=conn().execute('SELECT id,name FROM leads ORDER BY name').fetchall()
        rows=conn().execute('SELECT f.*,l.name lead,u.full_name employee FROM followups f JOIN leads l ON l.id=f.lead_id JOIN users u ON u.id=f.employee_id ORDER BY f.due_at LIMIT 300').fetchall()
    else:
        leads_rows=conn().execute('SELECT id,name FROM leads WHERE owner_id=? ORDER BY name',(session['uid'],)).fetchall()
        rows=conn().execute('SELECT f.*,l.name lead,u.full_name employee FROM followups f JOIN leads l ON l.id=f.lead_id JOIN users u ON u.id=f.employee_id WHERE f.employee_id=? ORDER BY f.due_at LIMIT 200',(session['uid'],)).fetchall()
    return render_template('followups.html',rows=rows,leads=leads_rows)

@app.route('/followups/<fid>/done',methods=['POST'])
@logged
def followup_done(fid):
    q='SELECT * FROM followups WHERE id=?'; f=conn().execute(q,(fid,)).fetchone()
    if f and (session['role']=='admin' or f['employee_id']==session['uid']): conn().execute("UPDATE followups SET status='done' WHERE id=?",(fid,)); conn().commit(); flash('Follow-up complete।','success')
    return redirect(url_for('followups'))

@app.route('/activities',methods=['GET','POST'])
@logged
def activities():
    if request.method=='POST':
        f=request.form; lid=f.get('lead_id','')
        if not visible_lead(lid): flash('Lead access नहीं है।','error')
        else:
            conn().execute('INSERT INTO activities(id,lead_id,employee_id,activity_type,notes,outcome,occurred_at) VALUES(?,?,?,?,?,?,?)',(secrets.token_hex(16),lid,session['uid'],f.get('activity_type'),f.get('notes'),f.get('outcome'),now())); conn().execute('UPDATE leads SET updated_at=? WHERE id=?',(now(),lid)); conn().commit(); flash('Activity दर्ज हो गई।','success')
        return redirect(url_for('activities'))
    if session['role']=='admin':
        leads_rows=conn().execute('SELECT id,name FROM leads ORDER BY name').fetchall()
        rows=conn().execute('SELECT x.*,l.name lead,u.full_name employee FROM activities x JOIN leads l ON l.id=x.lead_id JOIN users u ON u.id=x.employee_id ORDER BY occurred_at DESC LIMIT 250').fetchall()
    else:
        leads_rows=conn().execute('SELECT id,name FROM leads WHERE owner_id=? ORDER BY name',(session['uid'],)).fetchall()
        rows=conn().execute('SELECT x.*,l.name lead,u.full_name employee FROM activities x JOIN leads l ON l.id=x.lead_id JOIN users u ON u.id=x.employee_id WHERE x.employee_id=? ORDER BY occurred_at DESC LIMIT 150',(session['uid'],)).fetchall()
    return render_template('activities.html',rows=rows,leads=leads_rows)

@app.route('/targets',methods=['GET','POST'])
@logged
def targets():
    if request.method=='POST':
        if session['role']!='admin': return 'Forbidden',403
        f=request.form; uid=int(f.get('user_id')); period=f.get('period','monthly')
        conn().execute('INSERT INTO targets(user_id,period,start_date,end_date,leads_target,admissions_target,created_by) VALUES(?,?,?,?,?,?,?)',(uid,period,f.get('start_date'),f.get('end_date'),int(f.get('leads_target') or 0),int(f.get('admissions_target') or 0),session['uid'])); conn().commit(); flash('Target सेव हो गया।','success'); return redirect(url_for('targets'))
    if session['role']=='admin':
        rows=conn().execute('SELECT t.*,u.full_name FROM targets t LEFT JOIN users u ON u.id=t.user_id ORDER BY start_date DESC').fetchall(); users=conn().execute('SELECT id,full_name FROM users WHERE active=1').fetchall()
    else:
        rows=conn().execute('SELECT t.*,u.full_name FROM targets t LEFT JOIN users u ON u.id=t.user_id WHERE t.user_id=? ORDER BY start_date DESC',(session['uid'],)).fetchall(); users=[]
    return render_template('targets.html',rows=rows,users=users,today=date.today().isoformat())

@app.route('/export/collections.csv')
@admin
def export_collections():
    rows=conn().execute("SELECT a.admission_no,l.name student,c.name course,a.total_fee,COALESCE(SUM(CASE WHEN p.status='received' THEN p.amount ELSE 0 END),0) paid,a.total_fee-COALESCE(SUM(CASE WHEN p.status='received' THEN p.amount ELSE 0 END),0) balance,a.status FROM admissions a JOIN leads l ON l.id=a.lead_id LEFT JOIN courses c ON c.id=a.course_id LEFT JOIN payments p ON p.admission_id=a.id GROUP BY a.id ORDER BY a.created_at DESC").fetchall()
    out=io.StringIO(); w=csv.writer(out); w.writerow(rows[0].keys() if rows else ['admission_no','student','course','total_fee','paid','balance','status'])
    for r in rows: w.writerow(list(r))
    return Response('\ufeff'+out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=qubinaire_collections.csv'})


# ---- V4: Attendance and transparent incentive estimate ----
@app.route('/attendance', methods=['GET','POST'])
@logged
def attendance():
    today=date.today().isoformat()
    if request.method=='POST':
        action=request.form.get('action')
        existing=conn().execute('SELECT * FROM attendance WHERE user_id=? AND work_date=?',(session['uid'],today)).fetchone()
        if action=='in':
            if existing: flash('आज की attendance पहले से शुरू है।','error')
            else:
                conn().execute('INSERT INTO attendance(user_id,work_date,check_in,note) VALUES(?,?,?,?)',(session['uid'],today,now(),request.form.get('note','')))
                conn().commit(); flash('Check-in दर्ज हो गया।','success')
        elif action=='out':
            if not existing: flash('पहले Check-in करें।','error')
            elif existing['check_out']: flash('आज का Check-out पहले ही दर्ज है।','error')
            else:
                conn().execute('UPDATE attendance SET check_out=? WHERE user_id=? AND work_date=?',(now(),session['uid'],today))
                conn().commit(); flash('Check-out दर्ज हो गया।','success')
        return redirect(url_for('attendance'))
    mine=conn().execute('SELECT * FROM attendance WHERE user_id=? AND work_date=?',(session['uid'],today)).fetchone()
    if session['role']=='admin':
        rows=conn().execute('SELECT a.*,u.full_name FROM attendance a JOIN users u ON u.id=a.user_id ORDER BY work_date DESC,check_in DESC LIMIT 250').fetchall()
    else:
        rows=conn().execute('SELECT a.*,u.full_name FROM attendance a JOIN users u ON u.id=a.user_id WHERE a.user_id=? ORDER BY work_date DESC LIMIT 90',(session['uid'],)).fetchall()
    return render_template('attendance.html',mine=mine,rows=rows,today=today)

@app.route('/incentives', methods=['GET','POST'])
@logged
def incentives():
    if request.method=='POST':
        if session['role']!='admin': return 'Forbidden',403
        try:
            rate=float(request.form.get('collection_rate') or 0)
            bonus=float(request.form.get('admission_bonus') or 0)
            if rate<0 or rate>100 or bonus<0: raise ValueError()
        except ValueError:
            flash('Rate 0–100% और bonus शून्य या अधिक होना चाहिए।','error')
            return redirect(url_for('incentives'))
        conn().execute('UPDATE incentive_settings SET collection_rate=?,admission_bonus=?,updated_at=? WHERE id=1',(rate,bonus,now()))
        conn().commit(); flash('Incentive settings अपडेट हो गईं।','success')
        return redirect(url_for('incentives'))
    settings=conn().execute('SELECT * FROM incentive_settings WHERE id=1').fetchone()
    start=request.args.get('start',date.today().replace(day=1).isoformat())
    end=request.args.get('end',date.today().isoformat())
    if session['role']=='admin':
        rows=conn().execute("""
          SELECT u.id,u.full_name,
            COALESCE(SUM(CASE WHEN p.status='received' AND p.payment_date BETWEEN ? AND ? THEN p.amount ELSE 0 END),0) collections,
            COUNT(DISTINCT CASE WHEN a.admission_date BETWEEN ? AND ? THEN a.id END) admissions
          FROM users u LEFT JOIN leads l ON l.owner_id=u.id
          LEFT JOIN admissions a ON a.lead_id=l.id
          LEFT JOIN payments p ON p.admission_id=a.id
          WHERE u.active=1 GROUP BY u.id ORDER BY u.full_name
        """,(start,end,start,end)).fetchall()
    else:
        rows=conn().execute("""
          SELECT u.id,u.full_name,
            COALESCE(SUM(CASE WHEN p.status='received' AND p.payment_date BETWEEN ? AND ? THEN p.amount ELSE 0 END),0) collections,
            COUNT(DISTINCT CASE WHEN a.admission_date BETWEEN ? AND ? THEN a.id END) admissions
          FROM users u LEFT JOIN leads l ON l.owner_id=u.id
          LEFT JOIN admissions a ON a.lead_id=l.id
          LEFT JOIN payments p ON p.admission_id=a.id
          WHERE u.id=? GROUP BY u.id
        """,(start,end,start,end,session['uid'])).fetchall()
    result=[]
    for r in rows:
        result.append(dict(r,estimated=(float(r['collections'])*settings['collection_rate']/100)+(int(r['admissions'])*settings['admission_bonus'])))
    return render_template('incentives.html',settings=settings,rows=result,start=start,end=end)

@app.route('/export/attendance.csv')
@admin
def export_attendance():
    rows=conn().execute('SELECT u.full_name,a.work_date,a.check_in,a.check_out,a.note FROM attendance a JOIN users u ON u.id=a.user_id ORDER BY work_date DESC').fetchall()
    out=io.StringIO(); w=csv.writer(out); w.writerow(['Employee','Date','Check in','Check out','Note'])
    for r in rows: w.writerow(list(r))
    return Response('\\ufeff'+out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=qubinaire_attendance.csv'})


# ---- V5: Team hierarchy, leave workflow, refund requests, incentive approvals ----
@app.route('/team')
@logged
def team():
    role=session['role']; uid=session['uid']
    if role=='admin':
        members=conn().execute("SELECT u.id,u.full_name,u.username,u.role,u.active,m.full_name manager_name,(SELECT COUNT(*) FROM leads l WHERE l.owner_id=u.id) leads_count,(SELECT COUNT(*) FROM admissions a JOIN leads l ON l.id=a.lead_id WHERE l.owner_id=u.id) admissions_count FROM users u LEFT JOIN users m ON m.id=u.manager_id ORDER BY u.role,u.full_name").fetchall()
    elif role=='manager':
        members=conn().execute("SELECT u.id,u.full_name,u.username,u.role,u.active,? manager_name,(SELECT COUNT(*) FROM leads l WHERE l.owner_id=u.id) leads_count,(SELECT COUNT(*) FROM admissions a JOIN leads l ON l.id=a.lead_id WHERE l.owner_id=u.id) admissions_count FROM users u WHERE u.id=? OR u.manager_id=? ORDER BY u.full_name",(session['name'],uid,uid)).fetchall()
    else:
        members=conn().execute("SELECT u.id,u.full_name,u.username,u.role,u.active,m.full_name manager_name,(SELECT COUNT(*) FROM leads l WHERE l.owner_id=u.id) leads_count,(SELECT COUNT(*) FROM admissions a JOIN leads l ON l.id=a.lead_id WHERE l.owner_id=u.id) admissions_count FROM users u LEFT JOIN users m ON m.id=u.manager_id WHERE u.id=?",(uid,)).fetchall()
    return render_template('team.html',members=members)

@app.route('/leave',methods=['GET','POST'])
@logged
def leave():
    if request.method=='POST':
        f=request.form; start=f.get('start_date'); end=f.get('end_date'); typ=f.get('leave_type','Casual')
        try:
            sd=date.fromisoformat(start); ed=date.fromisoformat(end)
            if ed<sd: raise ValueError()
            conn().execute("INSERT INTO leave_requests(user_id,leave_type,start_date,end_date,reason,created_at) VALUES(?,?,?,?,?,?)",(session['uid'],typ,start,end,f.get('reason','').strip(),now()))
            conn().commit(); flash('Leave request submit हो गई।','success')
        except Exception: flash('Valid leave dates दें; end date start date से पहले नहीं हो सकती।','error')
        return redirect(url_for('leave'))
    if session['role']=='admin':
        rows=conn().execute("SELECT r.*,u.full_name FROM leave_requests r JOIN users u ON u.id=r.user_id ORDER BY r.created_at DESC").fetchall()
    elif session['role']=='manager':
        rows=conn().execute("SELECT r.*,u.full_name FROM leave_requests r JOIN users u ON u.id=r.user_id WHERE r.user_id=? OR u.manager_id=? ORDER BY r.created_at DESC",(session['uid'],session['uid'])).fetchall()
    else:
        rows=conn().execute("SELECT r.*,u.full_name FROM leave_requests r JOIN users u ON u.id=r.user_id WHERE r.user_id=? ORDER BY r.created_at DESC",(session['uid'],)).fetchall()
    return render_template('leave.html',rows=rows)

@app.route('/leave/<int:rid>/review',methods=['POST'])
@logged
def leave_review(rid):
    row=conn().execute("SELECT * FROM leave_requests WHERE id=?",(rid,)).fetchone()
    if not row: return 'Not found',404
    allowed=session['role']=='admin' or (session['role']=='manager' and row['user_id']!=session['uid'] and conn().execute("SELECT manager_id FROM users WHERE id=?",(row['user_id'],)).fetchone()['manager_id']==session['uid'])
    if not allowed: return 'Forbidden',403
    status=request.form.get('status')
    if status not in ('approved','rejected'): return 'Invalid status',400
    conn().execute("UPDATE leave_requests SET status=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=? AND status='pending'",(status,session['uid'],now(),request.form.get('review_note',''),rid))
    conn().commit(); flash('Leave request review update हो गया।','success'); return redirect(url_for('leave'))

@app.route('/refunds',methods=['GET','POST'])
@logged
def refunds():
    if request.method=='POST':
        f=request.form; pid=f.get('payment_id','')
        p=conn().execute("SELECT p.*,a.lead_id,l.owner_id FROM payments p JOIN admissions a ON a.id=p.admission_id JOIN leads l ON l.id=a.lead_id WHERE p.id=?",(pid,)).fetchone()
        if not p or (session['role']!='admin' and p['owner_id']!=session['uid']): return 'Forbidden',403
        try: amount=float(f.get('requested_amount') or 0)
        except ValueError: amount=0
        already=conn().execute("SELECT COALESCE(SUM(requested_amount),0) n FROM refund_requests WHERE payment_id=? AND status IN ('pending','approved')",(pid,)).fetchone()['n']
        if amount<=0 or amount+already>p['amount']: flash('Refund amount payment balance से अधिक है।','error')
        else:
            conn().execute("INSERT INTO refund_requests(payment_id,requested_amount,reason,requested_by,created_at) VALUES(?,?,?,?,?)",(pid,amount,f.get('reason','').strip(),session['uid'],now()))
            conn().commit(); flash('Refund request approval के लिए भेजी गई।','success')
        return redirect(url_for('refunds'))
    if session['role']=='admin':
        rows=conn().execute("SELECT r.*,p.amount payment_amount,p.reference,u.full_name requester FROM refund_requests r JOIN payments p ON p.id=r.payment_id JOIN users u ON u.id=r.requested_by ORDER BY r.created_at DESC").fetchall()
        payrows=conn().execute("SELECT p.id,p.amount,p.payment_date,p.reference,a.admission_no,l.name student FROM payments p JOIN admissions a ON a.id=p.admission_id JOIN leads l ON l.id=a.lead_id WHERE p.status='received' ORDER BY p.payment_date DESC LIMIT 300").fetchall()
    else:
        rows=conn().execute("SELECT r.*,p.amount payment_amount,p.reference,u.full_name requester FROM refund_requests r JOIN payments p ON p.id=r.payment_id JOIN users u ON u.id=r.requested_by WHERE r.requested_by=? ORDER BY r.created_at DESC",(session['uid'],)).fetchall()
        payrows=conn().execute("SELECT p.id,p.amount,p.payment_date,p.reference,a.admission_no,l.name student FROM payments p JOIN admissions a ON a.id=p.admission_id JOIN leads l ON l.id=a.lead_id WHERE l.owner_id=? AND p.status='received' ORDER BY p.payment_date DESC LIMIT 300",(session['uid'],)).fetchall()
    return render_template('refunds.html',rows=rows,payrows=payrows)

@app.route('/refunds/<int:rid>/review',methods=['POST'])
@admin
def refund_review(rid):
    status=request.form.get('status')
    if status not in ('approved','rejected'): return 'Invalid status',400
    conn().execute("UPDATE refund_requests SET status=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=? AND status='pending'",(status,session['uid'],now(),request.form.get('review_note',''),rid))
    conn().commit(); flash('Refund request review update हुआ। ध्यान दें: यह approval है, bank refund execution नहीं।','success')
    return redirect(url_for('refunds'))

@app.route('/incentives/approve',methods=['POST'])
@admin
def incentive_approve():
    uid=request.form.get('user_id'); start=request.form.get('start'); end=request.form.get('end')
    try: amount=float(request.form.get('approved_amount') or 0)
    except ValueError: amount=-1
    if amount<0: flash('Approved amount valid नहीं है।','error'); return redirect(url_for('incentives',start=start,end=end))
    settings=conn().execute("SELECT * FROM incentive_settings WHERE id=1").fetchone()
    row=conn().execute("""SELECT COALESCE(SUM(CASE WHEN p.status='received' AND p.payment_date BETWEEN ? AND ? THEN p.amount ELSE 0 END),0) collections,COUNT(DISTINCT CASE WHEN a.admission_date BETWEEN ? AND ? THEN a.id END) admissions FROM users u LEFT JOIN leads l ON l.owner_id=u.id LEFT JOIN admissions a ON a.lead_id=l.id LEFT JOIN payments p ON p.admission_id=a.id WHERE u.id=?""",(start,end,start,end,uid)).fetchone()
    estimate=float(row['collections'])*settings['collection_rate']/100+int(row['admissions'])*settings['admission_bonus']
    if amount>estimate: flash('Approved amount calculated estimate से अधिक नहीं हो सकता।','error')
    else:
        conn().execute("""INSERT INTO incentive_payouts(user_id,period_start,period_end,estimated_amount,approved_amount,status,approved_by,approved_at,note,created_at)
          VALUES(?,?,?,?,?,'approved',?,?,?,?) ON CONFLICT(user_id,period_start,period_end) DO UPDATE SET estimated_amount=excluded.estimated_amount,approved_amount=excluded.approved_amount,status='approved',approved_by=excluded.approved_by,approved_at=excluded.approved_at,note=excluded.note""",(uid,start,end,estimate,amount,session['uid'],now(),request.form.get('note',''),now()))
        conn().commit(); flash('Incentive amount approved and recorded. Actual payout separately record करें।','success')
    return redirect(url_for('incentives',start=start,end=end))


@app.route('/admin/backups')
@admin
def admin_backups():
    folder=os.path.join(ROOT,'backups'); os.makedirs(folder,exist_ok=True)
    files=sorted([n for n in os.listdir(folder) if n.endswith('.db')],reverse=True)
    return render_template('backups.html',files=files)

@app.route('/admin/backups/run',methods=['POST'])
@admin
def run_backup():
    try:
        path=backup_database(force=True)
        flash('Database backup बनाया गया: '+os.path.basename(path),'success')
    except Exception as e:
        app.logger.exception('Manual backup failed'); flash('Backup नहीं बन पाया: '+str(e),'error')
    return redirect(url_for('admin_backups'))

@app.route('/admin/backups/download/<path:name>')
@admin
def download_backup(name):
    folder=os.path.realpath(os.path.join(ROOT,'backups'))
    path=os.path.realpath(os.path.join(folder,name))
    if os.path.commonpath([folder,path])!=folder or not os.path.isfile(path) or not path.endswith('.db'):
        return 'Not found',404
    with open(path,'rb') as fh: data=fh.read()
    return Response(data,mimetype='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="{os.path.basename(path)}"'})

@app.route('/admin/maintenance')
@admin
def admin_maintenance():
    folder=os.path.join(ROOT,'backups'); os.makedirs(folder,exist_ok=True)
    items=[]
    for name in sorted(os.listdir(folder), reverse=True):
        if not name.endswith('.db'): continue
        path=os.path.join(folder,name)
        size=os.path.getsize(path)
        status='Not checked'
        try:
            check=sqlite3.connect(f'file:{path}?mode=ro',uri=True,timeout=10)
            result=check.execute('PRAGMA integrity_check').fetchone()[0]
            required={r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            check.close()
            status='Healthy' if result=='ok' and {'users','leads'}.issubset(required) else 'Invalid / incomplete'
        except Exception as ex:
            status='Unreadable'
        items.append({'name':name,'size':size,'status':status})
    return render_template('maintenance.html',items=items)

@app.route('/admin/maintenance/verify',methods=['POST'])
@admin
def verify_database():
    target=request.form.get('name','')
    folder=os.path.realpath(os.path.join(ROOT,'backups'))
    path=os.path.realpath(os.path.join(folder,target))
    if os.path.dirname(path)!=folder or not target.endswith('.db') or not os.path.isfile(path):
        flash('चुना गया backup मान्य नहीं है।','error')
        return redirect(url_for('admin_maintenance'))
    try:
        c=sqlite3.connect(f'file:{path}?mode=ro',uri=True,timeout=10)
        result=c.execute('PRAGMA integrity_check').fetchone()[0]
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        c.close()
        ok=result=='ok' and {'users','leads'}.issubset(tables)
        flash(('Backup स्वस्थ है।' if ok else 'Backup में integrity/schema समस्या मिली।')+' '+target,'success' if ok else 'error')
        conn().execute('INSERT INTO audit_logs(actor_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)',(session['uid'],'backup.verify','backup',target,f'integrity={result}; required_tables={int({"users","leads"}.issubset(tables))}',now()))
        conn().commit()
    except Exception as e:
        flash('जाँच विफल: '+str(e),'error')
    return redirect(url_for('admin_maintenance'))

@app.route('/admin/maintenance/restore',methods=['POST'])
@admin
def restore_database():
    target=request.form.get('name','')
    folder=os.path.realpath(os.path.join(ROOT,'backups'))
    path=os.path.realpath(os.path.join(folder,target))
    if os.path.dirname(path)!=folder or not target.endswith('.db') or not os.path.isfile(path):
        flash('चुना गया backup मान्य नहीं है।','error')
        return redirect(url_for('admin_maintenance'))
    try:
        check=sqlite3.connect(f'file:{path}?mode=ro',uri=True,timeout=10)
        integrity=check.execute('PRAGMA integrity_check').fetchone()[0]
        tables={r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        check.close()
        if integrity!='ok' or not {'users','leads'}.issubset(tables):
            flash('Restore रोका गया: backup healthy CRM database नहीं है।','error')
            return redirect(url_for('admin_maintenance'))
        # Preserve the current live database before any restore operation.
        backup_database(force=True)
        old=g.pop('db',None)
        if old: old.close()
        source=sqlite3.connect(f'file:{path}?mode=ro',uri=True,timeout=30)
        dest=sqlite3.connect(DB,timeout=30)
        try:
            source.backup(dest); dest.commit()
        finally:
            dest.close(); source.close()
        # Reconnect and record the restore in the restored database's audit trail.
        c=sqlite3.connect(DB,timeout=20)
        c.execute('INSERT INTO audit_logs(actor_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)',(session['uid'],'database.restore','database',target,'restored from verified backup; pre-restore snapshot retained',now()))
        c.commit(); c.close()
        flash('Database restore हो गया। Restore से पहले का database अलग backup में सुरक्षित रखा गया है।','success')
    except Exception as e:
        app.logger.exception('Database restore failed')
        flash('Restore पूरा नहीं हो सका: '+str(e),'error')
    return redirect(url_for('admin_maintenance'))

@app.route('/admin/maintenance/export')
@admin
def export_database_snapshot():
    path=backup_database(force=True)
    if not path:
        flash('Database snapshot नहीं बन पाया।','error')
        return redirect(url_for('admin_maintenance'))
    from flask import send_file
    return send_file(path,as_attachment=True,download_name=os.path.basename(path),mimetype='application/octet-stream')

@app.route('/admin/audit')
@admin
def audit_page():
    rows=conn().execute("SELECT a.*,u.full_name FROM audit_logs a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 500").fetchall()
    return render_template('audit.html',rows=rows)

@app.route('/admin/import-leads',methods=['GET','POST'])
@admin
def import_leads():
    if request.method=='POST':
        f=request.files.get('file')
        if not f or not f.filename.lower().endswith('.csv'):
            flash('CSV file चुनें।','error'); return redirect(url_for('import_leads'))
        try:
            stream=io.StringIO(f.stream.read().decode('utf-8-sig'),newline='')
            reader=csv.DictReader(stream)
            if not reader.fieldnames or 'name' not in {x.strip().lower() for x in reader.fieldnames}:
                raise ValueError('CSV में name column जरूरी है।')
            mapping={x.strip().lower():x for x in reader.fieldnames}
            created=0; skipped=0
            for row in reader:
                def val(key): return (row.get(mapping.get(key,'')) or '').strip()
                name=val('name')
                if not name: skipped+=1; continue
                lead_id=secrets.token_hex(16); stamp=now()
                typ=val('lead_type') or 'student'
                if typ not in ('student','college'): typ='student'
                owner_id=None
                if val('owner_username'):
                    owner=conn().execute("SELECT id FROM users WHERE username=? AND active=1",(val('owner_username'),)).fetchone()
                    if owner: owner_id=owner['id']
                sql="INSERT INTO leads(id,lead_type,name,phone,email,institution,course_interest,city,district,state,source,status,owner_id,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                conn().execute(sql,(lead_id,typ,name,val('phone'),val('email'),val('institution'),val('course_interest'),val('city'),val('district'),val('state'),val('source') or 'CSV Import',val('status') or 'new',owner_id,val('notes'),stamp,stamp))
                created+=1
            conn().execute("INSERT INTO audit_logs(actor_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",(session['uid'],'leads.import','lead',f'imported={created}; skipped={skipped}',now()))
            conn().commit(); flash(f'Import complete: {created} leads added, {skipped} blank rows skipped.','success')
        except Exception as e:
            conn().rollback(); flash('CSV import failed: '+str(e),'error')
        return redirect(url_for('import_leads'))
    return render_template('import_leads.html')

@app.route("/health")
def health(): return jsonify(status="healthy",app="Qubinaire CRM V4",database="sqlite")
@app.route("/manifest.webmanifest")
def manifest(): return app.send_static_file("manifest.webmanifest")
if __name__=="__main__":
    app.run(host=os.environ.get("CRM_HOST","127.0.0.1"),port=int(os.environ.get("CRM_PORT","5000")),debug=False)
