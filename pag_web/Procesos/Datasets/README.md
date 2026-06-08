# Datasets ISEU+

Esta carpeta guarda la capa de datos ya preparada para el asistente.

- `limpios/`: CSV normalizados generados por `../Limpieza/clean_datasets.py`.
- `iseu_datos.sqlite`: base SQLite creada por `build_sqlite.py`.
- `sqlite_carga.json`: resumen de la ultima carga.

Flujo recomendado:

```powershell
python api_clients\run_all.py
```

`run_all.py` ejecuta los conectores, normaliza los datos y recarga SQLite. Para regenerar solo la capa SQL con los raw ya descargados:

```powershell
python pag_web\Procesos\Limpieza\clean_datasets.py
python pag_web\Procesos\Datasets\build_sqlite.py
```

La tabla principal para respuestas analiticas es `indicadores`. Ademas, `build_sqlite.py` crea tablas `detalle_*` con los CSV limpios completos para no perder granularidad:

- `detalle_ine`
- `detalle_ree_precios`
- `detalle_ree_demanda`
- `detalle_mitma_precio_m2_vivienda`
- `detalle_bcn_licencias`
- `detalle_bcn_seguridad`
- `detalle_bcn_zonas_verdes`
- y el resto de datasets limpios.

El modelo no deberia leer archivos raw directamente: primero conviene consultar SQLite. Para respuestas finales se usa `indicadores`; para crear nuevas metricas o agregaciones se usan las tablas `detalle_*`.

`build_sqlite.py` tambien genera indicadores derivados desde algunas tablas detalle:

- precios MITMA/MIVAU para municipios disponibles.
- licencias comerciales por distrito/sector.
- accidentes por distrito y mes.
- movilidad Bicing por dia.
- equipamientos por distrito/tipo.
- zonas verdes por barrio.
- tarifas de movilidad.
- rangos de calidad del aire como proxy de baja confianza.
