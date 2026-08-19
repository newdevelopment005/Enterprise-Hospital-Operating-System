# Run all Phase 0 unit tests locally (Windows PowerShell).
$services = @("configuration-service", "audit-service", "notification-service", "api-gateway")

foreach ($service in $services) {
    Write-Host ""
    Write-Host "========================================"
    Write-Host "Testing backend\$service"
    Write-Host "========================================"
    Push-Location "backend\$service"
    python -m pytest -q
    $exitCode = $LASTEXITCODE
    Pop-Location
    if ($exitCode -ne 0) {
        Write-Error "Tests failed for $service"
        exit $exitCode
    }
}

Write-Host "`nAll Phase 0 tests passed."