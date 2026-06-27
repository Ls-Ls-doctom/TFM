<#
.SYNOPSIS
    Despliegue 100% automatico del pipeline ISEU en AWS (Fargate + EventBridge Scheduler).

.DESCRIPTION
    Crea/actualiza, de forma idempotente, toda la infraestructura necesaria para que el
    pipeline ISEU se ejecute SOLO una vez al mes y deje Bronze/Silver/Gold en S3:

        1.  Bucket S3 (data lake)            -> almacenamiento
        2.  Repositorio ECR                  -> imagen del contenedor
        3.  Build + push de la imagen Docker -> empaqueta el pipeline
        4.  Log group de CloudWatch          -> logs de cada ejecucion
        5.  (Opcional) Secret de AEMET       -> Secrets Manager
        6.  Task Role + Execution Role (IAM) -> permisos de la tarea
        7.  Cluster ECS                      -> donde corre Fargate
        8.  Task Definition (1 vCPU / 4 GB)  -> --mode full
        9.  Rol del Scheduler (IAM)          -> permite lanzar la tarea
        10. EventBridge Schedule (cron)      -> dispara la tarea cada mes

    Tras ejecutarlo una vez, NO hay que volver a tocar nada: la tarea se lanza sola.

.PARAMETER Bucket
    Nombre del bucket S3 (debe ser unico en TODO AWS). Obligatorio.

.PARAMETER Region
    Region AWS. Por defecto eu-west-1 (Irlanda).

.PARAMETER AemetApiKey
    (Opcional) Clave de AEMET OpenData. Si se indica, se guarda en Secrets Manager
    y se inyecta en la tarea como AEMET_API_KEY. Si se omite, AEMET se salta.

.PARAMETER ScheduleCron
    Expresion cron del Scheduler. Por defecto: dia 1 de cada mes a las 07:00.

.PARAMETER Timezone
    Zona horaria del cron. Por defecto Europe/Madrid.

.EXAMPLE
    ./deploy.ps1 -Bucket iseu-datalake-ismael-2026

.EXAMPLE
    ./deploy.ps1 -Bucket iseu-datalake-ismael-2026 -Region eu-west-1 -AemetApiKey "eyJhbGci..."
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $Bucket,
    [string] $Region        = "eu-west-1",
    [string] $AemetApiKey   = "",
    [string] $Repository    = "iseu-pipeline",
    [string] $Cluster       = "iseu-cluster",
    [string] $Family        = "iseu-pipeline",
    [string] $LogGroup      = "/ecs/iseu-pipeline",
    [string] $ScheduleName  = "iseu-monthly",
    [string] $ScheduleCron  = "cron(0 7 1 * ? *)",
    [string] $Timezone      = "Europe/Madrid"
)

$ErrorActionPreference = "Stop"

function Step([string]$msg) { Write-Host "`n==== $msg ====" -ForegroundColor Cyan }
function Info([string]$msg) { Write-Host "    $msg" -ForegroundColor Gray }
function Ok([string]$msg)   { Write-Host "    OK: $msg" -ForegroundColor Green }

# Ejecuta aws basandose en el codigo de salida (robusto en PowerShell 5.1) y
# tolera el error "ya existe" para que el script sea reejecutable.
function AwsTry([string]$description, [scriptblock]$block) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = (& $block 2>&1 | Out-String)
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($code -eq 0) { Ok $description; return }
    if ($output -match "already exists|AlreadyExists|EntityAlreadyExists|BucketAlreadyOwnedByYou|ResourceConflict|already attached|NoSuchEntity.*delete") {
        Info "$description ya existia (se mantiene)."; return
    }
    throw "Fallo en: $description`n$output"
}

# ---------------------------------------------------------------------------
# 0. Preparacion y comprobaciones previas
# ---------------------------------------------------------------------------
Step "0. Comprobaciones previas"

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw "AWS CLI no esta instalado. Instala: https://aws.amazon.com/cli/"
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker no esta instalado o no esta en PATH. Instala Docker Desktop y abrelo."
}

$Account = (aws sts get-caller-identity --query Account --output text).Trim()
if (-not $Account -or $Account -eq "None") {
    throw "No hay credenciales AWS validas. Ejecuta 'aws configure' primero."
}
Ok "Cuenta AWS: $Account  |  Region: $Region"

# Raiz del repo = dos niveles por encima de este script (apisVcloud/deploy -> raiz)
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Info "Raiz del repo: $RepoRoot"
if (-not (Test-Path (Join-Path $RepoRoot "apisVcloud\Dockerfile"))) {
    throw "No encuentro apisVcloud/Dockerfile en $RepoRoot. Ejecuta el script desde el repo."
}

