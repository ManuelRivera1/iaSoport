$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectPath
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Instala Git para Windows y vuelve a abrir este instalador.'
}
$pythonExe = Join-Path $projectPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    & py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Instala Python 3.12 o 3.13 desde python.org.' }
    }
}
& $pythonExe -m pip install -r requirements-lite.txt
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias ligeras.' }
& $pythonExe -m pip install --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar Support AI.' }
Write-Host 'La guia esta instalada. Preparando el modelo local por separado...'
& (Join-Path $PSScriptRoot 'prepare-ollama.ps1')
Write-Host 'Listo. Abre Abrir Support AI.cmd para usar la guia.'
