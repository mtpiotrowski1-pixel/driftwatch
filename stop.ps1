# Zatrzymuje dzialajacy serwer Driftwatch (proces nasluchujacy na porcie 8000).
# Uzycie:  .\stop.ps1
$ErrorActionPreference = "Stop"

$conns = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if (-not $conns) {
    Write-Host "Driftwatch nie jest uruchomiony (port 8000 wolny)." -ForegroundColor Yellow
    exit 0
}

$pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($processId in $pids) {
    try {
        Stop-Process -Id $processId -Force -ErrorAction Stop
        Write-Host "Zatrzymano Driftwatch (PID $processId)." -ForegroundColor Green
    } catch {
        Write-Warning "Nie udalo sie zatrzymac PID $processId : $_"
    }
}
