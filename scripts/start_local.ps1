$ErrorActionPreference = 'Stop'
$repositoryPath = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repositoryPath
$pythonPath = Join-Path $repositoryPath '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required.' }
    & $pythonPath -m pip install -e '.[test,tools]'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
    & $pythonPath scripts/create_reviewer.py reviewer-01
    Write-Host 'Save the token above. Enter it in the dashboard.'
}
& $pythonPath -m uvicorn src.asgi:app --host 127.0.0.1 --port 8000
