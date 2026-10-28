$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$projectPath = Split-Path -Parent $PSScriptRoot
$runtimePath = Join-Path $projectPath 'data\ollama'
$archivePath = Join-Path $projectPath 'data\ollama-windows-amd64.zip'
. (Join-Path $PSScriptRoot 'resolve-ollama.ps1')
$ollamaExe = Resolve-LocalOllama -ProjectPath $projectPath
New-Item -ItemType Directory -Force $runtimePath | Out-Null
if (-not (Test-Path -LiteralPath $ollamaExe)) {
    $release = Invoke-RestMethod 'https://api.github.com/repos/ollama/ollama/releases/latest'
    $asset = $release.assets | Where-Object name -eq 'ollama-windows-amd64.zip'
    if (-not $asset) { throw 'No se encontro el paquete oficial de Ollama.' }
    Write-Host ('Descargando Ollama ' + $release.tag_name + ' (paquete con bibliotecas GPU)...')
    & curl.exe --fail --location --retry 2 --silent --show-error --output $archivePath $asset.browser_download_url
    if ($LASTEXITCODE -ne 0) { throw 'Fallo la descarga de Ollama.' }
    $archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($asset.digest -and $asset.digest -ne ('sha256:' + $archiveHash)) {
        throw 'El checksum del paquete no coincide con GitHub.'
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($archivePath, $runtimePath)
    @{ release = $release.tag_name; sha256 = $archiveHash; url = $asset.browser_download_url } |
        ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $runtimePath 'installation.json')
}
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_MODELS = Join-Path $projectPath 'data\ollama-models'
$env:OLLAMA_NO_CLOUD = '1'
try { $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 2 }
catch {
    Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden -WorkingDirectory $runtimePath -RedirectStandardOutput (Join-Path $runtimePath 'stdout.log') -RedirectStandardError (Join-Path $runtimePath 'stderr.log')
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
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
    Write-Host 'Preparando qwen3:4b (descarga inicial, aproximadamente 2.5 GB)...'
    $pullBody = @{ model = 'qwen3:4b'; stream = $false } | ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/pull' -ContentType 'application/json' -Body $pullBody -TimeoutSec 3600 | Out-Null
    $tags = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags'
}
$tags.models | Where-Object name -eq 'qwen3:4b' | ConvertTo-Json -Depth 5 |
    Set-Content -Encoding UTF8 (Join-Path $runtimePath 'model.json')
Write-Host 'Ollama y qwen3:4b disponibles en 127.0.0.1:11434.'
