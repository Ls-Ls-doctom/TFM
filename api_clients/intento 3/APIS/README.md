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

## Ampliacion de indicadores INE

El conector `ine` descarga tambien tablas oficiales que permiten responder preguntas ciudadanas con datos comparables:

| Bloque | Tabla INE | Escala utilizada | Credenciales |
|---|---:|---|---|
| Demografia urbana | 69301 | Ciudad | No |
| Hogares, alquiler y vivienda | 69302 | Ciudad | No |
| Empleo, estructura sectorial y renta | 69303 | Ciudad | No |
| Educacion | 69304 | Ciudad | No |
| Suelo y zonas verdes | 69305 | Ciudad | No |
| Movilidad al trabajo | 69306 | Ciudad | No |
| Turismo | 69307 | Ciudad | No |
| IPC anual | 76154 | Provincia, etiquetado como proxy urbano | No |
| Precio del alquiler (IPVA) | 59060 | Municipio; no cubre territorios forales | No |
| Tejido empresarial (DIRCE) | 306 | Provincia, etiquetado como proxy urbano | No |

Los proxies provinciales conservan `territorial_scope=province_proxy`, `source_geography` y una nota metodologica en Silver. No deben presentarse como mediciones estrictamente municipales. La serie IPVA no ofrece Bilbao porque la fuente tributaria del indice excluye los territorios forales.
