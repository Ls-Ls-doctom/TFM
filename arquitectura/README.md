# Arquitectura cloud ISEU+

## Decisión vigente

La arquitectura objetivo prioriza bajo coste y ejecución bajo demanda. La web y
el chatbot se mantienen en Vercel. AWS se utiliza para actualizar, almacenar y
consultar los datos analíticos.

```text
Fuentes públicas
  -> EventBridge Scheduler
  -> ECS Fargate (pipeline Python)
  -> S3 Bronze / Silver / Gold Parquet
  -> Glue Data Catalog
  -> Athena
  -> Lambda + API Gateway
  -> Vercel (dashboard y chat)
```

El chatbot utiliza Google Gemini 2.5 Flash. Gemini genera una sentencia SQL de
solo lectura; una Lambda la valida, restringe la consulta a la tabla Gold y
fuerza un máximo de 100 filas antes de ejecutarla en Athena. Con los resultados,
Gemini redacta la respuesta final. La consulta de datos no entrega credenciales
de AWS al navegador: Vercel llama a API Gateway desde sus funciones Python.

## Componentes descartados

- Amazon Redshift: sustituido por Athena sobre Parquet en S3.
- AWS Glue como motor ETL: la transformación se ejecuta con Python en Fargate;
  Glue se utiliza únicamente como catálogo y crawler.
- AWS Lambda para la ingesta completa: el volumen y los conectores existentes
  encajan mejor en una tarea de Fargate.
- AWS IoT Greengrass: no aporta valor al flujo web y analítico del proyecto.

## Estado comprobado el 28 de junio de 2026

- Bucket S3 `iseu-datalake-ismael-2026` en `eu-west-1` con Bronze, Silver,
  Gold, reportes y salidas Parquet para Athena.
- Repositorio ECR `iseu-pipeline` con imagen publicada.
- Cluster ECS `iseu-cluster` y task definition `iseu-pipeline:1`.
- Scheduler `iseu-monthly`, día 1 a las 07:00 en `Europe/Madrid`.
- Logs en CloudWatch con retención de 90 días.
- Bloqueo de acceso público y cifrado AES-256 activos en S3.

## Infraestructura desplegada

- Stack CloudFormation `iseu-athena-web`.
- Glue Database `iseu` y crawler mensual `iseu-parquet-crawler`.
- Workgroup Athena `iseu`, cifrado y limitado a 50 MB por consulta.
- Lambda `iseu-athena-query` y API Gateway protegida mediante API key y cuota.
- API con operaciones `dashboard`, `catalog`, `indicators` y `sql`.
- Resultados temporales de Athena eliminados por S3 tras siete días.
- Vercel `project-zcvjr` conectado a Gemini y Athena.
- Producción: `https://project-zcvjr.vercel.app`.

## Seguridad

- ECS, Scheduler y Lambda deben usar roles IAM específicos y de mínimo permiso.
- Las claves del usuario administrador no deben almacenarse en Vercel, imágenes
  Docker ni archivos versionados.
- Las consultas aceptadas por Lambda deben usar plantillas o parámetros; no se
  ejecuta SQL arbitrario enviado directamente desde el navegador. El endpoint
  de modelo admite exclusivamente `SELECT` sobre la tabla lógica `indicators`.

## Artefactos

- `Arquitectura AWS - Athena y Vercel.svg`: fuente editable del diagrama.
- `Arquitectura AWS - Athena y Vercel.png`: versión raster para la memoria.
- `Arquitecturas de datos.pdf`: versión PDF actualizada.
- `Flujos de datos.png`: modelo lógico de datos del lakehouse.
