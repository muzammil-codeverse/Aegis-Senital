# Bootstrap script — sets up backend venv + installs frontend deps
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent

Write-Host "`n=== Backend ===" -ForegroundColor Cyan
Set-Location "$root\backend"
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install --upgrade pip -q
pip install -r requirements.txt
Write-Host "Backend ready. Run: uvicorn main:app --reload" -ForegroundColor Green

Write-Host "`n=== Frontend ===" -ForegroundColor Cyan
Set-Location "$root\frontend"
npm install
Write-Host "Frontend ready. Run: npm run dev" -ForegroundColor Green

Set-Location $root
Write-Host "`nAll done." -ForegroundColor Green
