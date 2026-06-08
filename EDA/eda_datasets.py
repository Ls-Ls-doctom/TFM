from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "api_clients" / "data"
CLEAN_DIR = ROOT / "pag_web" / "Procesos" / "Datasets" / "limpios"
DB_PATH = ROOT / "pag_web" / "Procesos" / "Datasets" / "iseu_datos.sqlite"
OUT_DIR = ROOT / "EDA" / "salidas"
API_REPORT_PATH = RAW_DIR / "informe_ejecucion.json"
CLEAN_REPORT_PATH = CLEAN_DIR / "catalogo_limpieza.json"


DATASET_OPPORTUNITIES = {
    "bcn_aire_limpio.csv": {
        "estado_sql": "fuera",
        "propuesta": "Detectar contaminante/valor si existe en fuente correcta o cambiar dataset a mediciones de calidad del aire; agregar media por estacion, contaminante y fecha.",
        "valor_sql": "Calidad del aire",
        "prioridad": "alta",
    },
    "bcn_equipamientos_limpio.csv": {
        "estado_sql": "fuera",
        "propuesta": "Contar equipamientos por tipo, barrio/distrito y calcular equipamientos por 10.000 habitantes cruzando poblacion.",
        "valor_sql": "Acceso a salud / educacion",
        "prioridad": "alta",
    },
    "bcn_licencias_limpio.csv": {
        "estado_sql": "fuera",
        "propuesta": "Contar locales/actividades por distrito, sector y estado; usar densidad empresarial y licencias comerciales.",
        "valor_sql": "Licencias comerciales / densidad empresarial",
        "prioridad": "alta",
    },
    "bcn_movilidad_limpio.csv": {
        "estado_sql": "fuera",
        "propuesta": "Agregar bicis en uso por timestamp, estacion o total; construir intensidad de uso Bicing como proxy de movilidad.",
        "valor_sql": "Movilidad urbana",
        "prioridad": "media",
    },
    "bcn_seguridad_limpio.csv": {
        "estado_sql": "fuera",
        "propuesta": "Contar accidentes por distrito, mes, dia/hora y causa; normalizar por poblacion.",
        "valor_sql": "Seguridad ciudadana",
        "prioridad": "alta",
    },
    "bcn_transporte_limpio.csv": {
        "estado_sql": "fuera",
        "propuesta": "Usar import_fraccio/import_maxim como coste de movilidad; crear indicador por tipo de tarifa.",
        "valor_sql": "Transporte publico coste",
        "prioridad": "media",
    },
    "bcn_turismo_limpio.csv": {
        "estado_sql": "fuera",
        "propuesta": "Contar hoteles/equipamientos turisticos por barrio/distrito y plazas si hay campo numerico util.",
        "valor_sql": "Turismo / ocupacion hotelera",
        "prioridad": "media",
    },
    "bcn_zonas_verdes_limpio.csv": {
        "estado_sql": "fuera",
        "propuesta": "Agregar arboles/zonas verdes por barrio/distrito; calcular elementos verdes por 1.000 habitantes si se cruza con poblacion.",
        "valor_sql": "Zonas verdes por habitante",
        "prioridad": "alta",
    },
    "mitma_precio_m2_vivienda_limpio.csv": {
        "estado_sql": "parcial",
        "propuesta": "Actualmente solo entra Barcelona municipio. Mantener detalle de otros municipios para benchmark metropolitano/provincial.",
        "valor_sql": "Precio vivienda m2",
        "prioridad": "alta",
    },
}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    clean_inventory, column_profile = profile_clean_files()
    raw_inventory = profile_raw_files()
    sql_counts = load_sql_counts()
    detail_counts = load_detail_counts()
    opportunities = build_opportunities(clean_inventory, sql_counts, detail_counts)
    api_health = build_api_health(raw_inventory, clean_inventory, sql_counts, detail_counts)
    data_quality = build_data_quality(clean_inventory, column_profile)
    indicator_quality = build_indicator_quality()
    null_recommendations = build_null_recommendations(column_profile)
    detail_correlations = build_detail_correlations()
    indicator_correlations = build_indicator_correlations()

    write_csv(clean_inventory, "inventario_limpios.csv")
    write_csv(raw_inventory, "inventario_raw.csv")
    write_csv(column_profile, "perfil_columnas_limpios.csv")
    write_csv(sql_counts, "conteo_sql_indicadores.csv")
    write_csv(detail_counts, "conteo_sql_detalle.csv")
    write_csv(opportunities, "oportunidades_sql.csv")
    write_csv(api_health, "salud_apis.csv")
    write_csv(data_quality, "calidad_datasets.csv")
    write_csv(indicator_quality, "calidad_indicadores.csv")
    write_csv(null_recommendations, "nulos_columnas.csv")
    write_csv(detail_correlations, "correlaciones_detalle.csv")
    write_csv(indicator_correlations, "correlaciones_indicadores.csv")
    write_report(
        clean_inventory,
        raw_inventory,
        sql_counts,
        detail_counts,
        opportunities,
        api_health,
        data_quality,
        indicator_quality,
        null_recommendations,
        detail_correlations,
        indicator_correlations,
    )

    print(f"EDA generado en: {OUT_DIR}")
    print(f"Datasets limpios perfilados: {len(clean_inventory)}")
    print(f"Columnas perfiladas: {len(column_profile)}")
    print(f"Oportunidades detectadas: {len(opportunities)}")
    print(f"Indicadores salud API: {len(api_health)}")
    print(f"Datasets con calidad evaluada: {len(data_quality)}")
    print(f"Columnas con recomendacion de nulos: {len(null_recommendations)}")
    print(f"Correlaciones detalle detectadas: {len(detail_correlations)}")
    print(f"Correlaciones indicadores detectadas: {len(indicator_correlations)}")


