<#
Arranca todo el stack de BrainBets (Docker Desktop + backend, frontend, n8n, postgres, workers)
y el tunel publico de ngrok al iniciar sesion en Windows. Pensado para ejecutarse desde una
Tarea Programada (ver Tarea "BrainBets-Startup", trigger de logon).
#>

$ErrorActionPreference = "Continue"

$ProjectDir   = "C:\Users\alejo\Documents\opencode\brainbets"
$DockerExe    = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
$NgrokExe     = "C:\Users\alejo\AppData\Local\Microsoft\WindowsApps\ngrok.exe"
$NgrokDomain  = "moneyless-suppletory-aryana.ngrok-free.dev"
$LogDir       = Join-Path $ProjectDir "storage\logs"
$LogFile      = Join-Path $LogDir "startup.log"

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

# 4. Esperar a que el frontend (nginx, puerto 80) responda antes de exponerlo
$maxWaitSeconds = 120
$elapsed = 0
$frontendReady = $false
while ($elapsed -lt $maxWaitSeconds) {
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:80" -UseBasicParsing -TimeoutSec 5
        if ($resp.StatusCode -eq 200) { $frontendReady = $true; break }
    } catch {}
    Start-Sleep -Seconds 5
    $elapsed += 5
}
if ($frontendReady) {
    Write-Log "Frontend listo (esperados $elapsed s)."
} else {
    Write-Log "ADVERTENCIA: frontend no respondio tras $maxWaitSeconds s. Arrancando ngrok igual (puede quedar con 502 hasta que el frontend termine de levantar)."
}

# 5. Arrancar el tunel publico de ngrok hacia el frontend, si no esta corriendo ya.
# Dominio estatico (free tier) -> URL fija aunque ngrok se reinicie: https://moneyless-suppletory-aryana.ngrok-free.dev
$ngrokProc = Get-Process "ngrok" -ErrorAction SilentlyContinue
if ($ngrokProc) {
    Write-Log "ngrok ya esta corriendo (PID $($ngrokProc.Id -join ',')). No se vuelve a arrancar."
} else {
    Write-Log "Arrancando tunel ngrok -> https://$NgrokDomain ..."
    Start-Process -FilePath $NgrokExe `
        -ArgumentList @("http", "--url=https://$NgrokDomain", "80") `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir "ngrok.log") `
        -RedirectStandardError (Join-Path $LogDir "ngrok-error.log")
    Start-Sleep -Seconds 3
    $ngrokProc2 = Get-Process "ngrok" -ErrorAction SilentlyContinue
    if ($ngrokProc2) {
        Write-Log "ngrok arrancado (PID $($ngrokProc2.Id))."
    } else {
        Write-Log "ERROR: ngrok no parece haber arrancado. Revisar storage/logs/ngrok-error.log."
    }
}

Write-Log "=== Fin del proceso de arranque ==="
