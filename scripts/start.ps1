$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectPath
$runtimePath = Join-Path $projectPath 'data\ollama'
. (Join-Path $PSScriptRoot 'resolve-ollama.ps1')
$ollamaExe = Resolve-LocalOllama -ProjectPath $projectPath
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_MODELS = Join-Path $projectPath 'data\ollama-models'
$env:OLLAMA_NO_CLOUD = '1'
try { $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 2 }
catch {
    if (-not (Test-Path -LiteralPath $ollamaExe)) {
        throw 'Ejecuta primero scripts/prepare-ollama.ps1 para instalar el modelo local.'
    }
    Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden -WorkingDirectory $runtimePath -RedirectStandardOutput (Join-Path $runtimePath 'stdout.log') -RedirectStandardError (Join-Path $runtimePath 'stderr.log')
    $ready = $false
    Write-Host 'Esperando a Ollama (la deteccion inicial de GPU puede tardar varios minutos)...'
    $startupTimer = [System.Diagnostics.Stopwatch]::StartNew()
    while ($startupTimer.Elapsed.TotalSeconds -lt 180) {
        Start-Sleep -Seconds 1
        try {
            $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
            $ready = $true
            break
        } catch { }
    }
    if (-not $ready) { throw 'Ollama no inicio. Revisa data/ollama/stderr.log.' }
}
$tags = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags'
if (-not ($tags.models | Where-Object name -eq 'qwen3:4b')) {
    throw 'Falta qwen3:4b. Ejecuta scripts/prepare-ollama.ps1.'
}
if (-not $env:SUPPORT_AI_SEARCH_MODE) { $env:SUPPORT_AI_SEARCH_MODE = 'light' }
Write-Host 'Support AI iniciando. La interfaz se abrira en tu navegador.'
Write-Host 'Deja esta ventana abierta mientras usas la aplicacion.'
Start-Process -FilePath (Join-Path $projectPath '.venv\Scripts\python.exe') -ArgumentList '-m', 'support_ai.open_browser' -WindowStyle Hidden -WorkingDirectory $projectPath
& (Join-Path $projectPath '.venv\Scripts\python.exe') -m support_ai.launcher