def profile_clean_files() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    inventory: list[dict[str, Any]] = []
    column_profile: list[dict[str, Any]] = []

    for path in sorted(CLEAN_DIR.glob("*.csv")):
        df = pd.read_csv(path, low_memory=False)
        numeric_columns = []
        date_candidates = []
        geo_candidates = []

        for column in df.columns:
            series = df[column]
            numeric = pd.to_numeric(series, errors="coerce")
            numeric_non_null = int(numeric.notna().sum())
            non_null = int(series.notna().sum())
            nulls = int(series.isna().sum())
            unique = int(series.nunique(dropna=True))
            sample = first_samples(series)

            lower = column.lower()
            if numeric_non_null > 0:
                numeric_columns.append(column)
            if any(token in lower for token in ["data", "fecha", "date", "any", "anio", "year", "mes", "period"]):
                date_candidates.append(column)
            if any(token in lower for token in ["barri", "barrio", "districte", "distrito", "lat", "lon", "geo", "utm", "seccion", "censal"]):
                geo_candidates.append(column)

            column_profile.append(
                {
                    "dataset": path.name,
                    "column": column,
                    "dtype": str(series.dtype),
                    "non_null": non_null,
                    "nulls": nulls,
                    "null_pct": round(nulls / len(df), 4) if len(df) else 0,
                    "unique": unique,
                    "numeric_non_null": numeric_non_null,
                    "sample": sample,
                }
            )

        inventory.append(
            {
                "dataset": path.name,
                "path": rel(path),
                "size_mb": round(path.stat().st_size / 1024 / 1024, 3),
                "rows": int(len(df)),
                "columns": int(len(df.columns)),
                "numeric_columns": len(numeric_columns),
                "numeric_column_names": "; ".join(numeric_columns[:20]),
                "date_candidates": "; ".join(date_candidates[:12]),
                "geo_candidates": "; ".join(geo_candidates[:12]),
            }
        )

    return inventory, column_profile


def profile_raw_files() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(RAW_DIR.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".csv", ".json", ".xls", ".xlsx", ".gpkg"}:
            continue

        item: dict[str, Any] = {
            "file": path.name,
            "path": rel(path),
            "suffix": path.suffix.lower(),
            "size_mb": round(path.stat().st_size / 1024 / 1024, 3),
            "rows": None,
            "columns": None,
            "notes": "",
        }
        try:
            if path.suffix.lower() == ".csv":
                df = pd.read_csv(path, low_memory=False)
                item["rows"] = int(len(df))
                item["columns"] = int(len(df.columns))
            elif path.suffix.lower() == ".json":
                parsed = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(parsed, list):
                    item["rows"] = len(parsed)
                elif isinstance(parsed, dict):
                    item["rows"] = len(parsed)
                    item["notes"] = "json_dict_keys=" + ",".join(list(parsed.keys())[:8])
            elif path.suffix.lower() in {".xls", ".xlsx"}:
                xls = pd.ExcelFile(path)
                item["rows"] = len(xls.sheet_names)
                item["notes"] = "sheets=" + ",".join(xls.sheet_names[:8])
            elif path.suffix.lower() == ".gpkg":
                import geopandas as gpd
                import pyogrio

                layers = pyogrio.list_layers(path)
                layer_name = layers[0][0] if len(layers) else None
                if layer_name:
                    gdf = gpd.read_file(path, layer=layer_name)
                    item["rows"] = int(len(gdf))
                    item["columns"] = int(len(gdf.columns))
                    item["notes"] = f"layer={layer_name}; crs={gdf.crs}"
        except Exception as exc:
            item["notes"] = f"error={exc}"
        rows.append(item)
    return rows


