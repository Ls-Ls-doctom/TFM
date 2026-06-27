<#
.SYNOPSIS
    Comprueba que todo esta listo ANTES de ejecutar deploy.ps1.
    No instala ni crea nada: solo verifica.
#>

$ok = $true
function Check([string]$name, [bool]$pass, [string]$hint) {
    if ($pass) { Write-Host ("  [OK]   {0}" -f $name) -ForegroundColor Green }
    else { Write-Host ("  [FALTA] {0}  ->  {1}" -f $name, $hint) -ForegroundColor Yellow; $script:ok = $false }
}

Write-Host "`nComprobando requisitos para el despliegue ISEU...`n" -ForegroundColor Cyan

# AWS CLI
$hasAws = [bool](Get-Command aws -ErrorAction SilentlyContinue)
Check "AWS CLI instalado" $hasAws "Instala: winget install Amazon.AWSCLI"

# Credenciales AWS
$creds = $false
if ($hasAws) {
    try { $id = aws sts get-caller-identity --query Account --output text 2>$null; if ($id -and $id -ne "None") { $creds = $true } } catch {}
}
Check "Credenciales AWS configuradas" $creds "Ejecuta: aws configure"

# Docker instalado
$hasDocker = [bool](Get-Command docker -ErrorAction SilentlyContinue)
Check "Docker instalado" $hasDocker "Instala Docker Desktop"

# Docker daemon corriendo
$dockerUp = $false
if ($hasDocker) {
    try { docker info 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { $dockerUp = $true } } catch {}
}
Check "Docker en marcha (engine running)" $dockerUp "Abre Docker Desktop y espera a 'Engine running'"

# WSL
$wslOk = $false
try { wsl --status 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { $wslOk = $true } } catch {}
Check "WSL2 disponible" $wslOk "Como admin: wsl --install  (y reinicia)"

Write-Host ""
if ($ok) { Write-Host "TODO LISTO. Puedes ejecutar: ./deploy.ps1 -Bucket TU_BUCKET`n" -ForegroundColor Green }
else { Write-Host "Faltan requisitos (ver arriba). Resuelvelos y vuelve a ejecutar este check.`n" -ForegroundColor Yellow }
