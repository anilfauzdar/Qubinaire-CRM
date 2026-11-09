from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def test_multimodule_offline_sync_contract():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "sync" / "contract_check.py")],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS:" in result.stdout

def test_standard_lead_create_does_not_require_lead_hunter_source_url():
    api = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
    start = api.index("def create_lead(")
    end = api.index('@app.patch("/v1/leads/{lead_id}")', start)
    handler = api[start:end]
    assert "body.source_url" not in handler
    assert "INSERT INTO lead_hunter_candidates" not in handler
