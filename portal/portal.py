import os, secrets, time, json
from functools import wraps
from flask import Flask, request, redirect, url_for, session, render_template_string, flash
import requests

API_URL=os.getenv("CRM_API_URL","http://api:8080").rstrip("/")
SECRET=os.getenv("PORTAL_SECRET") or secrets.token_hex(32)
app=Flask(__name__)
app.secret_key=SECRET
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax",SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE","0")=="1")
# Opaque server-side sessions: browser receives only a random session id, not the API bearer token.
SESSIONS={}
SESSION_TTL=12*60*60

BASE="""
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Qubinaire CRM Central</title><style>
:root{font-family:Arial,sans-serif;color:#172033;background:#f4f6fa}body{margin:0}
header{background:#14213d;color:#fff;padding:15px 22px;display:flex;justify-content:space-between;align-items:center}
main{max-width:1100px;margin:24px auto;padding:0 16px}.card{background:#fff;border:1px solid #e3e7ef;border-radius:12px;padding:18px;margin:14px 0}
nav a{color:#fff;margin-right:16px;text-decoration:none}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.metric{font-size:28px;font-weight:bold;margin-top:7px}input,select,textarea{width:100%;padding:10px;margin:6px 0 12px;border:1px solid #ccd3df;border-radius:7px;box-sizing:border-box}
button,.btn{background:#2457c5;color:white;border:0;padding:10px 15px;border-radius:7px;cursor:pointer;text-decoration:none;display:inline-block}
table{width:100%;border-collapse:collapse;background:white}th,td{text-align:left;padding:10px;border-bottom:1px solid #e6e9ef;font-size:14px}
.small{color:#687386;font-size:13px}.error{background:#fff0f0;padding:10px;border-radius:8px}.success{background:#effaf2;padding:10px;border-radius:8px}
label{font-weight:600;font-size:14px} .actions{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}
@media(max-width:600px){header{display:block}nav{margin-top:12px}table{display:block;overflow:auto}}
</style></head><body><header><div><b>QUBINAIRE CRM</b><div class="small" style="color:#ccd5e7">Central workspace · Complete Edition</div></div>
{% if user %}<nav><a href="{{url_for('dashboard')}}">Dashboard</a><a href="{{url_for('leads')}}">Leads</a><a href="{{url_for('modules')}}">Modules</a>{% if user.role in ('admin','manager') %}<a href="{{url_for('lead_hunter')}}">AI Lead Hunter</a><a href="{{url_for('employees')}}">Employees</a>{% endif %}<a href="{{url_for('logout')}}">Logout</a></nav>{% endif %}</header>
<main>{% with messages=get_flashed_messages() %}{% for m in messages %}<div class="card">{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}</main></body></html>
"""
LOGIN="""<div class="card" style="max-width:420px;margin:50px auto"><h2>Central CRM Login</h2><p class="small">Use your migrated Qubinaire CRM username and password.</p>
<form method="post"><input type="hidden" name="_csrf" value="{{csrf}}"><label>Username</label><input name="username" required autocomplete="username"><label>Password</label><input type="password" name="password" required autocomplete="current-password"><button>Sign in</button></form></div>"""
DASH="""<h2>Dashboard</h2><p class="small">Live summary from PostgreSQL Central API.</p><div class="grid">
{% for label,value in metrics %}<div class="card"><div class="small">{{label}}</div><div class="metric">{{value}}</div></div>{% endfor %}</div>
<div class="card"><h3>Next actions</h3><div class="actions"><a class="btn" href="{{url_for('leads')}}">Open leads</a><a class="btn" href="{{url_for('new_lead')}}">Add lead</a><a class="btn" href="{{url_for('modules')}}">Open modules</a></div>
<p class="small">Your role: {{role}}. This portal uses the central API; it does not read the old SQLite database.</p></div>"""
LEADS="""<div style="display:flex;justify-content:space-between;align-items:center"><h2>Leads</h2><a class="btn" href="{{url_for('new_lead')}}">+ Add lead</a></div>
<div class="card"><table><thead><tr><th>Name</th><th>Type</th><th>Phone</th><th>City</th><th>Status</th><th>Owner</th><th>Action</th></tr></thead><tbody>
{% for l in items %}<tr><td>{{l.name}}</td><td>{{l.lead_type}}</td><td>{{l.phone or ''}}</td><td>{{l.city or ''}}</td><td>{{l.status}}</td><td>{{l.owner_id}}</td><td><a href="{{url_for('edit_lead',lead_id=l.id)}}">Edit</a></td></tr>{% else %}<tr><td colspan="7">No leads found.</td></tr>{% endfor %}</tbody></table></div>"""
NEW_LEAD="""<div class="card" style="max-width:680px"><h2>Add Lead</h2><form method="post"><input type="hidden" name="_csrf" value="{{csrf}}">
<label>Lead type</label><select name="lead_type"><option value="student">Student</option><option value="college">College</option></select>
<label>Name *</label><input name="name" required><label>Phone</label><input name="phone">
<label>Email</label><input name="email" type="email"><label>Institution / College</label><input name="institution">
<label>Course interest</label><input name="course_interest"><label>City</label><input name="city">
<label>District</label><input name="district"><label>State</label><input name="state">
<label>Lead source</label><input name="source"><label>Notes</label><textarea name="notes"></textarea>
<button>Save lead</button> <a class="btn" href="{{url_for('leads')}}">Cancel</a></form></div>"""
EDIT_LEAD="""<div class="card" style="max-width:680px"><h2>Edit Lead</h2><p class="small">Lead ID: {{lead.id}} · Version {{lead.version}}</p><form method="post"><input type="hidden" name="_csrf" value="{{csrf}}"><input type="hidden" name="expected_version" value="{{lead.version}}">
<label>Name *</label><input name="name" value="{{lead.name or ''}}" required><label>Phone</label><input name="phone" value="{{lead.phone or ''}}">
<label>Email</label><input name="email" type="email" value="{{lead.email or ''}}"><label>Institution / College</label><input name="institution" value="{{lead.institution or ''}}">
<label>Course interest</label><input name="course_interest" value="{{lead.course_interest or ''}}"><label>City</label><input name="city" value="{{lead.city or ''}}">
<label>District</label><input name="district" value="{{lead.district or ''}}"><label>State</label><input name="state" value="{{lead.state or ''}}">
<label>Lead source</label><input name="source" value="{{lead.source or ''}}"><label>Status</label><input name="status" value="{{lead.status or ''}}">
<label>Notes</label><textarea name="notes">{{lead.notes or ''}}</textarea><button>Update lead</button> <a class="btn" href="{{url_for('leads')}}">Cancel</a></form></div>"""
EMPLOYEES="""<div style="display:flex;justify-content:space-between;align-items:center"><h2>Employees & Teams</h2>{% if role=='admin' %}<a class="btn" href="{{url_for('new_employee')}}">+ Add employee</a>{% endif %}</div>
<div class="card"><table><thead><tr><th>ID</th><th>Name</th><th>Username</th><th>Role</th><th>Manager ID</th><th>Status</th>{% if role=='admin' %}<th>Action</th>{% endif %}</tr></thead><tbody>
{% for e in items %}<tr><td>{{e.id}}</td><td>{{e.full_name}}</td><td>{{e.username}}</td><td>{{e.role}}</td><td>{{e.manager_id or ''}}</td><td>{{'Active' if e.active else 'Inactive'}}</td>{% if role=='admin' %}<td><a href="{{url_for('edit_employee',employee_id=e.id)}}">Edit</a></td>{% endif %}</tr>{% else %}<tr><td colspan="7">No employees found.</td></tr>{% endfor %}</tbody></table></div>"""
EMPLOYEE_FORM="""<div class="card" style="max-width:620px"><h2>{{heading}}</h2><form method="post"><input type="hidden" name="_csrf" value="{{csrf}}">
<label>Full name *</label><input name="full_name" value="{{employee.get('full_name','')}}" required>
<label>Username *</label><input name="username" value="{{employee.get('username','')}}" {% if editing %}readonly{% else %}required{% endif %}>
<label>Role *</label><select name="role">{% for v in ['sales','manager','admin'] %}<option value="{{v}}" {% if employee.get('role','sales')==v %}selected{% endif %}>{{v.title()}}</option>{% endfor %}</select>
<label>Manager user ID (optional)</label><input name="manager_id" type="number" value="{{employee.get('manager_id') or ''}}">
<label>New password {% if not editing %}*{% endif %}</label><input name="password" type="password" {% if not editing %}required{% endif %} minlength="14" placeholder="Minimum 14 characters">
{% if editing %}<label><input type="checkbox" name="active" value="true" {% if employee.get('active') %}checked{% endif %} style="width:auto"> Active account</label>{% endif %}
<button>Save employee</button> <a class="btn" href="{{url_for('employees')}}">Cancel</a></form></div>"""
LEAD_HUNTER="""<h2>AI Lead Hunter</h2><p class="small">Search public web sources for student or college partnership prospects. Results are drafts for human verification, not verified contacts.</p>
<div class="card"><form method="post" action="{{url_for('lead_hunter')}}"><input type="hidden" name="_csrf" value="{{csrf}}">
<label>Search query</label><input name="query" value="{{query or ''}}" placeholder="e.g. engineering colleges in Madhya Pradesh official website" required minlength="4">
<label>Target type</label><select name="target_type"><option value="college" {% if target_type=='college' %}selected{% endif %}>College / University</option><option value="student" {% if target_type=='student' %}selected{% endif %}>Student public professional profiles</option></select>
<label>Maximum results</label><select name="num_results"><option>5</option><option selected>10</option><option>20</option></select><button>Search public web</button></form></div>
{% if results is not none %}<h3>{{results|length}} candidate sources · Run #{{run_id}}</h3>{% for r in results %}<div class="card"><b>{{r.title}}</b><p class="small">{{r.description}}</p><p><a href="{{r.url}}" target="_blank" rel="noopener noreferrer">{{r.url}}</a></p>
<form method="post" action="{{url_for('lead_hunter_import')}}"><input type="hidden" name="_csrf" value="{{csrf}}"><input type="hidden" name="lead_type" value="{{target_type}}"><input type="hidden" name="name" value="{{r.title}}"><input type="hidden" name="source_url" value="{{r.url}}"><input type="hidden" name="notes" value="{{r.description}}"><button>Import as review-required lead</button></form></div>{% endfor %}{% endif %}"""
MODULES="""<h2>CRM Modules</h2><p class="small">Module records retrieved from the PostgreSQL API. Some modules are view-only in this portal.</p>
<div class="grid">{% for m in modules %}<div class="card"><b>{{m.replace('_',' ').title()}}</b><p class="small">{{counts.get(m,0)}} records on this page</p><a class="btn" href="{{url_for('module_view',name=m)}}">Open</a></div>{% endfor %}</div>"""
MODULE_VIEW="""<div style="display:flex;justify-content:space-between;align-items:center"><h2>{{name.replace('_',' ').title()}}</h2>{% if can_create %}<a class="btn" href="{{url_for('module_new',name=name)}}">+ New record</a>{% endif %}</div>
<div class="card"><p class="small">Central PostgreSQL records · Showing up to 100 records. Access and allowed fields are enforced by the API according to your role.</p>
{% if items %}<table><thead><tr>{% for key in items[0].keys() %}<th>{{key}}</th>{% endfor %}<th>Action</th></tr></thead><tbody>{% for row in items %}<tr>{% for key in items[0].keys() %}<td>{{row.get(key,'')}}</td>{% endfor %}<td><a href="{{url_for('module_edit',name=name,record_id=row.get('id'))}}">Edit</a></td></tr>{% endfor %}</tbody></table>{% else %}<p>No records found or access is not granted.</p>{% endif %}</div>"""
MODULE_FORM="""<div class="card" style="max-width:760px"><h2>{{heading}}</h2>
<p class="small">Fill the fields below. Linked IDs must already exist and be accessible to your account.</p>
<form method="post"><input type="hidden" name="_csrf" value="{{csrf}}">
{% for field in fields %}
<label>{{field.label}}{% if field.required %} *{% endif %}</label>
{% if field.kind == 'textarea' %}<textarea name="{{field.name}}" rows="3">{{values.get(field.name,'')}}</textarea>
{% elif field.kind == 'select' %}<select name="{{field.name}}">{% for val,label in field.options %}<option value="{{val}}" {% if values.get(field.name,'')|string == val|string %}selected{% endif %}>{{label}}</option>{% endfor %}</select>
{% else %}<input name="{{field.name}}" type="{{field.kind}}" value="{{values.get(field.name,'')}}" {% if field.required %}required{% endif %} {% if field.kind == 'number' %}step="any"{% endif %}>{% endif %}
{% endfor %}
<button type="submit">Save record</button> <a class="btn" href="{{url_for('module_view',name=name)}}">Cancel</a></form></div>"""


