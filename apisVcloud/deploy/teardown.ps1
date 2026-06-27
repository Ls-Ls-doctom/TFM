<#
.SYNOPSIS
    Elimina la infraestructura creada por deploy.ps1 (control de costes).

.DESCRIPTION
    Borra schedule, roles, cluster, task definitions, log group, repositorio ECR y,
    opcionalmente, el bucket S3 (con -DeleteBucket, que ademas borra los datos).

.EXAMPLE
    ./teardown.ps1 -Bucket iseu-datalake-ismael-2026
    ./teardown.ps1 -Bucket iseu-datalake-ismael-2026 -DeleteBucket
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $Bucket,
    [string] $Region       = "eu-west-1",
    [string] $Repository   = "iseu-pipeline",
    [string] $Cluster      = "iseu-cluster",
    [string] $Family       = "iseu-pipeline",
    [string] $LogGroup     = "/ecs/iseu-pipeline",
    [string] $ScheduleName = "iseu-monthly",
    [switch] $DeleteBucket
)

$ErrorActionPreference = "Continue"
function Try-Run([string]$desc, [scriptblock]$b) {
    Write-Host "-> $desc" -ForegroundColor Cyan
    try { & $b | Out-Null; Write-Host "   OK" -ForegroundColor Green }
    catch { Write-Host "   (omitido: $($_.Exception.Message))" -ForegroundColor DarkGray }
}

Try-Run "Borrar schedule mensual" { aws scheduler delete-schedule --name $ScheduleName --region $Region }
Try-Run "Quitar politica del rol Scheduler" { aws iam delete-role-policy --role-name "iseu-scheduler-role" --policy-name "iseu-run-task" }
Try-Run "Borrar rol Scheduler" { aws iam delete-role --role-name "iseu-scheduler-role" }

Try-Run "Quitar politica S3 del Task Role" { aws iam delete-role-policy --role-name "iseu-task-role" --policy-name "iseu-s3-datalake" }
Try-Run "Borrar Task Role" { aws iam delete-role --role-name "iseu-task-role" }

Try-Run "Desadjuntar politica del Execution Role" { aws iam detach-role-policy --role-name "iseu-execution-role" --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy" }
Try-Run "Quitar politica del secret AEMET" { aws iam delete-role-policy --role-name "iseu-execution-role" --policy-name "iseu-read-aemet-secret" }
Try-Run "Borrar Execution Role" { aws iam delete-role --role-name "iseu-execution-role" }

# Dar de baja todas las revisiones de la task definition
$revisions = aws ecs list-task-definitions --family-prefix $Family --region $Region --query "taskDefinitionArns[]" --output text
if ($revisions) {
    foreach ($arn in ($revisions -split "\s+")) {
        Try-Run "Deregister $arn" { aws ecs deregister-task-definition --task-definition $arn --region $Region }
    }
}

Try-Run "Borrar cluster ECS" { aws ecs delete-cluster --cluster $Cluster --region $Region }
Try-Run "Borrar log group" { aws logs delete-log-group --log-group-name $LogGroup --region $Region }
Try-Run "Borrar secret AEMET" { aws secretsmanager delete-secret --secret-id "iseu/aemet-api-key" --force-delete-without-recovery --region $Region }
Try-Run "Borrar imagenes ECR + repositorio" { aws ecr delete-repository --repository-name $Repository --force --region $Region }

if ($DeleteBucket) {
    Try-Run "Vaciar bucket S3" { aws s3 rm "s3://$Bucket" --recursive }
    Try-Run "Borrar bucket S3" { aws s3api delete-bucket --bucket $Bucket --region $Region }
} else {
    Write-Host "`nBucket s3://$Bucket conservado (usa -DeleteBucket para borrarlo y eliminar los datos)." -ForegroundColor Yellow
}

Write-Host "`nTeardown completado." -ForegroundColor Green
