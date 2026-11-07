$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    uv venv --cache-dir .cache/uv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
}
uv pip install --python .venv/Scripts/python.exe --cache-dir .cache/uv -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& .venv/Scripts/python.exe -m app.ingest
if ($LASTEXITCODE -ne 0) { throw 'Corpus ingestion failed; live snapshot was preserved' }
& .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