MODULE_FIELDS = {
 "activities": ["lead_id","activity_type","notes","outcome","occurred_at"],
 "followups": ["lead_id","due_at","status","notes"],
 "daily_reports": ["report_date","calls","connected_calls","whatsapp_followups","new_leads","meetings","college_visits","admissions","remarks"],
 "courses": ["name","fee","active"],
 "admissions": ["lead_id","course_id","admission_no","total_fee","status","admission_date"],
 "payments": ["admission_id","amount","mode","reference","status","payment_date"],
 "attendance": ["work_date","check_in","check_out","note"],
 "leave_requests": ["leave_type","start_date","end_date","reason"],
 "refund_requests": ["payment_id","requested_amount","reason"],
 "incentive_payouts": ["user_id","period_start","period_end","estimated_amount","note"],
 "targets": ["user_id","period","start_date","end_date","leads_target","admissions_target"],
 "incentive_settings": ["collection_rate","admission_bonus"],
}
MODULE_FORM_FIELDS = {
 "activities":[("lead_id","Lead ID","text",True),("activity_type","Activity type","text",True),("notes","Notes","textarea",False),("outcome","Outcome","text",False),("occurred_at","Occurred at","datetime-local",True)],
 "followups":[("lead_id","Lead ID","text",True),("due_at","Due date/time","datetime-local",True),("status","Status","select",False)],
 "daily_reports":[("report_date","Report date","date",True),("calls","Calls","number",False),("connected_calls","Connected calls","number",False),("whatsapp_followups","WhatsApp follow-ups","number",False),("new_leads","New leads","number",False),("meetings","Meetings","number",False),("college_visits","College visits","number",False),("admissions","Admissions","number",False),("remarks","Remarks","textarea",False)],
 "courses":[("name","Course name","text",True),("fee","Fee (INR)","number",True),("active","Active","select",False)],
 "admissions":[("lead_id","Lead ID","text",True),("course_id","Course ID","number",False),("admission_no","Admission number","text",True),("total_fee","Total fee (INR)","number",True),("status","Status","text",False),("admission_date","Admission date","date",True)],
 "payments":[("admission_id","Admission ID","text",True),("amount","Amount (INR)","number",True),("mode","Payment mode","text",False),("reference","Reference","text",False),("status","Status","text",False),("payment_date","Payment date","date",True)],
 "attendance":[("work_date","Work date","date",True),("check_in","Check-in time","datetime-local",True),("check_out","Check-out time","datetime-local",False),("note","Note","textarea",False)],
 "leave_requests":[("leave_type","Leave type","text",True),("start_date","Start date","date",True),("end_date","End date","date",True),("reason","Reason","textarea",False),("status","Approval status","select",False),("review_note","Review note","textarea",False)],
 "refund_requests":[("payment_id","Payment ID","text",True),("requested_amount","Requested amount (INR)","number",True),("reason","Reason","textarea",True),("status","Approval status","select",False),("review_note","Review note","textarea",False)],
 "incentive_payouts":[("user_id","Employee user ID","number",True),("period_start","Period start","date",True),("period_end","Period end","date",True),("estimated_amount","Estimated amount (INR)","number",True),("approved_amount","Approved amount (INR)","number",False),("status","Approval status","select",False),("note","Note","textarea",False)],
 "targets":[("user_id","Employee user ID (optional)","number",False),("period","Period label","text",True),("start_date","Start date","date",True),("end_date","End date","date",True),("leads_target","Lead target","number",False),("admissions_target","Admission target","number",False)],
 "incentive_settings":[("collection_rate","Collection incentive rate (%)","number",True),("admission_bonus","Per-admission bonus (INR)","number",True)],
}

