"""Scheduled public-web Lead Hunter worker.
Configure a dedicated admin/manager service account and explicit public-search queries.
All generated CRM leads are created with status=review_required; no outreach is sent.
"""
import json, os, time, urllib.request, urllib.error, sys
API=os.getenv("CRM_API_URL","http://api:8080").rstrip("/")
USERNAME=os.getenv("LEAD_HUNTER_USERNAME","")
PASSWORD=os.getenv("LEAD_HUNTER_PASSWORD","")
QUERIES=os.getenv("LEAD_HUNTER_QUERIES","")
INTERVAL=max(900,int(os.getenv("LEAD_HUNTER_INTERVAL_SECONDS","21600")))
NUM_RESULTS=min(20,max(1,int(os.getenv("LEAD_HUNTER_NUM_RESULTS","20"))))

def call(path,method="GET",payload=None,token=None):
    data=None if payload is None else json.dumps(payload).encode()
    headers={"Content-Type":"application/json"}
    if token: headers["Authorization"]="Bearer "+token
    req=urllib.request.Request(API+path,data=data,headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=45) as response:
        raw=response.read().decode()
        return json.loads(raw) if raw else {}

def query_items():
    result=[]
    for raw in QUERIES.split("||"):
        raw=raw.strip()
        if not raw: continue
        if ":" in raw and raw.split(":",1)[0] in ("student","college"):
            target,query=raw.split(":",1)
        else:
            target,query="college",raw
        if len(query.strip())>=4: result.append((target,query.strip()))
    return result

def run_cycle():
    if not USERNAME or not PASSWORD:
        raise RuntimeError("Set LEAD_HUNTER_USERNAME and LEAD_HUNTER_PASSWORD")
    token=call("/v1/auth/login","POST",{"username":USERNAME,"password":PASSWORD})["access_token"]
    queries=query_items()
    if not queries: raise RuntimeError("Set LEAD_HUNTER_QUERIES using 'college:query||student:query' format")
    total_results=0; total_imported=0
    for target,query in queries:
        result=call("/v1/lead-hunter/search","POST",
            {"query":query,"target_type":target,"num_results":NUM_RESULTS,"auto_import":True},token)
        total_results+=len(result.get("results",[]))
        total_imported+=int(result.get("imported_count",0))
        print(json.dumps({"query":query,"target":target,"found":len(result.get("results",[])),
                          "imported":result.get("imported_count",0),"run_id":result.get("run_id")}),flush=True)
    print(json.dumps({"cycle_complete":True,"queries":len(queries),"results":total_results,
                      "new_review_required_leads":total_imported}),flush=True)

if __name__=="__main__":
    print("Qubinaire AI Lead Hunter worker started. No WhatsApp or outbound messaging is enabled.",flush=True)
    while True:
        try: run_cycle()
        except Exception as exc: print(f"Lead Hunter cycle failed: {type(exc).__name__}: {exc}",file=sys.stderr,flush=True)
        time.sleep(INTERVAL)
