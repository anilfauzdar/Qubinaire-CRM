param(
  [string]$ApiBase = "http://127.0.0.1:8080",
  [string]$PortalBase = "http://127.0.0.1:5001",
  [string]$ApiToken = ""
)
$ErrorActionPreference = "Stop"
Write-Host "Checking API health..."
$health = Invoke-RestMethod "$ApiBase/health" -TimeoutSec 10
if ($health.status -ne "ok") { throw "API health failed" }
Write-Host "API health: PASS"
Write-Host "Checking OpenAPI..."
$spec = Invoke-RestMethod "$ApiBase/openapi.json" -TimeoutSec 10
if (-not $spec.paths."/v1/sync/push") { throw "Sync push route missing" }
if (-not $spec.paths."/v1/lead-hunter/search") { throw "Lead Hunter route missing" }
Write-Host "OpenAPI routes: PASS"
Write-Host "Checking portal..."
$portal = Invoke-WebRequest "$PortalBase/health" -TimeoutSec 10
if ($portal.StatusCode -ne 200) { throw "Portal health failed" }
Write-Host "Portal health: PASS"
if ($ApiToken) {
  $headers=@{Authorization="Bearer $ApiToken"}
  $me=Invoke-RestMethod "$ApiBase/v1/me" -Headers $headers -TimeoutSec 10
  Write-Host "Authenticated API: PASS ($($me.username))"
}
Write-Host "Smoke tests passed. This is not a penetration or load test."
