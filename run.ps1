param(
    [switch]$ShareOnLan
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = Join-Path $backend ".venv\Scripts\python.exe"
$bindHost = if ($ShareOnLan) { "0.0.0.0" } else { "127.0.0.1" }

if (-not (Test-Path $python)) {
    Write-Host "Creating backend virtual environment..."
    & python -m venv (Join-Path $backend ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Could not create Python virtual environment." }
}
if (-not (Test-Path (Join-Path $backend ".venv\Lib\site-packages\fastapi"))) {
    Write-Host "Installing backend dependencies..."
    & $python -m pip install -r (Join-Path $backend "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Could not install backend dependencies." }
}
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "Installing frontend dependencies..."
    Push-Location $frontend
    & npm.cmd install
    $installExitCode = $LASTEXITCODE
    Pop-Location
    if ($installExitCode -ne 0) { throw "Could not install frontend dependencies." }
}

Push-Location $backend
& $python seed.py
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Could not load seed data." }
Pop-Location

$apiCommand = "Set-Location '$backend'; & '.\.venv\Scripts\python.exe' -m uvicorn main:app --reload --host $bindHost"
$webCommand = "Set-Location '$frontend'; npm.cmd run dev -- --host $bindHost"
Start-Process powershell.exe -ArgumentList @("-NoExit", "-Command", $apiCommand)
Start-Process powershell.exe -ArgumentList @("-NoExit", "-Command", $webCommand)
Write-Host "Backend: http://localhost:8000/docs"
Write-Host "Frontend: http://localhost:5173"
