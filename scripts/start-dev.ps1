$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}

Write-Host "Starting ParkRock Hub database..."
docker compose up -d

Write-Host "Preparing backend..."
Set-Location "$root\backend"
if (-not (Test-Path ".venv")) {
  python -m venv .venv
}
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}
.\.venv\Scripts\python.exe -m app.migrate

Write-Host "Starting backend at http://localhost:8001"
Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001"

Write-Host "Preparing frontend..."
Set-Location "$root\frontend"
if (-not (Test-Path "node_modules")) {
  npm install
}

Write-Host "Public results: http://localhost:3000"
Write-Host "Administration: http://localhost:3000/admin"
npm run dev