def csrf_token():
    token=session.get("_csrf")
    if not token:
        token=secrets.token_urlsafe(32)
        session["_csrf"]=token
    return token

def check_csrf():
    expected=session.get("_csrf","")
    supplied=request.form.get("_csrf","")
    if not expected or not secrets.compare_digest(expected,supplied):
        from flask import abort
        abort(400, "Invalid or missing CSRF token")

@app.before_request
def protect_post_requests():
    if request.method=="POST":
        check_csrf()

def render(body,**kwargs):
    kwargs.setdefault("csrf",csrf_token())
    return render_template_string(BASE,body=render_template_string(body,**kwargs),user=session.get("profile"))
def get_session():
    sid=session.get("sid")
    item=SESSIONS.get(sid)
    if not item: return None
    if item["expires"]<time.time():
        SESSIONS.pop(sid,None); session.clear(); return None
    item["expires"]=time.time()+SESSION_TTL
    return item
def api(method,path,**kwargs):
    s=get_session()
    if not s: return None,401
    headers=kwargs.pop("headers",{})
    headers["Authorization"]="Bearer "+s["token"]
    try:
        r=requests.request(method,API_URL+path,headers=headers,timeout=15,**kwargs)
        if r.status_code==401:
            SESSIONS.pop(session.get("sid"),None); session.clear()
            return None,401
        return (r.json() if r.content else {}),r.status_code
    except requests.RequestException:
        return None,503
