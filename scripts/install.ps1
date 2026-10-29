$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectPath
Write-Host '[1/4] Comprobando Git y preparando Python...'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Instala Git para Windows y vuelve a abrir este instalador.'
}
function Test-CompatiblePython {
    param([string]$Executable, [string[]]$PrefixArguments = @())
    try {
        & $Executable @PrefixArguments -c 'import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] < (3, 14) else 1)' 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Find-CompatiblePython {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($version in @('-3.13', '-3.12')) {
            if (Test-CompatiblePython -Executable 'py' -PrefixArguments @($version)) {
                return @{ Executable = 'py'; Arguments = @($version) }
            }
        }
    }
    $candidates = @('python', 'python3')
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
        $candidates += Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    }
    foreach ($candidate in $candidates) {
        if ((Get-Command $candidate -ErrorAction SilentlyContinue) -and
            (Test-CompatiblePython -Executable $candidate)) {
            return @{ Executable = $candidate; Arguments = @() }
        }
    }
    return $null
}

$pythonExe = Join-Path $projectPath '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $pythonExe) {
    if (-not (Test-CompatiblePython -Executable $pythonExe)) {
        throw 'El entorno .venv no funciona o usa un Python incompatible. Renombra la carpeta .venv como respaldo y vuelve a ejecutar el instalador. No cambies data/ ni knowledge/.'
    }
} else {
    if (Test-Path -LiteralPath (Join-Path $projectPath '.venv')) {
        throw 'La carpeta .venv esta incompleta. Renombrala como respaldo y vuelve a ejecutar el instalador.'
    }
    $runtime = Find-CompatiblePython
    if (-not $runtime) {
        Write-Host 'Support AI necesita Python 3.12 o 3.13 para sus dependencias.'
        Write-Host 'Se instalara Python 3.13 para este usuario. Puedes conservar tus otras versiones.'
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw 'No se encontro WinGet. Instala Python 3.13 desde https://www.python.org/downloads/windows/ y vuelve a ejecutar este instalador.'
        }
        & winget install --id Python.Python.3.13 --exact --source winget --scope user
        if ($LASTEXITCODE -ne 0) {
            throw 'No se pudo instalar Python 3.13 con WinGet. Instalalo desde https://www.python.org/downloads/windows/ y vuelve a intentarlo.'
        }
        $runtime = Find-CompatiblePython
        if (-not $runtime) {
            throw 'Python se instalo pero aun no se encuentra. Cierra esta ventana y vuelve a ejecutar Instalar Support AI.cmd.'
        }
    }
    $executable = $runtime.Executable
    $prefixArguments = $runtime.Arguments
    & $executable @prefixArguments -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear .venv. Revisa los permisos de la carpeta del proyecto.' }
}
Write-Host '[2/4] Instalando dependencias de Support AI...'
& $pythonExe -m pip install -r requirements-lite.txt
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias ligeras.' }
Write-Host '[3/4] Instalando la aplicacion...'
& $pythonExe -m pip install --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar Support AI.' }
Write-Host '[4/4] La guia esta instalada. Preparando Ollama y el modelo local...'
& (Join-Path $PSScriptRoot 'prepare-ollama.ps1')
Write-Host 'Listo. Abre Abrir Support AI.cmd para usar la guia.'
