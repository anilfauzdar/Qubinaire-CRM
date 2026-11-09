from pathlib import Path
import re, sys
ROOT=Path(__file__).resolve().parent
issues=[]
compose=(ROOT/"docker-compose.yml").read_text()
portal=(ROOT/"portal/portal.py").read_text()
api=(ROOT/"server/main.py").read_text()
if '${CRM_BIND_ADDRESS:-127.0.0.1}:5001:5001' not in compose: issues.append("Portal is not loopback-bound by default")
if '${CRM_BIND_ADDRESS:-127.0.0.1}:8080:8080' not in compose: issues.append("API is not loopback-bound by default")
if 'SESSION_COOKIE_HTTPONLY=True' not in portal: issues.append("Portal HttpOnly cookie flag missing")
if 'SESSION_COOKIE_SAMESITE="Lax"' not in portal: issues.append("Portal SameSite cookie flag missing")
if 'def protect_post_requests' not in portal or 'check_csrf()' not in portal: issues.append("Portal CSRF middleware missing")
if 'def require_device' not in api or 'd.user_id' not in api: issues.append("Device-user binding missing")
if 'def sync_push' not in api or 'version_conflict' not in api: issues.append("Sync conflict guard missing")
if 'EXA_API_KEY' not in api: issues.append("Lead Hunter API key gate missing")
if re.search(r'POSTGRES_PASSWORD:\s*(?!\$\{)[A-Za-z0-9]',compose): issues.append("Possible hard-coded database password")
if issues:
    print("FAIL")
    for issue in issues: print("-",issue)
    sys.exit(1)
print("Static security checks: PASS")
print("Reminder: this is not a penetration test or independent security audit.")