def login_required(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        if not get_session(): return redirect(url_for("login"))
        return fn(*args,**kwargs)
    return wrapped
@app.route("/",methods=["GET"])
def home(): return redirect(url_for("dashboard") if get_session() else url_for("login"))
@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        try: r=requests.post(API_URL+"/v1/auth/login",json={"username":request.form.get("username",""),"password":request.form.get("password","")},timeout=15)
        except requests.RequestException:
            flash("Central API is unavailable. Start the API and PostgreSQL service."); return render(LOGIN)
        if r.status_code!=200:
            flash("Login failed. Check username/password and confirm user migration."); return render(LOGIN)
        data=r.json(); sid=secrets.token_urlsafe(32)
        SESSIONS[sid]={"token":data["access_token"],"profile":data["user"],"expires":time.time()+SESSION_TTL}
        session.clear(); session["sid"]=sid; session["profile"]=data["user"]
        return redirect(url_for("dashboard"))
    return render(LOGIN)
@app.route("/logout")
def logout():
    SESSIONS.pop(session.get("sid"),None); session.clear(); return redirect(url_for("login"))
@app.route("/dashboard")
@login_required
def dashboard():
    data,status=api("GET","/v1/dashboard/summary")
    if status!=200: flash("Dashboard API error. Check API status and access permissions."); data={"leads":"—","admissions":"—","collections":"—","pending_followups":"—"}
    metrics=[("Leads",data.get("leads","—")),("Admissions",data.get("admissions","—")),("Collections",data.get("collections","—")),("Pending follow-ups",data.get("pending_followups","—"))]
    return render(DASH,metrics=metrics,role=session["profile"].get("role",""))
@app.route("/leads")
@login_required
def leads():
    data,status=api("GET","/v1/leads?limit=200")
    if status!=200: flash("Could not load leads. Check your role and API."); data={"items":[]}
    return render(LEADS,items=data.get("items",[]))
@app.route("/leads/new",methods=["GET","POST"])
@login_required
def new_lead():
    if request.method=="POST":
        fields=["lead_type","name","phone","email","institution","course_interest","city","district","state","source","notes"]
        payload={k:request.form.get(k) or None for k in fields}
        payload["name"]=request.form.get("name","").strip()
        data,status=api("POST","/v1/leads",json=payload)
        if status in (200,201): flash("Lead created successfully."); return redirect(url_for("leads"))
        flash("Lead was not saved. API response: "+str(data or status))
    return render(NEW_LEAD)
@app.route("/leads/<lead_id>/edit",methods=["GET","POST"])
@login_required
def edit_lead(lead_id):
    data,status=api("GET","/v1/leads?limit=500")
    items=data.get("items",[]) if status==200 and data else []
    lead=next((x for x in items if str(x.get("id"))==str(lead_id)),None)
    if lead is None:
        flash("Lead not found in your permitted records.")
        return redirect(url_for("leads"))
    if request.method=="POST":
        fields=["name","phone","email","institution","course_interest","city","district","state","source","status","notes"]
        payload={k:(request.form.get(k) or None) for k in fields}
        payload["expected_version"]=int(request.form.get("expected_version",lead.get("version",1)))
        result,code=api("PATCH",f"/v1/leads/{lead_id}",json=payload)
        if code==200:
            flash("Lead updated successfully.")
            return redirect(url_for("leads"))
        flash("Lead update failed: "+str(result or code))
        lead.update({k:v for k,v in payload.items() if k!="expected_version"})
    return render(EDIT_LEAD,lead=lead)

@app.route("/lead-hunter",methods=["GET","POST"])
@login_required
def lead_hunter():
    if session["profile"].get("role") not in ("admin","manager"): return "Forbidden",403
    results=None; run_id=None; query=""; target_type="college"
    if request.method=="POST":
        query=request.form.get("query","").strip()
        target_type=request.form.get("target_type","college")
        n=int(request.form.get("num_results","10"))
        data,code=api("POST","/v1/lead-hunter/search",json={"query":query,"target_type":target_type,"num_results":n})
        if code==200:
            results=data.get("results",[]); run_id=data.get("run_id")
            flash("Candidates found. Verify each source before import.")
        else:
            flash("Lead Hunter unavailable: "+str(data or code))
            results=[]
    return render(LEAD_HUNTER,results=results,run_id=run_id,query=query,target_type=target_type)

@app.route("/lead-hunter/import",methods=["POST"])
@login_required
def lead_hunter_import():
    if session["profile"].get("role") not in ("admin","manager"): return "Forbidden",403
    payload={k:request.form.get(k) for k in ["lead_type","name","source_url","notes"]}
    data,code=api("POST","/v1/lead-hunter/import",json=payload)
    flash("Imported as review-required lead: "+str(data.get("id")) if code==201 else "Import failed: "+str(data or code))
    return redirect(url_for("lead_hunter"))

@app.route("/employees")
@login_required
def employees():
    role=session["profile"].get("role","")
    if role not in ("admin","manager"): return "Forbidden",403
    data,status=api("GET","/v1/users?limit=500")
    if status!=200: flash("Could not load employee list."); data={"items":[]}
    return render(EMPLOYEES,items=data.get("items",[]),role=role)

@app.route("/employees/new",methods=["GET","POST"])
@login_required
def new_employee():
    if session["profile"].get("role")!="admin": return "Only admin can add employees",403
    employee={"role":"sales"}
    if request.method=="POST":
        payload={"username":request.form.get("username","").strip(),"full_name":request.form.get("full_name","").strip(),
                 "password":request.form.get("password",""),"role":request.form.get("role","sales")}
        mid=request.form.get("manager_id","").strip()
        if mid: payload["manager_id"]=int(mid)
        data,status=api("POST","/v1/users",json=payload)
        if status in (200,201):
            flash("Employee created. User ID: "+str(data.get("id","")))
            return redirect(url_for("employees"))
        flash("Employee not created: "+str(data or status))
        employee={**payload}
    return render(EMPLOYEE_FORM,heading="Add employee",employee=employee,editing=False)

@app.route("/employees/<int:employee_id>/edit",methods=["GET","POST"])
@login_required
def edit_employee(employee_id):
    if session["profile"].get("role")!="admin": return "Only admin can edit employees",403
    data,status=api("GET","/v1/users?limit=500")
    items=data.get("items",[]) if status==200 and data else []
    employee=next((x for x in items if int(x.get("id"))==employee_id),None)
    if employee is None: flash("Employee not found."); return redirect(url_for("employees"))
    if request.method=="POST":
        payload={"full_name":request.form.get("full_name","").strip(),"role":request.form.get("role","sales"),
                 "active":request.form.get("active")=="true"}
        mid=request.form.get("manager_id","").strip()
        payload["manager_id"]=int(mid) if mid else None
        password=request.form.get("password","")
        if password: payload["password"]=password
        result,code=api("PATCH",f"/v1/users/{employee_id}",json=payload)
        if code==200:
            flash("Employee updated.")
            return redirect(url_for("employees"))
        flash("Employee update failed: "+str(result or code))
        employee.update({k:v for k,v in payload.items() if k!="password"})
    return render(EMPLOYEE_FORM,heading="Edit employee",employee=employee,editing=True)

@app.route("/modules")
@login_required
def modules():
    names=["activities","followups","daily_reports","courses","admissions","payments","attendance","leave_requests","refund_requests","incentive_payouts","targets","incentive_settings"]
    counts={}
    for name in names:
        data,status=api("GET",f"/v1/modules/{name}?limit=1")
        counts[name]=len(data.get("items",[])) if status==200 and data else 0
    return render(MODULES,modules=names,counts=counts)
@app.route("/modules/<name>")
@login_required
def module_view(name):
    allowed=set(MODULE_FIELDS)
    if name not in allowed: return "Not found",404
    data,status=api("GET",f"/v1/modules/{name}?limit=100")
    if status!=200: flash("Module unavailable or access denied."); data={"items":[]}
    role=session["profile"].get("role","")
    can_create = name not in ("courses","targets","incentive_payouts","incentive_settings") or role=="admin"
    return render(MODULE_VIEW,name=name,items=data.get("items",[]),can_create=can_create)

def build_form_fields(name, values):
    fields=[]
    for field_name,label,kind,required in MODULE_FORM_FIELDS[name]:
        value=values.get(field_name,"")
        if value is None:
            value=""
        if kind=="datetime-local" and value:
            value=str(value).replace("Z","").replace(" ","T")[:16]
            values[field_name]=value
        if field_name=="active" and value!="":
            values[field_name]=str(value).lower()
        if field_name=="status" and name=="followups":
            kind="select"; options=[("pending","Pending"),("completed","Completed"),("cancelled","Cancelled")]
        elif field_name=="status" and name in ("leave_requests","refund_requests","incentive_payouts"):
            kind="select"; options=[("pending","Pending"),("approved","Approved"),("rejected","Rejected"),("paid","Paid")]
        elif field_name=="active":
            kind="select"; options=[("true","Active"),("false","Inactive")]
        else:
            options=[]
        fields.append({"name":field_name,"label":label,"kind":kind,"required":required,"options":options})
    return fields

def form_payload(name):
    payload={}
    for field_name,label,kind,required in MODULE_FORM_FIELDS[name]:
        raw=request.form.get(field_name,"").strip()
        if raw=="":
            continue
        if kind=="number":
            payload[field_name]=float(raw) if "." in raw else int(raw)
        elif field_name=="active":
            payload[field_name]=(raw.lower()=="true")
        elif kind=="datetime-local":
            # Portal inputs are India local time; send an explicit +05:30 offset.
            payload[field_name]=raw.replace("T"," ")+(":00+05:30" if len(raw)==16 else "+05:30")
        else:
            payload[field_name]=raw
    return payload

@app.route("/modules/<name>/new",methods=["GET","POST"])
@login_required
def module_new(name):
    if name not in MODULE_FIELDS: return "Not found",404
    role=session["profile"].get("role","")
    if name in ("courses","targets","incentive_payouts","incentive_settings") and role!="admin":
        return "Only admin can create this record",403
    values={}
    if request.method=="POST":
        try:
            payload=form_payload(name)
        except (ValueError,TypeError) as exc:
            flash("Please check numeric values: "+str(exc)); payload={}
        else:
            data,status=api("POST",f"/v1/modules/{name}",json=payload)
            if status in (200,201):
                flash("Record created successfully. Record ID: "+str(data.get("id","")))
                return redirect(url_for("module_view",name=name))
            flash("Record not saved. API response: "+str(data or status))
            values=request.form.to_dict()
    fields=build_form_fields(name,values)
    return render(MODULE_FORM,name=name,heading="New "+name.replace("_"," ").title(),fields=fields,values=values)

@app.route("/modules/<name>/<record_id>/edit",methods=["GET","POST"])
@login_required
def module_edit(name,record_id):
    if name not in MODULE_FIELDS: return "Not found",404
    if name in ("courses","targets","incentive_payouts","incentive_settings") and session["profile"].get("role")!="admin":
        return "Only admin can edit this record",403
    if request.method=="POST":
        try:
            payload=form_payload(name)
        except (ValueError,TypeError) as exc:
            flash("Please check numeric values: "+str(exc)); payload={}
        else:
            data,status=api("PATCH",f"/v1/modules/{name}/{record_id}",json=payload)
            if status==200:
                flash("Record updated successfully.")
                return redirect(url_for("module_view",name=name))
            flash("Record not updated. API response: "+str(data or status))
            values=request.form.to_dict()
    else:
        data,status=api("GET",f"/v1/modules/{name}?limit=500")
        items=data.get("items",[]) if status==200 and data else []
        record=next((r for r in items if str(r.get("id"))==str(record_id)),None)
        if record is None:
            flash("Record not found in your permitted records, or it is outside the current page.")
            return redirect(url_for("module_view",name=name))
        values={k:record.get(k) for k in MODULE_FIELDS[name] if k in record}
    fields=build_form_fields(name,values)
    return render(MODULE_FORM,name=name,heading="Edit "+name.replace("_"," ").title(),fields=fields,values=values)

@app.get("/health")
def health():
    try:
        r=requests.get(API_URL+"/health",timeout=5)
        return {"portal":"ok","central_api":r.status_code==200},200 if r.status_code==200 else 503
    except requests.RequestException: return {"portal":"ok","central_api":False},503
