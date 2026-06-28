# ISEU+ — Índice de Salud Económica Urbana

Plataforma de análisis económico urbano para ciudades españolas, desarrollada como Trabajo de Fin de Máster. Integra datos oficiales de empleo, renta, demografía y movilidad en un sistema de consulta conversacional con trazabilidad completa.

**URL pública:** https://project-zcvjr.vercel.app

---

## Arquitectura

```
APIs oficiales (INE / SEPE / Open Data BCN)
        │
        ▼
┌─────────────────────────────────────────────────┐
│  ECS Fargate  ·  Pipeline Bronze → Silver → Gold │
│  (Docker, Python 3.12, programado con EventBridge│
└───────────────────────┬─────────────────────────┘
                        │  Parquet + Snappy
                        ▼
              Amazon S3  (iseu-datalake-ismael-2026)
              ├── bronze/          ← datos crudos
              ├── silver/athena/   ← datos limpios
              └── gold/athena/     ← indicadores
                        │
                        ▼
              AWS Glue Data Catalog  (base de datos: iseu)
                        │
                        ▼
              Amazon Athena  (dialecto Trino / SQL)
                        │
                        ▼
              AWS Lambda  (iseu-athena-query)
              ├── GET  /dashboard   ← KPIs y gráficas
              ├── GET  /catalog     ← catálogo de variables
              └── POST /sql         ← SQL validado
                        │
                        ▼
              Vercel  (project-zcvjr.vercel.app)
              ├── dashboard.html   ← visualización de datos
              ├── chatbot.html     ← asistente conversacional
              ├── api/dashboard.py ← proxy → Lambda
              └── api/chat.py      ← NL2SQL con Gemini 2.5 Flash
```

---

## Datos disponibles

| Métrica | Valor |
|---|---|
| Registros totales en Athena | 386.225 filas |
| Indicadores principales (`iseu_indicadores`) | 93.944 |
| Observaciones semánticas (`iseu_semantic_obs`) | 105.774 |
| Variables analíticas | 22 |
| Ciudades cubiertas | 7 |
| Cobertura temporal | 2015 – 2023 |
| Fuentes integradas | INE, SEPE, Municipal Open Data |

**Ciudades:** Barcelona · Bilbao · Madrid · Málaga · Sevilla · Valencia · Zaragoza

**Variables:** Renta (bruta, disponible, mediana, por hogar/persona) · Desigualdad Gini · P80/P20 · Paro registrado · Contratos registrados · Demandantes de empleo · Población total · Accidentes de tráfico · Registros de movilidad · Usuarios bicicleta pública

---

## Estructura del repositorio

```
TFM/
├── api/                        # Endpoints Vercel (Python)
│   ├── chat.py                 # Chatbot con Gemini 2.5 Flash (SSE + JSON)
│   ├── dashboard.py            # Proxy al endpoint Lambda /dashboard
│   └── health.py               # Health check
│
├── apisVcloud/                 # Infraestructura cloud AWS
│   ├── cloud_pipeline.py       # Orquestador del pipeline en contenedor
│   ├── s3_storage.py           # Cliente S3 con SHA-256 idempotente
│   ├── settings.py             # Configuración por variables de entorno
│   ├── publish_cloud.py        # Exportación a Parquet para Athena
│   ├── Dockerfile              # Imagen Python 3.12-slim para ECS Fargate
│   ├── athena-stack.yaml       # CloudFormation: Athena workgroup + Glue DB
│   ├── s3-lifecycle.json       # Política de ciclo de vida S3
│   ├── task-role-policy.json   # Política IAM del Task Role ECS
│   ├── requirements.txt        # Dependencias cloud (boto3, pandas, pyarrow)
│   └── query_api/
│       └── handler.py          # Lambda handler (endpoints dashboard/sql/catalog)
│
├── api_clients/intento 3/      # Pipeline de datos local
│   ├── APIS/                   # Conectores a fuentes oficiales
│   ├── pipeline/               # Scripts ETL (01-05: collect→clean→gold→sqlite→athena)
│   ├── run_pipeline.py         # Orquestador local
│   └── data_lake/              # Bronze/Silver/Gold generados (ignorados por Git)
│
├── pag_web/                    # Frontend y procesamiento local
│   ├── dashboard.html          # Dashboard de visualización
│   ├── chatbot.html            # Interfaz conversacional
│   ├── Assets/CSS/styles.css   # Estilos de la aplicación
│   ├── Assets/JS/app.js        # Lógica frontend (chart rendering, SSE, tabs)
│   ├── Procesos/
│   │   ├── gemini_data.py      # NL2SQL + respuesta con Gemini (streaming)
│   │   ├── sql_data.py         # Capa de acceso a datos (local + Lambda)
│   │   └── Datasets/           # SQLite local (ignorado por Git)
│   └── LMlocal/server.py       # Servidor local de desarrollo
│
├── arquitectura/               # Diagramas y documentación de arquitectura
├── EDA/                        # Análisis exploratorio y salidas de calidad
├── LaTeX Informe/              # Memoria del TFM en LaTeX
│   ├── main.tex                # Documento principal
│   ├── chapters/
│   │   ├── memoria.tex         # Capítulos principales (intro, contexto, pipeline)
│   │   └── arquitectura_cloud.tex  # Capítulo cloud (S3, Athena, Lambda, Vercel)
│   └── figures/                # Figuras del informe
│
├── vercel.json                 # Configuración de despliegue Vercel
├── requirements.txt            # Dependencias Python del proyecto
└── .github/workflows/          # CI/CD (rebuild Docker en push)
```

