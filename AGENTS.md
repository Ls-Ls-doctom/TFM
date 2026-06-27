# AGENTS.md — Guia para agentes (Codex / Claude) en el proyecto ISEU

Este archivo orienta a cualquier agente de IA (Codex, Claude, etc.) que trabaje en este
repositorio. Lee esto primero. Para el detalle del despliegue cloud ya en marcha, ve a
[apisVcloud/deploy/ESTADO.md](apisVcloud/deploy/ESTADO.md).

## Que es este proyecto

**ISEU** es un TFM que construye un **data lake** de indicadores socioeconomicos de Espana
(Bronze -> Silver -> Gold) a partir de APIs publicas (INE, MITMA, SEPE, AEMET, catalogos y
datos municipales de 7 ciudades), mas una **web/dashboard** y una **capa de ejecucion cloud**
en AWS que automatiza todo mensualmente.

## Mapa del repositorio

| Carpeta | Que contiene |
|---|---|
| `api_clients/intento 3/` | **El pipeline real** (lo importante). Conectores y transformacion. |
| `api_clients/intento 3/APIS/` | Conectores de APIs (`run_all.py`, `api_ine.py`, `api_aemet.py`, ...) y `municipios/`. |
| `api_clients/intento 3/pipeline/` | Transformacion por capas: `01_inventory_bronze.py`, `02_clean_silver.py`, `03_build_gold.py`, `04_build_sqlite.py`. |
| `api_clients/intento 3/data_lake/` | Salida local: `bronze/`, `silver/`, `gold/` (no versionar datos pesados). |
| `apisVcloud/` | **Capa cloud**. Envuelve el pipeline local y lo ejecuta en AWS Fargate sincronizando a S3. |
| `apisVcloud/deploy/` | **Automatizacion de despliegue** (scripts PowerShell + docs). Ver `ESTADO.md`. |
| `pag_web/` | Web y dashboard. `Assets/JS/app.js`, `Assets/CSS/`, `dashboard.html`, `LMlocal/` (servidor LLM local), `Procesos/` (datasets y limpieza). |
| `versiones/` | Notas de versiones del proyecto. |

## Principios al trabajar aqui

1. **No reescribas los conectores locales.** La capa `apisVcloud/` esta disenada para
   ejecutar `api_clients/intento 3/` SIN modificarlo. Si cambias el pipeline, hazlo en
   `api_clients/intento 3/` y verifica que la capa cloud lo sigue invocando igual.
2. **Dependencias minimas.** Los conectores usan solo stdlib + `pandas`. La imagen cloud
   ([apisVcloud/requirements.txt](apisVcloud/requirements.txt)) solo anade `boto3` y `pyarrow`.
   No introduzcas dependencias nuevas sin necesidad (engordan la imagen Fargate).
3. **Idempotencia.** La sincronizacion a S3 usa hash SHA-256: no resube objetos identicos.
   Manten esa propiedad si tocas [apisVcloud/s3_storage.py](apisVcloud/s3_storage.py).
4. **Config por entorno.** Todo se parametriza con variables `ISEU_*`
   (ver [apisVcloud/settings.py](apisVcloud/settings.py) y la tabla en
   [apisVcloud/README.md](apisVcloud/README.md)). No hardcodees buckets ni rutas.
5. **Credenciales fuera del codigo.** En AWS vienen del Task Role / Secrets Manager. Nunca
   commitees claves. La clave AEMET (`AEMET_API_KEY`) es opcional: si falta, esa fuente se
   omite (`SKIPPED_AUTH`) sin romper el resto.

## Como ejecutar el pipeline en local (sin Docker, sin AWS)

```powershell
cd "api_clients/intento 3"
python APIS/run_all.py          # recoleccion -> data_lake/bronze
python pipeline/01_inventory_bronze.py
python pipeline/02_clean_silver.py   # -> data_lake/silver
python pipeline/03_build_gold.py     # -> data_lake/gold
```

## Como ejecutar la capa cloud en local (apunta a S3)

```powershell
$env:ISEU_PROJECT_ROOT = "<raiz-del-repo>"   # en contenedor es /app
$env:ISEU_BUCKET = "iseu-datalake-ismael-2026"
$env:AWS_REGION  = "eu-west-1"
python -m apisVcloud.cloud_pipeline --mode full   # full | collect | transform
```

## Estado actual (resumen)

El despliegue cloud **ya esta hecho y funcionando** en la cuenta AWS `720644165834`
(region `eu-west-1`): Fargate + EventBridge ejecutan el pipeline el dia 1 de cada mes y
vuelcan a `s3://iseu-datalake-ismael-2026/`. El **diagrama de arquitectura**, el inventario
completo de recursos/ARNs, el runbook y las mejoras pendientes estan en
**[apisVcloud/deploy/ESTADO.md](apisVcloud/deploy/ESTADO.md)** (seccion "Arquitectura").

## Por donde seguir mejorando

Ver la seccion "Roadmap" de [apisVcloud/deploy/ESTADO.md](apisVcloud/deploy/ESTADO.md).
Lo mas inmediato: Glue Crawler + Athena, particionar Gold cuando crezca, y separar
`collect`/`transform` con Step Functions para reintentar solo la fase que falle.
