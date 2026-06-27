# Despliegue automatico de ISEU en AWS

Deja el pipeline ISEU ejecutandose **100% automatico, una vez al mes**, sin tu PC encendido.
Arquitectura: **EventBridge Scheduler -> ECS Fargate -> S3** (consultable luego con Athena).

```text
EventBridge Scheduler (cron mensual, Europe/Madrid)
        |
        v
   ECS RunTask (Fargate, --mode full)   <- imagen en ECR
        |
        v
   APIS -> bronze -> silver -> gold -> parquet
        |
        v
   S3 (bronze/ silver/ gold/ reports/ errors/)
```

## Requisitos previos (esto lo haces tu, una sola vez)

Estos pasos son humanos y no se pueden automatizar desde el repo:

1. **Cuenta AWS** activa (con metodo de pago).
2. **AWS CLI** instalado: https://aws.amazon.com/cli/
3. **Docker Desktop** instalado y **abierto** (el daemon debe estar corriendo).
4. Credenciales configuradas:
   ```powershell
   aws configure
   ```
5. Elige un **nombre de bucket unico en todo AWS** (p. ej. `iseu-datalake-tunombre-2026`).
6. (Opcional) Tu **clave de AEMET OpenData**. Si no la tienes, AEMET se omite sin romper nada.

## Despliegue (1 comando)

Desde esta carpeta (`apisVcloud/deploy`):

```powershell
# Minimo (sin AEMET)
./deploy.ps1 -Bucket iseu-datalake-tunombre-2026

# Con AEMET y region explicita
./deploy.ps1 -Bucket iseu-datalake-tunombre-2026 -Region eu-west-1 -AemetApiKey "TU_CLAVE_AEMET"
```

El script es **idempotente**: si algo falla a mitad, puedes volver a lanzarlo sin duplicar recursos.
Crea, en orden: bucket S3, repositorio ECR, imagen Docker, log group, (secret AEMET), roles IAM,
cluster ECS, task definition, rol del Scheduler y el schedule mensual.

Cuando termina, **no hay que hacer nada mas**: la tarea se lanza sola el dia 1 de cada mes a las 07:00 (Europe/Madrid).

## Cambiar la frecuencia

Por defecto: dia 1 de cada mes a las 07:00. Para otra cadencia, pasa `-ScheduleCron`:

| Cuando | Expresion |
|---|---|
| Dia 1 de cada mes, 07:00 (por defecto) | `cron(0 7 1 * ? *)` |
| Dia 15 de cada mes, 03:00 | `cron(0 3 15 * ? *)` |
| Cada lunes, 06:00 | `cron(0 6 ? * MON *)` |
| Cada trimestre (ene/abr/jul/oct dia 1) | `cron(0 7 1 1,4,7,10 ? *)` |

## Probar sin esperar al cron

El propio `deploy.ps1` imprime al final el comando `aws ecs run-task` listo para lanzar una ejecucion manual.
Tambien puedes ver el progreso:

```powershell
aws logs tail /ecs/iseu-pipeline --follow --region eu-west-1   # logs en vivo
aws s3 ls s3://TU_BUCKET/ --recursive                          # datos generados
```

Cada ejecucion deja un informe en `s3://TU_BUCKET/reports/cloud_runs/` y, si falla, el detalle en `errors/`.

## Consultar los datos con Athena (opcional)

1. Crea un **Glue Crawler** apuntando a `s3://TU_BUCKET/silver/athena/` y `s3://TU_BUCKET/gold/athena/`.
2. Ejecutalo para que registre las tablas Parquet.
3. Consulta desde Athena con SQL estandar.

## Coste orientativo

- Fargate (1 vCPU / 4 GB, ~2 h/mes): **~USD 0,12 / ejecucion**.
- S3 (~1,4 GB): **~USD 0,03 / mes**.
- ECR + CloudWatch + EventBridge: normalmente **< USD 0,50 / mes**.

Total aproximado: **USD 0,25 - 1,00 / mes**. (SageMaker, si se usa para inferencia, va aparte y es lo caro.)

## Borrar todo (control de costes)

```powershell
./teardown.ps1 -Bucket iseu-datalake-tunombre-2026                 # conserva el bucket/datos
./teardown.ps1 -Bucket iseu-datalake-tunombre-2026 -DeleteBucket   # borra TAMBIEN datos y bucket
```

## Resolucion de problemas

| Sintoma | Causa probable | Solucion |
|---|---|---|
| `docker build fallo` | Docker Desktop cerrado | Abre Docker Desktop y reintenta. |
| `No hay credenciales AWS validas` | Falta `aws configure` | Configura credenciales. |
| `No hay VPC por defecto` | Cuenta sin VPC default | Crea una VPC default o edita el script con tus subnets. |
| AEMET no descarga datos | Sin `AEMET_API_KEY` | Relanza con `-AemetApiKey`. Es opcional. |
| La tarea falla en una fuente | API externa caida | `ISEU_CONTINUE_ON_COLLECT_ERROR=true` deja seguir; revisa `errors/`. |
