"""Create the first Qubinaire CRM administrator.
Run inside the API container only after the schema exists:
  CRM_ADMIN_USERNAME=admin CRM_ADMIN_PASSWORD='strong-password' CRM_ADMIN_NAME='Qubinaire Admin' python bootstrap_admin.py
Refuses to run if any user already exists.
"""
import os, secrets, hashlib
from sqlalchemy import create_engine, text

url=os.getenv("DATABASE_URL")
username=os.getenv("CRM_ADMIN_USERNAME","").strip()
password=os.getenv("CRM_ADMIN_PASSWORD","")
full_name=os.getenv("CRM_ADMIN_NAME","Qubinaire Administrator").strip()
if not url or not username or len(password)<14:
    raise SystemExit("Set DATABASE_URL, CRM_ADMIN_USERNAME and CRM_ADMIN_PASSWORD (minimum 14 characters).")
salt=secrets.token_bytes(16)
digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,310000).hex()
stored=salt.hex()+"$"+digest
engine=create_engine(url,pool_pre_ping=True)
with engine.begin() as conn:
    count=conn.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
    if count:
        raise SystemExit("Refusing: users table is not empty. Use existing admin or a reviewed migration.")
    conn.execute(text("""INSERT INTO users(username,full_name,password_hash,role,active,manager_id,created_at)
      VALUES(:u,:n,:p,'admin',TRUE,NULL,NOW())"""),{"u":username,"n":full_name,"p":stored})
print("First admin created. Remove the password from shell history and store it in your password manager.")
