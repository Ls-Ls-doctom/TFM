# Pipeline ISEU+ Bronze / Silver / Gold

Este pipeline deja la limpieza ejecutable por scripts `.py` y evita modificar la capa Bronze.

## Orden manual

```powershell
python "api_clients\intento 3\APIS\run_all.py"
python "api_clients\intento 3\APIS\municipios\run_municipios.py"
python "api_clients\intento 3\pipeline\01_inventory_bronze.py"
python "api_clients\intento 3\pipeline\02_clean_silver.py"
python "api_clients\intento 3\pipeline\03_build_gold.py"
python "api_clients\intento 3\pipeline\04_build_sqlite.py"
```

## Orquestador

```powershell
python "api_clients\intento 3\run_pipeline.py"
```

Para reutilizar datos ya descargados:

```powershell
python "api_clients\intento 3\run_pipeline.py" --skip-collect
```

## Salidas

- `data_lake/bronze/`: datos raw descargados.
- `data_lake/silver/`: tablas limpias filtradas a ciudades objetivo.
- `data_lake/gold/indicators.csv`: indicadores normalizados.
- `data_lake/gold/iseu_indicadores.sqlite`: base SQLite para consultas.
- `reports/`: reportes de inventario, limpieza, Gold, SQLite y ejecución completa.

## Nota para repositorio

Subir el código, README y manifiestos pequeños. Evitar subir archivos raw pesados de `data_lake/bronze`; se regeneran ejecutando los conectores.
