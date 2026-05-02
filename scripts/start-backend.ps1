# Start FastAPI backend with hot reload
$root = Split-Path $PSScriptRoot -Parent
Set-Location "$root\backend"
.\venv\Scripts\Activate.ps1
uvicorn main:app --reload --host 0.0.0.0 --port 8000
