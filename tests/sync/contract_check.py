"""Static contract checks for the multi-module offline sync implementation."""
from pathlib import Path
import ast, re, sys
root=Path(__file__).resolve().parents[2]
api=(root/'server/main.py').read_text()
client=(root/'clients/flutter/lib/main.dart').read_text()
schema=(root/'server/schema.sql').read_text()

# Parse Python source and assert one canonical sync pull endpoint.
ast.parse(api)
assert api.count('def sync_pull(')==1, 'duplicate sync_pull route'
assert '@app.get("/v1/sync/snapshot/{module}")' in api
assert 'pg_advisory_xact_lock(73201401)' in api
assert 'conn.begin_nested()' in api

# The client caches every writable API module and the read-only employee directory.
module_match=re.search(r'static const modules=\[(.*?)\];',client,re.S)
assert module_match, 'client module registry missing'
client_modules=set(re.findall(r"'([^']+)'",module_match.group(1)))
write_config=api.split('WRITE_CONFIG = {',1)[1].split('\n}',1)[0]
server_modules=set(re.findall(r'^\s*"([a-z_]+)"\s*:',write_config,re.M))
assert server_modules <= client_modules, f'missing client modules: {sorted(server_modules-client_modules)}'
assert 'users' in client_modules
pattern=re.search(r'entity: str = Field\(pattern="\^\((.*?)\)\$"\)',api)
assert pattern, 'sync entity allowlist missing'
allowed=set(pattern.group(1).split('|'))
assert {'lead'} | server_modules <= allowed, f'missing sync entities: {sorted((server_modules|{"lead"})-allowed)}'
assert 'CREATE TABLE IF NOT EXISTS sync_changes' in schema
assert 'device_id UUID REFERENCES devices(id)' in schema
assert "'/v1/sync/push'" not in api # route decorator is canonical and not a quoted URL literal
assert 'sync_boot_${module}_${Api.userId}' in client
assert "Connectivity().onConnectivityChanged" in client
assert "AppLifecycleState.resumed" in client
assert "CREATE TABLE IF NOT EXISTS module_records" in client
assert "CREATE TABLE IF NOT EXISTS id_mappings" in client
print(f'PASS: {len(server_modules)} writable modules + users read-only are wired to offline cache/sync.')
