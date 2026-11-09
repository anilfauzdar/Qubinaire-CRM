import os, sys, glob, sqlite3, shutil, json, time
from pathlib import Path

APP_DIR=Path(__file__).resolve().parent
TARGET=APP_DIR/"data"/"qubinaire_crm.db"
LOG=APP_DIR/"migration_report.json"
HOME=Path.home()

def valid_db(path):
    try:
        con=sqlite3.connect(f"file:{path}?mode=ro",uri=True,timeout=5)
        check=con.execute("PRAGMA integrity_check").fetchone()[0]
        tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        return check=="ok" and "users" in tables and "leads" in tables
    except Exception:
        return False

def candidate_roots():
    roots=[APP_DIR.parent, HOME/"Desktop", HOME/"Downloads", HOME/"Documents"]
    # Common shared install directories if present.
    for p in [Path("C:/Qubinaire"), Path("C:/QubinaireCRM"), Path("C:/Qubinaire_CRM")]:
        roots.append(p)
    out=[]
    for r in roots:
        if r.exists() and r not in out: out.append(r)
    return out

def discover():
    found=[]
    seen=set()
    for base in candidate_roots():
        try:
            # Only search Qubinaire CRM version folders and this package's siblings.
            dirs=[]
            if base==APP_DIR.parent:
                dirs=[p for p in base.iterdir() if p.is_dir() and (p.name.lower().startswith("qubinaire_crm") or p.name.lower().startswith("qubinaire crm"))]
            else:
                dirs=[p for p in base.iterdir() if p.is_dir() and (p.name.lower().startswith("qubinaire_crm") or p.name.lower().startswith("qubinaire crm"))]
            for d in dirs:
                for pattern in ("data/qubinaire_crm.db","data/*.db","*.db"):
                    for p in d.glob(pattern):
                        key=str(p.resolve())
                        if key not in seen and p.is_file():
                            seen.add(key)
                            if valid_db(p): found.append(p)
        except (PermissionError,OSError):
            continue
    return sorted(found,key=lambda p:p.stat().st_mtime,reverse=True)

def main():
    TARGET.parent.mkdir(parents=True,exist_ok=True)
    report={"target":str(TARGET),"status":"no_legacy_database_found","candidates":[],"time":time.strftime("%Y-%m-%d %H:%M:%S")}
    if TARGET.exists() and valid_db(TARGET):
        report["status"]="existing_v7_database_kept"
        report["message"]="Existing CRM database was not overwritten."
    else:
        choices=discover()
        report["candidates"]=[str(p) for p in choices]
        if choices:
            source=choices[0]
            stamp=time.strftime("%Y%m%d_%H%M%S")
            temp=TARGET.with_suffix(".importing.db")
            src=sqlite3.connect(f"file:{source}?mode=ro",uri=True,timeout=30)
            dst=sqlite3.connect(temp,timeout=30)
            try:
                src.backup(dst); dst.commit()
                result=dst.execute("PRAGMA integrity_check").fetchone()[0]
                tables={r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if result!="ok" or not {"users","leads"}.issubset(tables):
                    raise RuntimeError("Imported database validation failed")
            finally:
                dst.close(); src.close()
            if TARGET.exists():
                saved=APP_DIR/"backups"; saved.mkdir(exist_ok=True)
                shutil.copy2(TARGET,saved/f"pre_migration_{stamp}.db")
            os.replace(temp,TARGET)
            report["status"]="legacy_database_imported"
            report["source"]=str(source)
            report["message"]="Latest valid legacy CRM database was imported. Schema upgrades will run on first V8 launch."
        else:
            report["message"]="No old CRM database was found in recognized Qubinaire_CRM folders. V8 will start fresh; old source-code archives are included separately."
    LOG.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(report["message"])
    if report.get("source"): print("Imported from:",report["source"])
    print("Report:",LOG)

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print("Automatic migration stopped safely:",exc)
        print("No source database was deleted.")
        sys.exit(2)
