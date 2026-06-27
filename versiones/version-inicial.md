# Version inicial del repositorio TFM

Fecha de lectura: 2026-06-27

## Proposito del repositorio

Este repositorio contiene el Trabajo Fin de Master orientado a construir un sistema ISEU de integracion, analisis y consulta de indicadores urbanos y socioeconomicos. El proyecto combina conectores de datos publicos, pipeline Bronze/Silver/Gold, base SQLite para consulta, interfaz web, API ligera para Vercel, validaciones, analisis exploratorio y documentacion academica.

## Estado versionado de partida

- Rama actual: `main`.
- Remoto GitHub: `origin` -> `https://github.com/Ls-Ls-doctom/TFM.git`.
- Archivos ya rastreados antes de esta version: 119.
- Archivos nuevos detectados para subir: capa `apisVcloud/` y este documento de versionado.

## Lectura del repositorio actual

### Aplicacion y API web

- `api/`: endpoints Python desplegables en Vercel.
  - `chat.py`: recibe mensajes, compacta historial, construye traza y llama al motor local/servicio configurado.
  - `dashboard.py`: expone el payload del dashboard.
  - `health.py`: endpoint simple de disponibilidad.
- `pag_web/`: interfaz HTML estatica del dashboard y chatbot, con recursos en `Assets/`.
- `vercel.json`: define builds para `api/*.py`, contenido estatico de `pag_web/` y rutas publicas.

### Motor local y analisis

- `pag_web/LMlocal/`: configuracion y servidor local del modelo conversacional.
- `pag_web/Procesos/analysis_engine.py`: activa analisis bajo demanda segun la pregunta y consulta series de empleo, IPC, energia y poblacion.
- `pag_web/Procesos/sql_data.py`: capa de acceso a datos SQLite para las consultas del chatbot y del dashboard.
- `pag_web/Procesos/semantic_dictionary.json`: diccionario semantico para relacionar preguntas con indicadores y fuentes.

### Pipeline de datos

- `api_clients/intento 3/APIS/`: conectores y descargas desde fuentes externas como AEMET, catalogos, INE, MITMA, SEPE y recursos municipales.
- `api_clients/intento 3/pipeline/`: scripts reproducibles del flujo Bronze -> Silver -> Gold -> SQLite.
- `api_clients/intento 3/run_pipeline.py`: orquestador local del pipeline completo o reutilizando Bronze existente.
- `api_clients/intento 3/reports/`: reportes de inventario, limpieza, Gold, ejecucion y manifiestos.
- `api_clients/intento 3/data_lake/`: capas Bronze, Silver y Gold generadas; estan ignoradas por Git segun la regla local para evitar versionar datos pesados regenerables.

### Diagnostico, EDA y validacion

- `diagnostico_datos.py`: diagnostico de flujo de datos raw, limpios y SQLite.
- `EDA/salidas/`: salidas de analisis exploratorio, calidad de datasets, correlaciones, inventarios y oportunidades SQL.
- `datos de validacion/`: paginas y CSV de preguntas usadas para validar el sistema.
- `arquitectura/` y `esquemas de datos/`: material de apoyo, esquemas y documentacion de arquitectura.

### Informe academico

- `LaTeX Informe/`: memoria en LaTeX, portada, capitulos y figuras del informe.
- `Articulos/`: material documental complementario.
- `plantillas/` y `tmp/`: recursos auxiliares del trabajo.

## Nuevos archivos incluidos en esta version

La carpeta `apisVcloud/` introduce una capa de ejecucion cloud para llevar el pipeline a AWS sin modificar los conectores locales.

- `apisVcloud/cloud_pipeline.py`: orquesta la ejecucion en contenedor, permite modos `full`, `collect` y `transform`, sincroniza capas con S3 y registra errores/reportes.
- `apisVcloud/s3_storage.py`: cliente S3 con calculo SHA-256, subida idempotente, descarga por prefijo, cifrado server-side y metadatos de ejecucion.
- `apisVcloud/settings.py`: configuracion por variables de entorno, validacion de bucket, modo y rutas del pipeline.
- `apisVcloud/publish_cloud.py`: genera salidas Parquet comprimidas para Athena desde Silver y Gold.
- `apisVcloud/Dockerfile`: imagen Python 3.12 slim para ejecutar el pipeline en Fargate.
- `apisVcloud/Dockerfile.dockerignore`: exclusiones para el contexto de Docker.
- `apisVcloud/requirements.txt`: dependencias cloud (`boto3`, `pandas`, `pyarrow`).
- `apisVcloud/task-role-policy.json`: plantilla IAM con placeholder `REPLACE_BUCKET` para S3.
- `apisVcloud/README.md`: documentacion de flujo, variables, build local, publicacion ECR, Fargate, EventBridge y costes estimados.
- `apisVcloud/__init__.py`: inicializa el paquete Python.

## Control de versiones

Esta version inicial documenta la linea base del repositorio antes de subir la capa cloud. A partir de aqui, las siguientes versiones deberian crear nuevos documentos en esta carpeta con:

- Fecha y rama.
- Resumen funcional del cambio.
- Archivos agregados, modificados o eliminados.
- Impacto en datos, despliegue o ejecucion.
- Validaciones realizadas.
- Riesgos o tareas pendientes.

## Validaciones realizadas para esta version

- Lectura del estado Git y remoto configurado.
- Inventario general del repositorio.
- Lectura de archivos principales de API, pipeline, analisis y despliegue cloud.
- Escaneo basico de patrones sensibles en `apisVcloud/`; solo aparecieron menciones documentales a Secrets Manager y comandos de login ECR, sin claves embebidas.

## Notas operativas

- No se deben versionar credenciales, perfiles AWS locales, bases SQLite ni datos regenerables pesados.
- La capa cloud espera credenciales mediante Task Role de ECS o configuracion externa segura.
- `ISEU_BUCKET` es obligatorio para ejecuciones cloud.
- Los datos Bronze/Silver/Gold se conservan como artefactos regenerables y sincronizables con S3, no como codigo fuente versionado.