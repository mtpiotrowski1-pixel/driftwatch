param([switch]$Dev)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
foreach ($environment in @('.venv', '.venv-bootstrap')) {
    $environmentItem = Get-Item -LiteralPath $environment -Force -ErrorAction SilentlyContinue
    if ($environmentItem -and (($environmentItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or !$environmentItem.PSIsContainer)) {
        throw "Refusing linked or invalid $environment; existing files preserved"
    }
}
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit $LASTEXITCODE" }
}
if (!(Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    # The PSF's current Python 3.12 security releases are source-only on Windows.
    # Bootstrap uv in an isolated environment, then select its managed runtime.
    if (!(Test-Path -LiteralPath '.venv-bootstrap\Scripts\python.exe')) {
        Invoke-Checked 'py' @('-3', '-m', 'venv', '.venv-bootstrap')
    }
    $releaseBootstrap = Join-Path $PSScriptRoot '.venv-bootstrap\Scripts\python.exe'
    Invoke-Checked $releaseBootstrap @('-m', 'pip', 'install', '--require-hashes', '--only-binary=:all:', '-r', 'requirements-installer.lock')
    Invoke-Checked $releaseBootstrap @('-m', 'pip', 'install', '--require-hashes', '--only-binary=:all:', '-r', 'requirements-tools.lock')
    Invoke-Checked $releaseBootstrap @('-m', 'uv', 'venv', '--managed-python', '--python', '3.12.15', '.venv')
    Invoke-Checked $releaseBootstrap @('-m', 'uv', 'pip', 'install', '--python', '.venv\Scripts\python.exe', '--require-hashes', '--only-binary=:all:', '-r', 'requirements-installer.lock')
}
$releasePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Invoke-Checked $releasePython @('scripts/prepare_project_environment.py', '--check-only')
Invoke-Checked $releasePython @('-m', 'pip', 'install', '--require-hashes', '--only-binary=:all:', '-r', 'requirements-installer.lock')
$releaseLock = if ($Dev) { 'requirements-dev.lock' } else { 'requirements.lock' }
Invoke-Checked $releasePython @('-m', 'pip', 'install', '--require-hashes', '-r', $releaseLock)
Invoke-Checked $releasePython @('scripts/prepare_project_environment.py')
Invoke-Checked $releasePython @('-m', 'pip', 'install', '--require-hashes', '--only-binary=:all:', '-r', 'requirements-build.lock')
Invoke-Checked $releasePython @('-m', 'pip', 'install', '--no-deps', '--no-build-isolation', '-e', '.')
Invoke-Checked $releasePython @('-m', 'pip', 'check')
Invoke-Checked $releasePython @('-m', 'playwright', 'install', 'chromium')
Push-Location web
try {
    Invoke-Checked 'npm.cmd' @('ci')
    Invoke-Checked 'npm.cmd' @('run', 'build')
} finally { Pop-Location }
Write-Host 'Installed. Run .\start.ps1. Docker Compose provides the isolated worker and socket firewall.'
