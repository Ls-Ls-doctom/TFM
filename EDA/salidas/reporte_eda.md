# EDA datasets ISEU+

Generado: 2026-05-14T01:00:35
Estado general: POSITIVO

## Resumen

- Archivos raw perfilados: 41
- Filas raw perfiladas: 390.212
- Datasets limpios perfilados: 18
- Filas limpias sin contar `indicadores_limpios.csv`: 413.440
- Filas en SQLite `indicadores`: 279.048
- Filas en tablas detalle SQL: 413.440
- Tablas detalle SQL: 17
- Ratio SQL/limpio: 0.6749

## Salud de APIs

- OK `raw_rows`: 390212 - Filas recuperadas en archivos raw perfilables.
- OK `clean_rows`: 413440 - Filas normalizadas en CSV limpios.
- OK `sql_indicator_rows`: 279048 - Filas cargadas en la tabla analitica indicadores.
- OK `sql_detail_rows`: 413440 - Filas cargadas en tablas detalle SQL.
- OK `sql_detail_tables`: 17 - Tablas detalle creadas desde CSV limpios.
- OK `api_total_ok`: 1 - Extracciones API correctas.
- OK `api_total_error`: 0 - Errores de extraccion.
- AVISO `api_total_manual`: 1 - Fuentes documentadas como manuales.
- OK `sql_pipeline`: OK - Estado de limpieza y carga SQLite dentro de run_all.
- OK `api_empleo`: 1 ok / 0 err / 1 manual - Resultado por conector.
- OK `cleaning_status`: 0 - Transformaciones de limpieza con estado distinto de OK/SIN_DATOS.

## Principales Huecos De Indicadores

- `bcn_licencias_limpio.csv`: 44000 filas limpias, 44000 en detalle SQL, 358 en indicadores. Contar locales/actividades por distrito, sector y estado; usar densidad empresarial y licencias comerciales.
- `bcn_zonas_verdes_limpio.csv`: 33389 filas limpias, 33389 en detalle SQL, 52 en indicadores. Agregar arboles/zonas verdes por barrio/distrito; calcular elementos verdes por 1.000 habitantes si se cruza con poblacion.
- `sepe_contratos_limpio.csv`: 97538 filas limpias, 97538 en detalle SQL, 78028 en indicadores. Revisar transformacion.
- `bcn_aire_limpio.csv`: 15041 filas limpias, 15041 en detalle SQL, 7 en indicadores. Detectar contaminante/valor si existe en fuente correcta o cambiar dataset a mediciones de calidad del aire; agregar media por estacion, contaminante y fecha.
- `bcn_movilidad_limpio.csv`: 8055 filas limpias, 8055 en detalle SQL, 30 en indicadores. Agregar bicis en uso por timestamp, estacion o total; construir intensidad de uso Bicing como proxy de movilidad.
- `bcn_seguridad_limpio.csv`: 8072 filas limpias, 8072 en detalle SQL, 120 en indicadores. Contar accidentes por distrito, mes, dia/hora y causa; normalizar por poblacion.
- `sepe_paro_limpio.csv`: 98156 filas limpias, 98156 en detalle SQL, 94359 en indicadores. Revisar transformacion.
- `bcn_equipamientos_limpio.csv`: 2722 filas limpias, 2722 en detalle SQL, 149 en indicadores. Contar equipamientos por tipo, barrio/distrito y calcular equipamientos por 10.000 habitantes cruzando poblacion.
- `bcn_turismo_limpio.csv`: 446 filas limpias, 446 en detalle SQL, 39 en indicadores. Contar hoteles/equipamientos turisticos por barrio/distrito y plazas si hay campo numerico util.
- `mitma_precio_m2_vivienda_limpio.csv`: 24366 filas limpias, 24366 en detalle SQL, 24249 en indicadores. Actualmente solo entra Barcelona municipio. Mantener detalle de otros municipios para benchmark metropolitano/provincial.

## Calidad De Datos

Resumen de indicadores por nivel de calidad calculado:
- `alta`: 275.651 filas
- `media`: 3.396 filas
- `revisar`: 1 filas

Datasets limpios con menor puntuacion de calidad:
- `bcn_equipamientos_limpio.csv`: score 87.8 (alta), completitud 84.05%, duplicados 0.0%, flags: 5_columnas_muy_nulas
- `sepe_contratos_limpio.csv`: score 89.5 (alta), completitud 83.25%, duplicados 0.0%, flags: 3_columnas_muy_nulas
- `bcn_turismo_limpio.csv`: score 91.2 (alta), completitud 89.35%, duplicados 0.0%, flags: 4_columnas_muy_nulas
- `bcn_movilidad_limpio.csv`: score 92.0 (alta), completitud 100.0%, duplicados 0.0%, flags: sin_geo_clara
- `bcn_alquiler_limpio.csv`: score 92.0 (alta), completitud 100.0%, duplicados 0.0%, flags: sin_fecha_clara
- `bcn_transporte_limpio.csv`: score 92.0 (alta), completitud 100.0%, duplicados 0.0%, flags: sin_geo_clara
- `idescat_limpio.csv`: score 92.0 (alta), completitud 100.0%, duplicados 0.0%, flags: sin_fecha_clara
- `ine_limpio.csv`: score 94.0 (alta), completitud 88.88%, duplicados 0.0%, flags: 1_columnas_muy_nulas

## Nulos Y Columnas

