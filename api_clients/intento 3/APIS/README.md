# APIs intento 3

Conectores de ingesta raw para la capa Bronze del TFM.

## Estructura de salida

Los datos crudos se guardan separados por tipo de fuente:

```text
api_clients/intento 3/data_lake/bronze/
  apis/
    ine/
    mitma/
    sepe/
    catalogos/
    aemet/
  municipios/
    barcelona/
    madrid/
    valencia/
    sevilla/
    bilbao/
    malaga/
    zaragoza/
```

Cada carpeta de API incluye los archivos raw descargados y un `manifest_raw.json` con metadatos de ejecucion, URLs consultadas y estado de cada recurso.

## Ejecucion APIs nacionales

```powershell
python "api_clients\intento 3\APIS\run_all.py"
```

Sin argumentos ejecuta: `ine`, `mitma`, `sepe`, `catalogos` y `aemet`.

Tambien se pueden ejecutar fuentes concretas:

```powershell
python "api_clients\intento 3\APIS\run_all.py" ine sepe catalogos
```

El informe de lote se guarda en:

```text
api_clients/intento 3/reports/apis_run.json
```

## Ejecucion APIs municipales

```powershell
python "api_clients\intento 3\APIS\municipios\run_municipios.py"
```

El informe municipal se guarda en:

```text
api_clients/intento 3/reports/municipios_run.json
```

## Notas

- AEMET requiere API key para descargar datos reales. Define `AEMET_API_KEY` antes de ejecutar si quieres activar esa descarga.
- MITMA/MIVAU conserva una referencia legacy a `precio_medio_m2_municipios.xls`, pero actualmente no responde correctamente. El error queda registrado en Bronze para mantener trazabilidad.