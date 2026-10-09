# Uruchamia Driftwatch (serwer API + UI) na http://127.0.0.1:8000
# Uzycie:  .\start.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$exe = Join-Path $PSScriptRoot ".venv\Scripts\driftwatch.exe"
if (-not (Test-Path $exe)) {
    Write-Error "Nie znaleziono $exe . Najpierw uruchom .\install.ps1 (Python 3.12 i Node 22.12+)."
    exit 1
}

Write-Host "Uruchamiam Driftwatch; adres i port wynikaja z konfiguracji. Zatrzymaj: Ctrl+C." -ForegroundColor Green
& $exe