- `conservar`: 304 columnas
- `conservar_con_cautela`: 8 columnas
- `revisar_columna`: 7 columnas
- `revisar_constante`: 5 columnas

Columnas candidatas a eliminar por nulos:
- Ninguna columna cumple criterio fuerte de eliminacion automatica.

Columnas a revisar antes de eliminar:
- `bcn_equipamientos_limpio.csv.addresses_roadtype_id`: 100.0% nulos. Nulidad alta, pero puede aportar informacion parcial.
- `bcn_turismo_limpio.csv.addresses_roadtype_id`: 100.0% nulos. Nulidad alta, pero puede aportar informacion parcial.
- `bcn_turismo_limpio.csv.institution_id`: 100.0% nulos. Nulidad alta, pero puede aportar informacion parcial.
- `bcn_turismo_limpio.csv.values_description`: 100.0% nulos. Nulidad alta, pero puede aportar informacion parcial.
- `ine_limpio.csv.unidad`: 100.0% nulos. Nulidad alta, pero puede aportar informacion parcial.
- `bcn_equipamientos_limpio.csv.values_description`: 97.21% nulos. Nulidad alta, pero puede aportar informacion parcial.
- `bcn_zonas_verdes_limpio.csv.data_plantacio`: 93.95% nulos. Nulidad alta, pero puede aportar informacion parcial.
- `bcn_equipamientos_limpio.csv.institution_id`: 91.77% nulos. Nulidad alta, pero puede aportar informacion parcial.
- `bcn_equipamientos_limpio.csv.institution_name`: 91.77% nulos. Muchos nulos; conservar solo si aporta contexto metodologico.
- `bcn_turismo_limpio.csv.addresses_end_street_number`: 91.03% nulos. Muchos nulos; conservar solo si aporta contexto metodologico.
- `bcn_equipamientos_limpio.csv.addresses_end_street_number`: 81.81% nulos. Muchos nulos; conservar solo si aporta contexto metodologico.
- `bcn_licencias_limpio.csv.nom_eix`: 61.77% nulos. Nulidad alta, pero puede aportar informacion parcial.

## Correlaciones E Interacciones

Correlaciones fuertes dentro de datasets detalle:
- `bcn_movilidad_limpio.csv`: `bikesinusage` vs `mechanicalbikesinusage` = 0.9999 (positiva muy fuerte, n=8055)
- `bcn_turismo_limpio.csv`: `addresses_end_street_number` vs `addresses_start_street_number` = 0.9999 (positiva muy fuerte, n=40)
- `bcn_equipamientos_limpio.csv`: `addresses_end_street_number` vs `addresses_start_street_number` = 0.9992 (positiva muy fuerte, n=495)
- `sepe_paro_limpio.csv`: `paro_total` vs `mujeres_45_mas` = 0.9989 (positiva muy fuerte, n=89026)
- `sepe_paro_limpio.csv`: `paro_total` vs `mujeres_25_44` = 0.9986 (positiva muy fuerte, n=81018)
- `sepe_paro_limpio.csv`: `paro_total` vs `sector_servicios` = 0.9979 (positiva muy fuerte, n=93723)
- `sepe_paro_limpio.csv`: `hombres_25_44` vs `sector_servicios` = 0.9979 (positiva muy fuerte, n=79120)
- `sepe_paro_limpio.csv`: `paro_total` vs `hombres_45_mas` = 0.9972 (positiva muy fuerte, n=88783)
- `sepe_paro_limpio.csv`: `paro_total` vs `hombres_25_44` = 0.9969 (positiva muy fuerte, n=79420)
- `sepe_paro_limpio.csv`: `mujeres_25_44` vs `mujeres_45_mas` = 0.9969 (positiva muy fuerte, n=78710)
- `sepe_paro_limpio.csv`: `hombres_45_mas` vs `sector_servicios` = 0.9967 (positiva muy fuerte, n=88048)
- `sepe_paro_limpio.csv`: `hombres_25_44` vs `hombres_45_mas` = 0.9965 (positiva muy fuerte, n=76668)

Correlaciones fuertes entre indicadores:
- `Open Data BCN | bcn_licencias_agregado | Licencias comerciales` vs `Open Data BCN | bcn_licencias_sector_agregado | Densidad empresarial` = 0.963 (positiva muy fuerte, periodos=22)
- `INE | tasa_empleo_cataluna | Tasa de empleo` vs `INE | tasa_paro_cataluna | Tasa de paro` = -0.9543 (negativa muy fuerte, periodos=20)
- `MITMA/MIVAU | precio_m2_vivienda | Precio vivienda m2` vs `MITMA/MIVAU | precio_m2_vivienda_municipios | Precio vivienda m2` = 0.7617 (positiva fuerte, periodos=84)

## Archivos generados

- `inventario_raw.csv`
- `inventario_limpios.csv`
- `perfil_columnas_limpios.csv`
- `conteo_sql_indicadores.csv`
- `conteo_sql_detalle.csv`
- `oportunidades_sql.csv`
- `salud_apis.csv`
- `calidad_datasets.csv`
- `calidad_indicadores.csv`
- `nulos_columnas.csv`
- `correlaciones_detalle.csv`
- `correlaciones_indicadores.csv`

## Lectura tecnica

El cuello de botella no esta en SQLite, sino en la capa de transformacion a indicadores. Muchos datasets limpios son registros geograficos o administrativos; para aprovecharlos hay que agregarlos por fecha, barrio/distrito, tipo o fuente antes de insertarlos en la tabla analitica.