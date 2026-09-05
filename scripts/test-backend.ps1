$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$python = Join-Path $backend ".venv\Scripts\python.exe"
$testDatabase = "climbhub_test"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Backend-окружение не найдено. Сначала запустите scripts\start-dev.ps1."
}

$exists = & docker exec climbhub-postgres psql --username climbhub --dbname postgres `
    --tuples-only --no-align --command "SELECT 1 FROM pg_database WHERE datname = '$testDatabase';"
if ($LASTEXITCODE -ne 0) { throw "Не удалось проверить тестовую базу." }
if ("$exists".Trim() -ne "1") {
    & docker exec climbhub-postgres createdb --username climbhub $testDatabase
    if ($LASTEXITCODE -ne 0) { throw "Не удалось создать тестовую базу." }
}

Push-Location $backend
try {
    $previousTelegramBotToken = [Environment]::GetEnvironmentVariable("TELEGRAM_BOT_TOKEN", "Process")
    $previousTelegramChatId = [Environment]::GetEnvironmentVariable("TELEGRAM_CHAT_ID", "Process")
    & $python -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw "Не удалось установить тестовые зависимости." }
    $env:DATABASE_URL = "postgresql+psycopg://climbhub:climbhub@localhost:5432/$testDatabase"
    $env:TELEGRAM_BOT_TOKEN = ""
    $env:TELEGRAM_CHAT_ID = ""
    & $python -m app.migrate
    if ($LASTEXITCODE -ne 0) { throw "Не удалось применить миграции тестовой базы." }
    & $python -m pytest
    if ($LASTEXITCODE -ne 0) { throw "Backend-тесты завершились с ошибкой." }
}
finally {
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    if ($null -eq $previousTelegramBotToken) { Remove-Item Env:TELEGRAM_BOT_TOKEN -ErrorAction SilentlyContinue }
    else { $env:TELEGRAM_BOT_TOKEN = $previousTelegramBotToken }
    if ($null -eq $previousTelegramChatId) { Remove-Item Env:TELEGRAM_CHAT_ID -ErrorAction SilentlyContinue }
    else { $env:TELEGRAM_CHAT_ID = $previousTelegramChatId }
    Pop-Location
}