def load_sql_counts() -> list[dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT source, dataset, variable, metric, geo, raw_file, COUNT(*) AS rows,
                   MIN(period) AS min_period, MAX(period) AS max_period
            FROM indicadores
            GROUP BY source, dataset, variable, metric, geo, raw_file
            ORDER BY rows DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def load_detail_counts() -> list[dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        exists = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'cargas_detalle'
            """
        ).fetchone()
        if not exists:
            return []
        rows = conn.execute(
            """
            SELECT table_name, source_file, rows_loaded, columns_loaded
            FROM cargas_detalle
            ORDER BY rows_loaded DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def build_opportunities(clean_inventory: list[dict[str, Any]], sql_counts: list[dict[str, Any]], detail_counts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sql_by_dataset: dict[str, int] = {}
    sql_by_source: dict[str, int] = {}
    sql_by_raw_file: dict[str, int] = {}
    detail_by_source_file = {item["source_file"].replace("/", "\\"): int(item["rows_loaded"]) for item in detail_counts}
    for item in sql_counts:
        sql_by_dataset[item["dataset"]] = sql_by_dataset.get(item["dataset"], 0) + int(item["rows"])
        sql_by_source[item["source"]] = sql_by_source.get(item["source"], 0) + int(item["rows"])
        raw_file = str(item.get("raw_file") or "").replace("/", "\\")
        if raw_file:
            sql_by_raw_file[raw_file] = sql_by_raw_file.get(raw_file, 0) + int(item["rows"])

    rows = []
    for item in clean_inventory:
        dataset = item["dataset"]
        stem = dataset.replace("_limpios.csv", "").replace("_limpio.csv", "")
        sql_rows = sql_by_dataset.get(stem, 0)
        if stem in {"indicadores", "indicadores_limpios"}:
            sql_rows = sum(int(row["rows"]) for row in sql_counts)
        if stem == "mitma_precio_m2_vivienda":
            sql_rows = sql_by_dataset.get("precio_m2_vivienda", 0)
        if stem == "ine":
            sql_rows = sql_by_source.get("INE", 0)
        if stem == "idescat":
            sql_rows = sql_by_source.get("Idescat", 0)
        detail_rows = detail_by_source_file.get(item["path"].replace("/", "\\"), 0)
        sql_rows = max(sql_rows, sql_by_raw_file.get(item["path"].replace("/", "\\"), 0))

        opportunity = DATASET_OPPORTUNITIES.get(dataset, {})
        missing_detail = max(int(item["rows"]) - int(detail_rows), 0)
        missing_indicator = max(int(item["rows"]) - int(sql_rows), 0)
        if missing_indicator == 0:
            status = "entra"
        elif sql_rows > 0:
            status = "agregado"
        elif detail_rows > 0:
            status = "detalle"
        else:
            status = opportunity.get("estado_sql", "revisar")
        rows.append(
            {
                "dataset": dataset,
                "clean_rows": item["rows"],
                "detail_rows": detail_rows,
                "indicator_rows": sql_rows,
                "missing_detail_rows_approx": missing_detail,
                "missing_indicator_rows_approx": missing_indicator,
                "status": status,
                "target_indicator": opportunity.get("valor_sql", ""),
                "priority": opportunity.get("prioridad", ""),
                "proposal": opportunity.get("propuesta", ""),
                "numeric_columns": item["numeric_column_names"],
                "date_candidates": item["date_candidates"],
                "geo_candidates": item["geo_candidates"],
            }
        )
    return rows


def build_api_health(raw_inventory: list[dict[str, Any]], clean_inventory: list[dict[str, Any]], sql_counts: list[dict[str, Any]], detail_counts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    api_report = load_json(API_REPORT_PATH)
    clean_report = load_json(CLEAN_REPORT_PATH)
    raw_rows = sum(int(item["rows"] or 0) for item in raw_inventory if item["suffix"] in {".csv", ".json", ".gpkg"})
    clean_rows = sum(int(item["rows"]) for item in clean_inventory if item["dataset"] != "indicadores_limpios.csv")
    sql_rows = sum(int(item["rows"]) for item in sql_counts)
    detail_rows = sum(int(item["rows_loaded"]) for item in detail_counts)

    rows = [
        health_row("raw_rows", raw_rows, "OK" if raw_rows >= 100000 else "REVISAR", "Filas recuperadas en archivos raw perfilables."),
        health_row("clean_rows", clean_rows, "OK" if clean_rows >= 100000 else "REVISAR", "Filas normalizadas en CSV limpios."),
        health_row("sql_indicator_rows", sql_rows, "OK" if sql_rows >= 50000 else "REVISAR", "Filas cargadas en la tabla analitica indicadores."),
        health_row("sql_detail_rows", detail_rows, "OK" if detail_rows >= clean_rows else "REVISAR", "Filas cargadas en tablas detalle SQL."),
        health_row("sql_detail_tables", len(detail_counts), "OK" if len(detail_counts) >= 10 else "REVISAR", "Tablas detalle creadas desde CSV limpios."),
    ]

    if api_report:
        resumen = api_report.get("resumen", {})
        total_ok = int(resumen.get("total_ok", 0))
        total_error = int(resumen.get("total_error", 0))
        total_manual = int(resumen.get("total_manual", 0))
        rows.extend(
            [
                health_row("api_total_ok", total_ok, "OK" if total_ok else "ERROR", "Extracciones API correctas."),
                health_row("api_total_error", total_error, "OK" if total_error == 0 else "ERROR", "Errores de extraccion."),
                health_row("api_total_manual", total_manual, "AVISO" if total_manual else "OK", "Fuentes documentadas como manuales."),
                health_row(
                    "sql_pipeline",
                    api_report.get("pipeline_sql", {}).get("estado", "SIN_DATO"),
                    "OK" if api_report.get("pipeline_sql", {}).get("estado") == "OK" else "ERROR",
                    "Estado de limpieza y carga SQLite dentro de run_all.",
                ),
            ]
        )

        for api_name, results in api_report.get("resultados", {}).items():
            ok = sum(1 for value in results.values() if isinstance(value, dict) and value.get("estado") in {"OK", "RAW_DESCARGADO", "XLS_DESCARGADO"})
            err = sum(1 for value in results.values() if isinstance(value, dict) and value.get("estado") in {"ERROR", "NO_ENCONTRADO", "SIN_DATOS"})
            manual = sum(1 for value in results.values() if isinstance(value, dict) and value.get("estado") == "MANUAL")
            status = "OK" if ok and not err else "ERROR" if err else "AVISO"
            rows.append(health_row(f"api_{api_name}", f"{ok} ok / {err} err / {manual} manual", status, "Resultado por conector."))

    if clean_report:
        clean_errors = [
            item for item in clean_report.get("resultados", [])
            if item.get("estado") not in {"OK", "SIN_DATOS"}
        ]
        rows.append(
            health_row(
                "cleaning_status",
                len(clean_errors),
                "OK" if not clean_errors else "REVISAR",
                "Transformaciones de limpieza con estado distinto de OK/SIN_DATOS.",
            )
        )

    return rows


def build_data_quality(clean_inventory: list[dict[str, Any]], column_profile: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in column_profile:
        grouped.setdefault(item["dataset"], []).append(item)

    inventory_by_dataset = {item["dataset"]: item for item in clean_inventory}
    rows = []
    for dataset, columns in grouped.items():
        inventory = inventory_by_dataset[dataset]
        total_cells = sum(int(column["non_null"]) + int(column["nulls"]) for column in columns)
        null_cells = sum(int(column["nulls"]) for column in columns)
        completeness = 1 - (null_cells / total_cells if total_cells else 0)
        numeric_columns = sum(1 for column in columns if int(column["numeric_non_null"]) > 0)
        useful_numeric_ratio = numeric_columns / len(columns) if columns else 0
        date_candidates = split_semicolon(inventory.get("date_candidates", ""))
        geo_candidates = split_semicolon(inventory.get("geo_candidates", ""))

        df = pd.read_csv(CLEAN_DIR / dataset, low_memory=False)
        duplicate_rows = int(df.duplicated().sum())
        duplicate_ratio = duplicate_rows / len(df) if len(df) else 0
        empty_columns = sum(1 for column in columns if int(column["non_null"]) == 0)
        high_null_columns = sum(1 for column in columns if float(column["null_pct"]) >= 0.5)

        score = 100
        score -= min(35, (1 - completeness) * 45)
        score -= min(20, duplicate_ratio * 100)
        if not date_candidates:
            score -= 8
        if not geo_candidates and dataset.startswith("bcn_"):
            score -= 8
        if useful_numeric_ratio == 0:
            score -= 12
        score -= min(10, high_null_columns)
        score = max(0, round(score, 1))

        flags = []
        if completeness < 0.75:
            flags.append("muchos_nulos")
        if duplicate_ratio > 0.05:
            flags.append("duplicados")
        if not date_candidates:
            flags.append("sin_fecha_clara")
        if not geo_candidates and dataset.startswith("bcn_"):
            flags.append("sin_geo_clara")
        if useful_numeric_ratio == 0:
            flags.append("sin_valor_numerico")
        if high_null_columns:
            flags.append(f"{high_null_columns}_columnas_muy_nulas")

        rows.append(
            {
                "dataset": dataset,
                "rows": int(inventory["rows"]),
                "columns": int(inventory["columns"]),
                "completeness_pct": round(completeness * 100, 2),
                "duplicate_rows": duplicate_rows,
                "duplicate_pct": round(duplicate_ratio * 100, 2),
                "numeric_columns": numeric_columns,
                "date_candidate_count": len(date_candidates),
                "geo_candidate_count": len(geo_candidates),
                "empty_columns": empty_columns,
                "high_null_columns": high_null_columns,
                "quality_score": score,
                "quality_level": classify_quality_score(score),
                "flags": "; ".join(flags) if flags else "ok",
            }
        )

    return sorted(rows, key=lambda item: (item["quality_score"], -item["rows"]))


def build_indicator_quality() -> list[dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                source,
                dataset,
                variable,
                quality,
                COUNT(*) AS rows,
                SUM(CASE WHEN value IS NULL THEN 1 ELSE 0 END) AS null_values,
                SUM(CASE WHEN period IS NULL OR TRIM(period) = '' THEN 1 ELSE 0 END) AS missing_periods,
                COUNT(DISTINCT geo) AS geos,
                COUNT(DISTINCT period) AS periods,
                MIN(period) AS min_period,
                MAX(period) AS max_period
            FROM indicadores
            GROUP BY source, dataset, variable, quality
            ORDER BY rows DESC
            """
        ).fetchall()

    output = []
    for row in rows:
        item = dict(row)
        total = int(item["rows"])
        null_values = int(item["null_values"] or 0)
        missing_periods = int(item["missing_periods"] or 0)
        score = 100
        score -= min(45, (null_values / total) * 100 if total else 0)
        score -= min(25, (missing_periods / total) * 100 if total else 0)
        if item["quality"] == "media":
            score -= 8
        elif item["quality"] == "baja":
            score -= 25
        elif item["quality"] not in {"alta", "media", "baja"}:
            score -= 15
        if int(item["periods"] or 0) <= 1 and total > 10:
            score -= 8
        item["quality_score"] = max(0, round(score, 1))
        item["quality_level"] = classify_quality_score(item["quality_score"])
        output.append(item)
    return output


def build_null_recommendations(column_profile: list[dict[str, Any]]) -> list[dict[str, Any]]:
    key_terms = [
        "id",
        "codi",
        "codigo",
        "fecha",
        "data",
        "period",
        "anio",
        "any",
        "mes",
        "valor",
        "value",
        "import",
        "precio",
        "lat",
        "lon",
        "geo",
        "utm",
        "barri",
        "barrio",
        "districte",
        "distrito",
        "municipio",
        "provincia",
        "variable",
        "fuente",
    ]
    rows = []
    for item in column_profile:
        column = str(item["column"])
        lower = column.lower()
        null_pct = float(item["null_pct"])
        numeric_non_null = int(item["numeric_non_null"])
        unique = int(item["unique"])
        non_null = int(item["non_null"])
        is_key_like = any(term in lower for term in key_terms)

        if null_pct >= 0.95 and not is_key_like:
            action = "eliminar_columna"
            reason = "Mas del 95% de nulos y no parece columna clave."
        elif null_pct >= 0.80 and not is_key_like:
            action = "revisar_columna"
            reason = "Muchos nulos; conservar solo si aporta contexto metodologico."
        elif null_pct >= 0.50:
            action = "conservar_con_cautela" if is_key_like else "revisar_columna"
            reason = "Nulidad alta, pero puede aportar informacion parcial."
        elif non_null == 0:
            action = "eliminar_columna"
            reason = "Columna completamente vacia."
        elif unique <= 1 and not is_key_like and numeric_non_null == 0:
            action = "revisar_constante"
            reason = "Columna casi constante; puede no aportar variabilidad."
        else:
            action = "conservar"
            reason = "Nulidad manejable o columna relevante."

        rows.append(
            {
                "dataset": item["dataset"],
                "column": column,
                "non_null": non_null,
                "nulls": int(item["nulls"]),
                "null_pct": round(null_pct * 100, 2),
                "unique": unique,
                "numeric_non_null": numeric_non_null,
                "key_like": is_key_like,
                "recommended_action": action,
                "reason": reason,
                "sample": item.get("sample", ""),
            }
        )
    return sorted(rows, key=lambda row: (-row["null_pct"], row["dataset"], row["column"]))


def build_detail_correlations() -> list[dict[str, Any]]:
    rows = []
    ignore_terms = ["id", "codi", "codigo", "lat", "lon", "utm", "x_", "y_", "zip", "postal", "seccion", "censal"]
    for path in sorted(CLEAN_DIR.glob("*.csv")):
        if path.name == "indicadores_limpios.csv":
            continue
        df = pd.read_csv(path, low_memory=False)
        numeric = pd.DataFrame()
        for column in df.columns:
            lower = column.lower()
            if any(term in lower for term in ignore_terms):
                continue
            series = pd.to_numeric(df[column], errors="coerce")
            if series.notna().sum() >= 20 and series.nunique(dropna=True) > 3:
                numeric[column] = series
        if numeric.shape[1] < 2:
            continue
        corr = numeric.corr(method="pearson", min_periods=20)
        for i, left in enumerate(corr.columns):
            for right in corr.columns[i + 1:]:
                value = corr.loc[left, right]
                if pd.isna(value) or abs(value) < 0.65:
                    continue
                overlap = int(numeric[[left, right]].dropna().shape[0])
                rows.append(
                    {
                        "dataset": path.name,
                        "left_column": left,
                        "right_column": right,
                        "correlation": round(float(value), 4),
                        "abs_correlation": round(abs(float(value)), 4),
                        "overlap_rows": overlap,
                        "interpretation": interpret_correlation(value),
                    }
                )
    return sorted(rows, key=lambda row: (-row["abs_correlation"], row["dataset"]))


def build_indicator_correlations() -> list[dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(
            """
            SELECT source, dataset, variable, geo, period, value
            FROM indicadores
            WHERE value IS NOT NULL
              AND period IS NOT NULL
              AND TRIM(period) != ''
            """,
            conn,
        )
    if df.empty:
        return []

    df["period_key"] = df["period"].map(period_to_month)
    df = df.dropna(subset=["period_key"])
    df["series"] = df["source"].astype(str) + " | " + df["dataset"].astype(str) + " | " + df["variable"].astype(str)
    grouped = df.groupby(["period_key", "series"], as_index=False)["value"].mean()
    pivot = grouped.pivot_table(index="period_key", columns="series", values="value", aggfunc="mean")
    valid_columns = [column for column in pivot.columns if pivot[column].notna().sum() >= 12 and pivot[column].nunique(dropna=True) > 3]
    pivot = pivot[valid_columns]
    if pivot.shape[1] < 2:
        return []

    corr = pivot.corr(method="pearson", min_periods=12)
    rows = []
    for i, left in enumerate(corr.columns):
        for right in corr.columns[i + 1:]:
            value = corr.loc[left, right]
            if pd.isna(value) or abs(value) < 0.75:
                continue
            overlap = int(pivot[[left, right]].dropna().shape[0])
            if overlap < 12:
                continue
            rows.append(
                {
                    "left_series": left,
                    "right_series": right,
                    "correlation": round(float(value), 4),
                    "abs_correlation": round(abs(float(value)), 4),
                    "overlap_periods": overlap,
                    "interpretation": interpret_correlation(value),
                    "warning": "Correlacion temporal exploratoria; no implica causalidad.",
                }
            )
    return sorted(rows, key=lambda row: -row["abs_correlation"])


def period_to_month(value: Any) -> str | None:
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    quarter_match = pd.Series([text]).str.extract(r"^(20\d{2})-T([1-4])$").iloc[0]
    if not quarter_match.isna().any():
        year = int(quarter_match[0])
        quarter = int(quarter_match[1])
        month = quarter * 3
        return f"{year:04d}-{month:02d}"
    timestamp = pd.to_datetime(text, errors="coerce", utc=True)
    if pd.isna(timestamp):
        if len(text) >= 7 and text[:4].isdigit() and text[4] == "-":
            return text[:7]
        if len(text) == 4 and text.isdigit():
            return f"{text}-12"
        return None
    return timestamp.strftime("%Y-%m")


def interpret_correlation(value: float) -> str:
    direction = "positiva" if value > 0 else "negativa"
    strength = "muy fuerte" if abs(value) >= 0.9 else "fuerte"
    return f"{direction} {strength}"


def classify_quality_score(score: float) -> str:
    if score >= 85:
        return "alta"
    if score >= 70:
        return "media"
    if score >= 50:
        return "revisar"
    return "baja"


def split_semicolon(value: str) -> list[str]:
    return [item.strip() for item in str(value).split(";") if item.strip()]


def health_row(metric: str, value: Any, status: str, note: str) -> dict[str, Any]:
    return {
        "metric": metric,
        "value": value,
        "status": status,
        "note": note,
    }


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_report(
    clean_inventory,
    raw_inventory,
    sql_counts,
    detail_counts,
    opportunities,
    api_health,
    data_quality,
    indicator_quality,
    null_recommendations,
    detail_correlations,
    indicator_correlations,
) -> None:
    total_clean = sum(int(item["rows"]) for item in clean_inventory if item["dataset"] != "indicadores_limpios.csv")
    total_sql = sum(int(item["rows"]) for item in sql_counts)
    total_detail = sum(int(item["rows_loaded"]) for item in detail_counts)
    total_raw = sum(int(item["rows"] or 0) for item in raw_inventory if item["suffix"] in {".csv", ".json", ".gpkg"})
    blocking_statuses = [item for item in api_health if item["status"] == "ERROR"]
    general_status = "POSITIVO" if not blocking_statuses and total_sql >= 50000 and total_detail >= total_clean else "REVISAR"
    lines = [
        "# EDA datasets ISEU+",
        "",
        f"Generado: {datetime.now().isoformat(timespec='seconds')}",
        f"Estado general: {general_status}",
        "",
        "## Resumen",
        "",
        f"- Archivos raw perfilados: {len(raw_inventory)}",
        f"- Filas raw perfiladas: {total_raw:,}".replace(",", "."),
        f"- Datasets limpios perfilados: {len(clean_inventory)}",
        f"- Filas limpias sin contar `indicadores_limpios.csv`: {total_clean:,}".replace(",", "."),
        f"- Filas en SQLite `indicadores`: {total_sql:,}".replace(",", "."),
        f"- Filas en tablas detalle SQL: {total_detail:,}".replace(",", "."),
        f"- Tablas detalle SQL: {len(detail_counts)}",
        f"- Ratio SQL/limpio: {round(total_sql / total_clean, 4) if total_clean else 0}",
        "",
        "## Salud de APIs",
        "",
    ]

    for item in api_health:
        lines.append(f"- {item['status']} `{item['metric']}`: {item['value']} - {item['note']}")

    lines.extend([
        "",
        "## Principales Huecos De Indicadores",
        "",
    ])

    gaps = sorted(
        [row for row in opportunities if row["dataset"] != "indicadores_limpios.csv"],
        key=lambda row: int(row["missing_indicator_rows_approx"]),
        reverse=True,
    )
    for row in gaps[:10]:
        lines.append(
            f"- `{row['dataset']}`: {row['clean_rows']} filas limpias, {row['detail_rows']} en detalle SQL, {row['indicator_rows']} en indicadores. {row['proposal'] or 'Revisar transformacion.'}"
        )

    worst_quality = sorted(data_quality, key=lambda item: item["quality_score"])[:8]
    indicator_quality_counts = {}
    for item in indicator_quality:
        level = item["quality_level"]
        indicator_quality_counts[level] = indicator_quality_counts.get(level, 0) + int(item["rows"])

    lines.extend([
        "",
        "## Calidad De Datos",
        "",
        "Resumen de indicadores por nivel de calidad calculado:",
    ])

    for level, rows in sorted(indicator_quality_counts.items()):
        lines.append(f"- `{level}`: {rows:,} filas".replace(",", "."))

    lines.extend([
        "",
        "Datasets limpios con menor puntuacion de calidad:",
    ])

    for item in worst_quality:
        lines.append(
            f"- `{item['dataset']}`: score {item['quality_score']} ({item['quality_level']}), completitud {item['completeness_pct']}%, duplicados {item['duplicate_pct']}%, flags: {item['flags']}"
        )

    null_actions = {}
    for item in null_recommendations:
        action = item["recommended_action"]
        null_actions[action] = null_actions.get(action, 0) + 1
    drop_candidates = [item for item in null_recommendations if item["recommended_action"] == "eliminar_columna"]
    review_candidates = [
        item for item in null_recommendations
        if item["recommended_action"] in {"revisar_columna", "conservar_con_cautela"}
    ]

    lines.extend([
        "",
        "## Nulos Y Columnas",
        "",
    ])
    for action, count in sorted(null_actions.items()):
        lines.append(f"- `{action}`: {count} columnas")
    lines.append("")
    lines.append("Columnas candidatas a eliminar por nulos:")
    for item in drop_candidates[:12]:
        lines.append(f"- `{item['dataset']}.{item['column']}`: {item['null_pct']}% nulos. {item['reason']}")
    if not drop_candidates:
        lines.append("- Ninguna columna cumple criterio fuerte de eliminacion automatica.")
    lines.append("")
    lines.append("Columnas a revisar antes de eliminar:")
    for item in review_candidates[:12]:
        lines.append(f"- `{item['dataset']}.{item['column']}`: {item['null_pct']}% nulos. {item['reason']}")

    lines.extend([
        "",
        "## Correlaciones E Interacciones",
        "",
        "Correlaciones fuertes dentro de datasets detalle:",
    ])
    for item in detail_correlations[:12]:
        lines.append(
            f"- `{item['dataset']}`: `{item['left_column']}` vs `{item['right_column']}` = {item['correlation']} ({item['interpretation']}, n={item['overlap_rows']})"
        )
    if not detail_correlations:
        lines.append("- No se detectaron correlaciones internas fuertes con los umbrales actuales.")

    lines.append("")
    lines.append("Correlaciones fuertes entre indicadores:")
    for item in indicator_correlations[:12]:
        lines.append(
            f"- `{item['left_series']}` vs `{item['right_series']}` = {item['correlation']} ({item['interpretation']}, periodos={item['overlap_periods']})"
        )
    if not indicator_correlations:
        lines.append("- No se detectaron correlaciones entre indicadores con suficientes periodos comparables.")

    lines.extend([
        "",
        "## Archivos generados",
        "",
        "- `inventario_raw.csv`",
        "- `inventario_limpios.csv`",
        "- `perfil_columnas_limpios.csv`",
        "- `conteo_sql_indicadores.csv`",
        "- `conteo_sql_detalle.csv`",
        "- `oportunidades_sql.csv`",
        "- `salud_apis.csv`",
        "- `calidad_datasets.csv`",
        "- `calidad_indicadores.csv`",
        "- `nulos_columnas.csv`",
        "- `correlaciones_detalle.csv`",
        "- `correlaciones_indicadores.csv`",
        "",
        "## Lectura tecnica",
        "",
        "El cuello de botella no esta en SQLite, sino en la capa de transformacion a indicadores. Muchos datasets limpios son registros geograficos o administrativos; para aprovecharlos hay que agregarlos por fecha, barrio/distrito, tipo o fuente antes de insertarlos en la tabla analitica.",
    ])

    (OUT_DIR / "reporte_eda.md").write_text("\n".join(lines), encoding="utf-8")


def write_csv(rows: list[dict[str, Any]], filename: str) -> None:
    pd.DataFrame(rows).to_csv(OUT_DIR / filename, index=False, encoding="utf-8")


def first_samples(series: pd.Series, limit: int = 3) -> str:
    values = []
    for value in series.dropna().astype(str).head(limit):
        values.append(value.replace("\n", " ")[:120])
    return " | ".join(values)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
