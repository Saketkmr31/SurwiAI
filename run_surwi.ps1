Set-Location $PSScriptRoot
if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
    Write-Host "Virtual environment not found. Create/install it first." -ForegroundColor Yellow
    exit 1
}
. .venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
