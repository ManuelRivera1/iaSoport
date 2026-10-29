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
    & curl.exe --fail --location --retry 2 --progress-bar --show-error --output $archivePath $asset.browser_download_url
    if ($LASTEXITCODE -ne 0) { throw 'Fallo la descarga de Ollama.' }
    Write-Host 'Verificando la integridad de la descarga...'
    $archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($asset.digest -and $asset.digest -ne ('sha256:' + $archiveHash)) {
        throw 'El checksum del paquete no coincide con GitHub.'
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    Write-Host 'Extrayendo Ollama y sus bibliotecas. Esta etapa no muestra porcentaje...'
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
    Write-Host 'Esperando a Ollama (la deteccion inicial de GPU puede tardar varios minutos)...'
    $startupTimer = [System.Diagnostics.Stopwatch]::StartNew()
    while ($startupTimer.Elapsed.TotalSeconds -lt 180) {
        Write-Host ('Esperando respuesta de Ollama: {0}s de un maximo de 180s...' -f [int]$startupTimer.Elapsed.TotalSeconds)
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
    # Read Ollama's NDJSON stream so the console shows actual downloaded bytes.
    $pullBody = @{ model = 'qwen3:4b'; stream = $true } | ConvertTo-Json
    $request = [System.Net.HttpWebRequest]::Create('http://127.0.0.1:11434/api/pull')
    $request.Method = 'POST'
    $request.ContentType = 'application/json'
    $request.Timeout = 3600000
    $request.ReadWriteTimeout = 3600000
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($pullBody)
    $request.ContentLength = $bodyBytes.Length
    $response = $null
    $reader = $null
    $previousStatus = ''
    $previousPercent = -1
    $pullSucceeded = $false
    try {
        $requestStream = $request.GetRequestStream()
        try { $requestStream.Write($bodyBytes, 0, $bodyBytes.Length) }
        finally { $requestStream.Dispose() }
        $response = $request.GetResponse()
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
        while ($null -ne ($line = $reader.ReadLine())) {
            if ([string]::IsNullOrWhiteSpace($line)) { continue }
            $update = $line | ConvertFrom-Json
            if ($update.error) { throw ('Ollama: ' + $update.error) }
            $status = [string]$update.status
            if ($status -ne $previousStatus) {
                Write-Host $status
                $previousStatus = $status
                $previousPercent = -1
            }
            if ($update.total -gt 0) {
                $percent = [int][Math]::Min(100, [Math]::Floor(100.0 * $update.completed / $update.total))
                if ($percent -ne $previousPercent) {
                    $filled = [int][Math]::Floor($percent / 4)
                    $bar = ('#' * $filled) + ('-' * (25 - $filled))
                    Write-Host ("`r  [{0}] {1,3}% - {2:N1} / {3:N1} MB (archivo actual)   " -f $bar, $percent, ($update.completed / 1MB), ($update.total / 1MB)) -NoNewline
                    if ($percent -eq 100) { Write-Host '' }
                    $previousPercent = $percent
                }
            }
            if ($status -eq 'success') { $pullSucceeded = $true }
        }
        if (-not $pullSucceeded) { throw 'La descarga del modelo se interrumpio. Vuelve a ejecutar el instalador para reintentar.' }
    } finally {
        if ($reader) { $reader.Dispose() }
        if ($response) { $response.Dispose() }
    }
    $tags = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags'
}
$tags.models | Where-Object name -eq 'qwen3:4b' | ConvertTo-Json -Depth 5 |
    Set-Content -Encoding UTF8 (Join-Path $runtimePath 'model.json')
Write-Host 'Ollama y qwen3:4b disponibles en 127.0.0.1:11434.'
