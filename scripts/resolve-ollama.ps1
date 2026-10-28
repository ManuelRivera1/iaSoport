function Resolve-LocalOllama {
    param([string]$ProjectPath)
    $installed = Get-Command ollama -ErrorAction SilentlyContinue
    if ($installed) { return $installed.Source }
    $userInstall = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path -LiteralPath $userInstall) { return $userInstall }
    return (Join-Path $ProjectPath 'data\ollama\ollama.exe')
}