$EcrUri   = "$Account.dkr.ecr.$Region.amazonaws.com"
$ImageUri = "$EcrUri/${Repository}:latest"
$Work     = Join-Path ([System.IO.Path]::GetTempPath()) "iseu-deploy"
New-Item -ItemType Directory -Force -Path $Work | Out-Null

function WriteJson($obj, $name) {
    $path = Join-Path $Work $name
    ($obj | ConvertTo-Json -Depth 20) | Out-File -FilePath $path -Encoding ascii
    return $path
}

# ---------------------------------------------------------------------------
# 1. Bucket S3
# ---------------------------------------------------------------------------
Step "1. Bucket S3 ($Bucket)"
AwsTry "crear bucket" {
    if ($Region -eq "us-east-1") {
        aws s3api create-bucket --bucket $Bucket --region $Region
    } else {
        aws s3api create-bucket --bucket $Bucket --region $Region `
            --create-bucket-configuration "LocationConstraint=$Region"
    }
}
AwsTry "bloquear acceso publico" {
    aws s3api put-public-access-block --bucket $Bucket `
        --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
}
$encConfig = @{ Rules = @(@{ ApplyServerSideEncryptionByDefault = @{ SSEAlgorithm = "AES256" } }) }
$encFile = WriteJson $encConfig "encryption.json"
AwsTry "cifrado por defecto (AES256)" {
    aws s3api put-bucket-encryption --bucket $Bucket --server-side-encryption-configuration "file://$encFile"
}

# ---------------------------------------------------------------------------
# 2. Repositorio ECR
# ---------------------------------------------------------------------------
Step "2. Repositorio ECR ($Repository)"
AwsTry "crear repositorio" { aws ecr create-repository --repository-name $Repository --region $Region }

# ---------------------------------------------------------------------------
# 3. Build + push de la imagen Docker
# ---------------------------------------------------------------------------
Step "3. Construir y subir imagen Docker"
Info "Login en ECR..."
$pw = aws ecr get-login-password --region $Region
docker login --username AWS --password $pw $EcrUri | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Fallo el login en ECR." }
Ok "login ECR"

Info "docker build (puede tardar la primera vez)..."
Push-Location $RepoRoot
try {
    docker build -f "apisVcloud/Dockerfile" -t "${Repository}:latest" .
    if ($LASTEXITCODE -ne 0) { throw "docker build fallo." }
    docker tag "${Repository}:latest" $ImageUri
    docker push $ImageUri
    if ($LASTEXITCODE -ne 0) { throw "docker push fallo." }
} finally { Pop-Location }
Ok "imagen subida: $ImageUri"

# ---------------------------------------------------------------------------
# 4. Log group CloudWatch
# ---------------------------------------------------------------------------
Step "4. Log group CloudWatch ($LogGroup)"
AwsTry "crear log group" { aws logs create-log-group --log-group-name $LogGroup --region $Region }
AwsTry "retencion 90 dias" { aws logs put-retention-policy --log-group-name $LogGroup --retention-in-days 90 --region $Region }

# ---------------------------------------------------------------------------
# 5. Secret de AEMET (opcional)
# ---------------------------------------------------------------------------
$AemetSecretArn = ""
if ($AemetApiKey -ne "") {
    Step "5. Secret AEMET (Secrets Manager)"
    try {
        $AemetSecretArn = (aws secretsmanager create-secret --name "iseu/aemet-api-key" `
            --secret-string $AemetApiKey --region $Region --query ARN --output text).Trim()
        Ok "secret creado"
    } catch {
        $AemetSecretArn = (aws secretsmanager put-secret-value --secret-id "iseu/aemet-api-key" `
            --secret-string $AemetApiKey --region $Region --query ARN --output text).Trim()
        Info "secret ya existia: valor actualizado"
    }
} else {
    Step "5. Secret AEMET -> omitido (AEMET se saltara en la ejecucion)"
}

# ---------------------------------------------------------------------------
# 6. Roles IAM (Task Role + Execution Role)
# ---------------------------------------------------------------------------
Step "6. Roles IAM"

$EcsTrust = @{
    Version   = "2012-10-17"
    Statement = @(@{ Effect = "Allow"; Principal = @{ Service = "ecs-tasks.amazonaws.com" }; Action = "sts:AssumeRole" })
}
$ecsTrustFile = WriteJson $EcsTrust "ecs-trust.json"

$TaskRoleName = "iseu-task-role"
$ExecRoleName = "iseu-execution-role"

AwsTry "crear Task Role" { aws iam create-role --role-name $TaskRoleName --assume-role-policy-document "file://$ecsTrustFile" }
AwsTry "crear Execution Role" { aws iam create-role --role-name $ExecRoleName --assume-role-policy-document "file://$ecsTrustFile" }

# Politica del Task Role: acceso S3 al data lake (a partir de la plantilla del repo).
$taskPolicyTemplate = Get-Content (Join-Path $PSScriptRoot "..\task-role-policy.json") -Raw
$taskPolicy = $taskPolicyTemplate.Replace("REPLACE_BUCKET", $Bucket)
$taskPolicyFile = Join-Path $Work "task-role-policy.json"
$taskPolicy | Out-File -FilePath $taskPolicyFile -Encoding ascii
AwsTry "politica S3 del Task Role" {
    aws iam put-role-policy --role-name $TaskRoleName --policy-name "iseu-s3-datalake" --policy-document "file://$taskPolicyFile"
}

# Execution Role: permiso gestionado para tirar de ECR y escribir logs.
AwsTry "adjuntar AmazonECSTaskExecutionRolePolicy" {
    aws iam attach-role-policy --role-name $ExecRoleName `
        --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Si hay secret AEMET, el Execution Role debe poder leerlo.
if ($AemetSecretArn -ne "") {
    $secretPolicy = @{
        Version   = "2012-10-17"
        Statement = @(@{ Effect = "Allow"; Action = "secretsmanager:GetSecretValue"; Resource = $AemetSecretArn })
    }
    $secretPolicyFile = WriteJson $secretPolicy "secret-policy.json"
    AwsTry "permiso de lectura del secret AEMET" {
        aws iam put-role-policy --role-name $ExecRoleName --policy-name "iseu-read-aemet-secret" --policy-document "file://$secretPolicyFile"
    }
}

$TaskRoleArn = (aws iam get-role --role-name $TaskRoleName --query "Role.Arn" --output text).Trim()
$ExecRoleArn = (aws iam get-role --role-name $ExecRoleName --query "Role.Arn" --output text).Trim()
Ok "Task Role: $TaskRoleArn"
Ok "Exec Role: $ExecRoleArn"
Info "Esperando propagacion IAM (10s)..."
Start-Sleep -Seconds 10

# ---------------------------------------------------------------------------
# 7. Cluster ECS
# ---------------------------------------------------------------------------
Step "7. Cluster ECS ($Cluster)"
AwsTry "crear cluster" { aws ecs create-cluster --cluster-name $Cluster --region $Region }

# ---------------------------------------------------------------------------
# 8. Task Definition
# ---------------------------------------------------------------------------
Step "8. Task Definition ($Family)"

$container = @{
    name        = "iseu-pipeline"
    image       = $ImageUri
    essential   = $true
    command     = @("--mode", "full")
    environment = @(
        @{ name = "ISEU_BUCKET"; value = $Bucket },
        @{ name = "AWS_REGION";  value = $Region }
    )
    logConfiguration = @{
        logDriver = "awslogs"
        options   = @{
            "awslogs-group"         = $LogGroup
            "awslogs-region"        = $Region
            "awslogs-stream-prefix" = "iseu"
        }
    }
}
if ($AemetSecretArn -ne "") {
    $container["secrets"] = @(@{ name = "AEMET_API_KEY"; valueFrom = $AemetSecretArn })
}

$taskDef = @{
    family                  = $Family
    networkMode             = "awsvpc"
    requiresCompatibilities = @("FARGATE")
    cpu                     = "1024"
    memory                  = "4096"
    runtimePlatform         = @{ operatingSystemFamily = "LINUX"; cpuArchitecture = "X86_64" }
    executionRoleArn        = $ExecRoleArn
    taskRoleArn             = $TaskRoleArn
    containerDefinitions    = @($container)
}
$taskDefFile = WriteJson $taskDef "task-definition.json"
$TaskDefArn = (aws ecs register-task-definition --cli-input-json "file://$taskDefFile" --region $Region `
    --query "taskDefinition.taskDefinitionArn" --output text).Trim()
Ok "Task Definition: $TaskDefArn"

# ---------------------------------------------------------------------------
# 9. Red por defecto (subnets + security group)
# ---------------------------------------------------------------------------
Step "9. Red (VPC por defecto)"
$VpcId = (aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text --region $Region).Trim()
if (-not $VpcId -or $VpcId -eq "None") { throw "No hay VPC por defecto en $Region. Crea una o indica subnets manualmente." }
$SubnetList = (aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VpcId" --query "Subnets[].SubnetId" --output text --region $Region).Trim() -split "\s+"
$SgId = (aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VpcId" "Name=group-name,Values=default" --query "SecurityGroups[0].GroupId" --output text --region $Region).Trim()
Ok "VPC $VpcId | subnets: $($SubnetList -join ', ') | SG: $SgId"

# ---------------------------------------------------------------------------
# 10. Rol del Scheduler + Schedule mensual
# ---------------------------------------------------------------------------
Step "10. EventBridge Scheduler"

$SchedTrust = @{
    Version   = "2012-10-17"
    Statement = @(@{ Effect = "Allow"; Principal = @{ Service = "scheduler.amazonaws.com" }; Action = "sts:AssumeRole" })
}
$schedTrustFile = WriteJson $SchedTrust "scheduler-trust.json"
$SchedRoleName = "iseu-scheduler-role"
AwsTry "crear rol del Scheduler" { aws iam create-role --role-name $SchedRoleName --assume-role-policy-document "file://$schedTrustFile" }

$ClusterArn = (aws ecs describe-clusters --clusters $Cluster --query "clusters[0].clusterArn" --output text --region $Region).Trim()
$SchedPolicy = @{
    Version   = "2012-10-17"
    Statement = @(
        @{ Effect = "Allow"; Action = "ecs:RunTask"; Resource = "*" },
        @{ Effect = "Allow"; Action = "iam:PassRole"; Resource = @($TaskRoleArn, $ExecRoleArn) }
    )
}
$schedPolicyFile = WriteJson $SchedPolicy "scheduler-policy.json"
AwsTry "politica del rol Scheduler" {
    aws iam put-role-policy --role-name $SchedRoleName --policy-name "iseu-run-task" --policy-document "file://$schedPolicyFile"
}
$SchedRoleArn = (aws iam get-role --role-name $SchedRoleName --query "Role.Arn" --output text).Trim()
Start-Sleep -Seconds 8

# Target del schedule: ECS RunTask en Fargate, subnet publica con IP publica.
$target = @{
    Arn        = $ClusterArn
    RoleArn    = $SchedRoleArn
    EcsParameters = @{
        TaskDefinitionArn    = $TaskDefArn
        TaskCount            = 1
        LaunchType           = "FARGATE"
        NetworkConfiguration = @{
            awsvpcConfiguration = @{
                Subnets        = $SubnetList
                SecurityGroups = @($SgId)
                AssignPublicIp = "ENABLED"
            }
        }
    }
    RetryPolicy = @{ MaximumRetryAttempts = 2 }
}
$targetFile = WriteJson $target "scheduler-target.json"

aws scheduler get-schedule --name $ScheduleName --region $Region 2>$null | Out-Null
$exists = ($LASTEXITCODE -eq 0)

if ($exists) {
    aws scheduler update-schedule --name $ScheduleName --region $Region `
        --schedule-expression $ScheduleCron --schedule-expression-timezone $Timezone `
        --flexible-time-window "Mode=OFF" --target "file://$targetFile" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Fallo al actualizar el schedule." }
    Ok "schedule actualizado"
} else {
    aws scheduler create-schedule --name $ScheduleName --region $Region `
        --schedule-expression $ScheduleCron --schedule-expression-timezone $Timezone `
        --flexible-time-window "Mode=OFF" --target "file://$targetFile" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Fallo al crear el schedule." }
    Ok "schedule creado"
}

# ---------------------------------------------------------------------------
# Resumen
# ---------------------------------------------------------------------------
Step "DESPLIEGUE COMPLETADO"
Write-Host @"
  Bucket S3 .......... s3://$Bucket
  Imagen ............. $ImageUri
  Cluster ............ $Cluster
  Task Definition .... $TaskDefArn
  Schedule ........... $ScheduleName  ($ScheduleCron, $Timezone)
  AEMET .............. $(if ($AemetSecretArn) { 'activada (Secrets Manager)' } else { 'omitida' })

  El pipeline se ejecutara SOLO segun el cron. No hay que hacer nada mas.

  Probar AHORA sin esperar al cron (lanza una ejecucion manual):
    aws ecs run-task --cluster $Cluster --launch-type FARGATE ``
      --task-definition $Family --region $Region ``
      --network-configuration "awsvpcConfiguration={subnets=[$($SubnetList -join ',')],securityGroups=[$SgId],assignPublicIp=ENABLED}"

  Ver logs:    aws logs tail $LogGroup --follow --region $Region
  Ver datos:   aws s3 ls s3://$Bucket/ --recursive
"@ -ForegroundColor Green
