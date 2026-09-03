param(
    [switch]$ConfirmDemoData
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "backend\.venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Сначала запустите scripts\start-dev.ps1, чтобы подготовить backend."
}
if (-not $ConfirmDemoData) {
    throw "Демоданные могут изменить текущую базу. Для продолжения укажите -ConfirmDemoData."
}

Push-Location (Join-Path $root "backend")
try {
    & $python -m app.migrate
    $env:PARKROCK_ALLOW_DEMO_SEED = "1"
    & $python -m app.seed
}
finally {
    Remove-Item Env:PARKROCK_ALLOW_DEMO_SEED -ErrorAction SilentlyContinue
    Pop-Location
}