---

## Despliegue

### Frontend (Vercel)

El frontend se despliega automáticamente en cada `git push` a `main`. Variables de entorno requeridas en Vercel:

```
GEMINI_API_KEY=...           # API Key de Google Gemini
LAMBDA_URL=https://...       # URL del API Gateway de Lambda
LAMBDA_API_KEY=...           # API Key del endpoint Lambda
```

### Pipeline cloud (ECS Fargate)

```bash
# Trigger manual del pipeline
aws ecs run-task \
  --cluster iseu-cluster \
  --task-definition iseu-pipeline:2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[subnet-xxx],
    securityGroups=[sg-xxx],
    assignPublicIp=ENABLED}"
```

### Lambda (actualización de código)

```bash
# Empaquetar y desplegar el handler
cd apisVcloud/query_api
zip handler.zip handler.py
aws lambda update-function-code \
  --function-name iseu-athena-query \
  --zip-file fileb://handler.zip \
  --publish
```

### Pipeline local

```bash
cd "api_clients/intento 3"
python run_pipeline.py          # Pipeline completo
python run_pipeline.py --skip-bronze  # Solo transformación (reutiliza Bronze)
```

---

## Chatbot: flujo NL2SQL

```
Usuario: "¿Cuál es la ciudad con más paro registrado?"
         │
         ▼
  Gemini 2.5 Flash (planificador SQL)
  → { needs_data: true,
      sql: "SELECT city, SUM(value) FROM indicators
            WHERE variable='unemployed_registered'
            GROUP BY city ORDER BY 2 DESC LIMIT 7",
      reason: "..." }
         │
         ▼
  Lambda /sql → Athena → resultados (7 filas)
         │
         ▼
  Gemini 2.5 Flash (generación de respuesta)
  → "Madrid lidera con 203.542 personas en paro
     registrado según datos SEPE de 2023..."
         │
         ▼
  SSE streaming al usuario (token a token)
```

---

## Variables de entorno locales

```env
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
LAMBDA_URL=https://xxx.execute-api.eu-west-1.amazonaws.com/prod
LAMBDA_API_KEY=...
ISEU_BUCKET=iseu-datalake-ismael-2026
AWS_REGION=eu-west-1
```

---

## Fuentes de datos

| Fuente | Organismo | Variables |
|---|---|---|
| INE | Instituto Nacional de Estadística | Renta (bruta, disponible, mediana, por hogar/persona), Desigualdad Gini y P80/P20, Población |
| SEPE | Servicio Público de Empleo Estatal | Paro registrado, Contratos registrados, Demandantes de empleo |
| Municipal Open Data | Ayuntamiento de Barcelona | Accidentes de tráfico, Registros de movilidad, Usuarios bicicleta pública |

---

## Coste cloud estimado

| Servicio | Estimación mensual |
|---|---|
| Amazon S3 (500 MB Parquet) | < 0,02 USD |
| Amazon Athena (3.000 consultas) | < 0,01 USD |
| AWS Lambda (3.000 invocaciones) | < 0,01 USD |
| ECS Fargate (4 ejecuciones/mes) | ≈ 0,20 USD |
| Gemini 2.5 Flash API | 0,00 USD (plan gratuito) |
| Vercel | 0,00 USD (plan Hobby) |
| **Total** | **< 0,30 USD/mes** |

---

*Trabajo de Fin de Máster · Análisis de Datos Urbanos · 2026*
