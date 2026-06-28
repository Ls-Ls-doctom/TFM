# apisVcloud

Capa de ejecucion cloud para ISEU. No modifica los conectores locales de
`api_clients/intento 3`: los ejecuta dentro de un contenedor Fargate y sincroniza
Bronze, Silver, Gold y reportes con S3.

## Flujo

```text
EventBridge Scheduler -> ECS Fargate -> conectores locales -> S3
                                             |-> bronze/
                                             |-> silver/
                                             |-> gold/
                                             |-> reports/
                                             `-> errors/ si falla
```

La sincronizacion calcula SHA-256. Si un objeto remoto ya tiene el mismo hash,
no vuelve a subirlo y evita crear versiones duplicadas.

## Variables de entorno

| Variable | Obligatoria | Predeterminado | Uso |
|---|---:|---|---|
| `ISEU_BUCKET` | Si | - | Bucket del data lake |
| `AWS_REGION` | No | `eu-west-1` | Region AWS |
| `ISEU_MODE` | No | `full` | `full`, `collect` o `transform` |
| `ISEU_S3_PREFIX` | No | vacio | Prefijo adicional dentro del bucket |
| `ISEU_SINCE_YEAR` | No | `2010` | Antiguedad de recursos municipales |
| `ISEU_MUNICIPAL_MAX_RESOURCES` | No | `80` | Limite por ciudad |
| `ISEU_SKIP_MUNICIPAL_RESOURCES` | No | `false` | Omite descargas municipales pesadas |
| `ISEU_CONTINUE_ON_COLLECT_ERROR` | No | `true` | Permite fuentes parciales |
| `ISEU_DOWNLOAD_BRONZE` | No | `true` | Descarga Bronze antes de `transform` |
| `ISEU_BUILD_SQLITE` | No | `false` | Genera SQLite como artefacto adicional |
| `ISEU_UPLOAD_WORKERS` | No | `8` | Subidas S3 paralelas |

Las credenciales no se guardan en variables: en ECS se obtienen del Task Role.
Las claves de fuentes como AEMET deben inyectarse desde Secrets Manager.

## Construccion local

Ejecutar desde la raiz del repositorio:

```powershell
docker build -f apisVcloud/Dockerfile -t iseu-pipeline:local .
```

Prueba usando las credenciales AWS del perfil local:

```powershell
docker run --rm `
  -e ISEU_BUCKET=REPLACE_BUCKET `
  -e AWS_REGION=eu-west-1 `
  -v "$env:USERPROFILE\.aws:/root/.aws:ro" `
  iseu-pipeline:local --mode collect
```

## Publicacion en ECR

```powershell
$region = "eu-west-1"
$repository = "iseu-pipeline"
$account = aws sts get-caller-identity --query Account --output text

aws ecr create-repository --repository-name $repository --region $region
aws ecr get-login-password --region $region |
  docker login --username AWS --password-stdin "$account.dkr.ecr.$region.amazonaws.com"

docker tag iseu-pipeline:local "$account.dkr.ecr.$region.amazonaws.com/${repository}:latest"
docker push "$account.dkr.ecr.$region.amazonaws.com/${repository}:latest"
```

## Configuracion Fargate inicial

- CPU: `1 vCPU`.
- Memoria: `4 GB`.
- Almacenamiento efimero: `20 GB` (incluido por defecto).
- Comando: `--mode full`.
- Red: subnet publica, IP publica y Security Group sin reglas de entrada.
- Task Role: copiar `task-role-policy.json` y sustituir `REPLACE_BUCKET`.
- Execution Role: permisos administrados para descargar ECR y escribir CloudWatch Logs.

La subnet publica evita mantener un NAT Gateway solo para una tarea mensual. El
contenedor no abre puertos ni necesita trafico de entrada.

## Programacion

Crear un EventBridge Scheduler con:

- Destino: `ECS RunTask`.
- Launch type: Fargate.
- Zona horaria: `Europe/Madrid`.
- Ejemplo: dia 1 de cada mes a las 07:00.
- Reintentos: 2.
- DLQ: una cola SQS para invocaciones no entregadas.

## Modos separados

Se puede usar una tarea para descargar y otra para transformar:

```text
collect   -> ejecuta APIs y sube bronze/
transform -> descarga bronze/, genera silver/ y gold/
full      -> ejecuta ambas fases en la misma tarea
```

La fase `publish_parquet` es exclusiva de cloud y genera:

```text
silver/athena/**/*.parquet
gold/athena/indicators/data.parquet
gold/athena/catalog/indicator_catalog.parquet
```

Gold se publica inicialmente en un solo fichero porque el volumen actual es
pequeno. Esto evita el problema de muchos Parquet diminutos. Cuando Gold crezca
por encima de varios GB se puede particionar por `year` y `month`.

El crawler de Glue debe apuntar a `silver/athena/` y `gold/athena/`, no a los
CSV originales. SQLite se puede activar con `ISEU_BUILD_SQLITE=true`, pero no es
necesario cuando las consultas se ejecutan con Athena.

La infraestructura de consulta está definida en `athena-stack.yaml` e incluye
Glue Data Catalog, el workgroup Athena, Lambda, API Gateway, roles IAM y cuota.
La web desplegada en Vercel usa Google Gemini para generar SQL `SELECT`; Lambda
valida y limita la sentencia antes de enviarla a Athena. Los endpoints públicos
no aceptan escrituras ni acceso directo a otras tablas.

Para una primera prueba se recomienda `full`. Al introducir Step Functions,
separar `collect` y `transform` permite reintentar solo la fase que falla.

## Estimacion orientativa en Irlanda

Sin SageMaker y con una ejecucion mensual de dos horas:

- Fargate 1 vCPU / 4 GB: aproximadamente USD 0.12 por ejecucion.
- S3 Standard para 1.4 GB: aproximadamente USD 0.03 al mes, sin contar versiones.
- Athena con Parquet y 100 consultas pequenas: aproximadamente USD 0.01.
- ECR, CloudWatch, SQS y EventBridge: normalmente menos de USD 0.50.
- Total orientativo de datos y automatizacion: USD 0.25-1.00 al mes.

El endpoint SageMaker es el componente costoso en `eu-west-1`:

- `ml.g4dn.xlarge`: USD 0.821/h, unos USD 8.21 por 10 horas o USD 599/mes continuo.
- `ml.g5.xlarge`: USD 1.57/h, unos USD 15.70 por 10 horas o USD 1,146/mes continuo.

Para el TFM conviene crear el endpoint solo durante pruebas/demos, automatizar su
eliminacion posterior o usar un modelo pequeno compatible con inferencia serverless.
Las cifras no incluyen IVA, transferencia de datos ni un NAT Gateway.
