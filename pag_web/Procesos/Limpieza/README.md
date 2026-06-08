# Limpieza de datasets ISEU+

Esta carpeta contiene los scripts que transforman los datos brutos de `api_clients/data` en datos limpios.

Script principal:

```powershell
python pag_web\Procesos\Limpieza\clean_datasets.py
```

Salidas:

- `pag_web/Procesos/Datasets/limpios/*_limpio.csv`
- `pag_web/Procesos/Datasets/limpios/indicadores_limpios.csv`
- `pag_web/Procesos/Datasets/limpios/catalogo_limpieza.json`

Notas:

- MITMA/MIVAU `precio_m2_venta_raw.xls` se convierte a `mitma_precio_m2_vivienda_limpio.csv`.
- Open Data BCN `2017_taxa_lloguer_od.gpkg` se convierte a `bcn_alquiler_limpio.csv`.
- El dato de alquiler se marca como proxy porque mide tasa/esfuerzo de alquiler por seccion censal, no precio mensual en euros.
