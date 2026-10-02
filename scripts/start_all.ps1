<#
Arranca todo el stack de BrainBets (Docker Desktop + backend, frontend, n8n, postgres, workers)
al iniciar sesion en Windows. Pensado para ejecutarse desde una Tarea Programada.
#>

$ErrorActionPreference = "Continue"

$ProjectDir  = "C:\Users\alejo\Documents\opencode\brainbets"
$DockerExe   = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
$LogDir      = Join-Path $ProjectDir "storage\logs"
$LogFile     = Join-Path $LogDir "startup.log"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $LogFile -Value $line
}

Write-Log "=== Iniciando BrainBets stack ==="

# 1. Arrancar Docker Desktop si no esta corriendo
$dockerProc = Get-Process "Docker Desktop" -ErrorAction SilentlyContinue
if (-not $dockerProc) {
    Write-Log "Docker Desktop no esta corriendo. Arrancando..."
    Start-Process -FilePath $DockerExe
} else {
    Write-Log "Docker Desktop ya esta corriendo."
}

# 2. Esperar a que el daemon de Docker responda (hasta 5 minutos)
$maxWaitSeconds = 300
$elapsed = 0
$dockerReady = $false

while ($elapsed -lt $maxWaitSeconds) {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) {
        $dockerReady = $true
        break
    }
    Start-Sleep -Seconds 5
    $elapsed += 5
}

if (-not $dockerReady) {
    Write-Log "ERROR: Docker no respondio despues de $maxWaitSeconds segundos. Abortando."
    exit 1
}

Write-Log "Docker esta listo (esperados $elapsed s)."

# 3. Levantar el stack completo
Set-Location $ProjectDir
Write-Log "Ejecutando docker compose up -d..."
# Se usa cmd.exe para redirigir stdout/stderr a nivel de SO y evitar que PowerShell
# envuelva la salida de stderr de docker (que no siempre es un error real) en un ErrorRecord.
cmd /c "docker compose up -d >> `"$LogFile`" 2>&1"

if ($LASTEXITCODE -eq 0) {
    Write-Log "Stack levantado correctamente."
} else {
    Write-Log "ERROR: docker compose up -d fallo con codigo $LASTEXITCODE."
}

Write-Log "=== Fin del proceso de arranque ==="
