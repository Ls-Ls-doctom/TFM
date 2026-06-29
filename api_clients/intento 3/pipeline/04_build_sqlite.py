from __future__ import annotations

import re
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from _common import BASE_DIR, GOLD_COLUMNS, GOLD_DIR, REPORTS_DIR, SILVER_DIR, ensure_dirs, now, relative, sqlite_connect, write_json


DB_PATH = GOLD_DIR / "iseu_indicadores.sqlite"
WEB_DB_PATH = BASE_DIR.parents[1] / "pag_web" / "Procesos" / "Datasets" / "iseu_datos.sqlite"
WEB_REPORT_PATH = WEB_DB_PATH.with_name("sqlite_carga.json")

INDICADORES_COLUMNS = [
    "source",
    "dataset",
    "variable",
    "metric",
    "geo",
    "period",
    "value",
    "unit",
    "quality",
    "notes",
    "raw_file",
    "extracted_at",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT NOT NULL,
    district TEXT,
    variable TEXT NOT NULL,
    value REAL NOT NULL,
    date TEXT NOT NULL,
    source TEXT NOT NULL,
    quality_score INTEGER,
    category TEXT,
    unit TEXT
);

CREATE INDEX IF NOT EXISTS idx_indicators_city ON indicators(city);
CREATE INDEX IF NOT EXISTS idx_indicators_variable ON indicators(variable);
CREATE INDEX IF NOT EXISTS idx_indicators_date ON indicators(date);
CREATE INDEX IF NOT EXISTS idx_indicators_category ON indicators(category);

CREATE TABLE IF NOT EXISTS indicator_catalog (
    variable TEXT PRIMARY KEY,
    category TEXT,
    unit TEXT,
    sources TEXT,
    cities TEXT,
    rows INTEGER
);

CREATE TABLE IF NOT EXISTS load_report (
    loaded_at TEXT,
    source_file TEXT,
    rows_loaded INTEGER
);

CREATE TABLE IF NOT EXISTS indicadores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    dataset TEXT,
    variable TEXT,
    metric TEXT,
    geo TEXT,
    period TEXT,
    value REAL,
    unit TEXT,
    quality TEXT,
    notes TEXT,
    raw_file TEXT,
    extracted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_indicadores_source ON indicadores(source);
CREATE INDEX IF NOT EXISTS idx_indicadores_variable ON indicadores(variable);
CREATE INDEX IF NOT EXISTS idx_indicadores_dataset ON indicadores(dataset);
CREATE INDEX IF NOT EXISTS idx_indicadores_geo ON indicadores(geo);
CREATE INDEX IF NOT EXISTS idx_indicadores_period ON indicadores(period);

CREATE TABLE IF NOT EXISTS semantic_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    layer TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source TEXT NOT NULL,
    dataset TEXT,
    city TEXT,
    district TEXT,
    neighborhood TEXT,
    geo TEXT,
    period TEXT,
    variable TEXT NOT NULL,
    metric TEXT,
    value REAL NOT NULL,
    unit TEXT,
    category TEXT,
    granularity TEXT,
    quality TEXT,
    source_file TEXT,
    notes TEXT,
    extracted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_semantic_city ON semantic_observations(city);
CREATE INDEX IF NOT EXISTS idx_semantic_variable ON semantic_observations(variable);
CREATE INDEX IF NOT EXISTS idx_semantic_period ON semantic_observations(period);
CREATE INDEX IF NOT EXISTS idx_semantic_source_table ON semantic_observations(source_table);

CREATE TABLE IF NOT EXISTS sql_table_catalog (
    table_name TEXT PRIMARY KEY,
    layer TEXT NOT NULL,
    source_file TEXT,
    rows_loaded INTEGER NOT NULL,
    columns_loaded INTEGER NOT NULL,
    description TEXT
);
"""

MUNICIPAL_INCOME_MEASURES = {
    "import_renda_bruta_eur": ("Renta bruta", "Renta bruta por seccion censal", "EUR", "economy"),
    "import_euros": ("Renta disponible", "Importe de renta disponible", "EUR", "economy"),
    "mediana_renda_eur": ("Renta mediana", "Mediana de renta", "EUR", "economy"),
    "mitjana_renda_eur": ("Renta media", "Media de renta", "EUR", "economy"),
    "index_gini": ("Desigualdad Gini", "Indice de Gini de renta", "indice", "economy"),
    "distribucio_p80_20": ("Desigualdad P80/P20", "Ratio P80/P20 de renta", "ratio", "economy"),
    "media_de_la_renta_por_unidad_de_consumo": ("Renta media por unidad de consumo", "Media de renta por unidad de consumo", "EUR", "economy"),
    "mediana_de_la_renta_por_unidad_de_consumo": ("Renta mediana por unidad de consumo", "Mediana de renta por unidad de consumo", "EUR", "economy"),
    "renta_bruta_media_por_hogar": ("Renta bruta media por hogar", "Renta bruta media por hogar", "EUR", "economy"),
    "renta_bruta_media_por_persona": ("Renta bruta media por persona", "Renta bruta media por persona", "EUR", "economy"),
    "renta_neta_media_por_hogar": ("Renta neta media por hogar", "Renta neta media por hogar", "EUR", "economy"),
    "renta_neta_media_por_persona": ("Renta neta media por persona", "Renta neta media por persona", "EUR", "economy"),
    "mitja_de_la_renda_per_unitat_de_consum": ("Renta media por unidad de consumo", "Mitja de la renda per unitat de consum", "EUR", "economy"),
    "mitjana_de_la_renda_per_unitat_de_consum": ("Renta mediana por unidad de consumo", "Mitjana de la renda per unitat de consum", "EUR", "economy"),
    "renta_bruta_media_por_hogar_renda_bruta_mitja_per_llar": ("Renta bruta media por hogar", "Renta bruta media por hogar", "EUR", "economy"),
    "renta_bruta_mitja_per_persona": ("Renta bruta media por persona", "Renta bruta mitja per persona", "EUR", "economy"),
    "renda_neta_mitja_per_llar": ("Renta neta media por hogar", "Renda neta mitja per llar", "EUR", "economy"),
    "renda_neta_mitja_per_persona": ("Renta neta media por persona", "Renda neta mitja per persona", "EUR", "economy"),
}


def main() -> int:
    ensure_dirs()
    indicators_path = GOLD_DIR / "indicators.csv"
    if not indicators_path.exists():
        raise FileNotFoundError(f"No existe {indicators_path}. Ejecuta primero pipeline/03_build_gold.py.")

    indicators = pd.read_csv(indicators_path, low_memory=False)
    for column in GOLD_COLUMNS:
        if column not in indicators.columns:
            indicators[column] = ""
    indicators = indicators[GOLD_COLUMNS].copy()
    indicators["value"] = pd.to_numeric(indicators["value"], errors="coerce")
    indicators["quality_score"] = pd.to_numeric(indicators["quality_score"], errors="coerce").fillna(0).astype(int)
    indicators = indicators.dropna(subset=["city", "variable", "value", "date", "source"])

    catalog_path = GOLD_DIR / "indicator_catalog.csv"
    catalog = pd.read_csv(catalog_path, low_memory=False) if catalog_path.exists() else build_catalog(indicators)

    silver_tables = load_silver_tables()
    semantic_observations = build_semantic_observations(indicators, silver_tables)
    indicadores = build_compat_indicadores(indicators, semantic_observations)
    table_catalog = build_table_catalog(indicators, catalog, silver_tables, semantic_observations, indicadores)

    with sqlite_connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM indicators")
        conn.execute("DELETE FROM indicator_catalog")
        conn.execute("DELETE FROM load_report")
        conn.execute("DELETE FROM indicadores")
        conn.execute("DELETE FROM semantic_observations")
        conn.execute("DELETE FROM sql_table_catalog")
        indicators.to_sql("indicators", conn, if_exists="append", index=False)
        catalog.to_sql("indicator_catalog", conn, if_exists="append", index=False)
        indicadores.to_sql("indicadores", conn, if_exists="append", index=False)
        semantic_observations.to_sql("semantic_observations", conn, if_exists="append", index=False)
        table_catalog.to_sql("sql_table_catalog", conn, if_exists="append", index=False)
        silver_detail_tables = write_silver_tables(conn, silver_tables)
        conn.execute(
            "INSERT INTO load_report (loaded_at, source_file, rows_loaded) VALUES (?, ?, ?)",
            (now(), relative(indicators_path), int(len(indicators))),
        )
        rows_by_city = read_sql(conn, "SELECT city, COUNT(*) AS rows FROM indicators GROUP BY city ORDER BY rows DESC")
        rows_by_variable = read_sql(
            conn, "SELECT variable, COUNT(*) AS rows FROM indicators GROUP BY variable ORDER BY rows DESC"
        )

    summary = {
        "loaded_at": now(),
        "database": relative(DB_PATH),
        "web_database": relative(WEB_DB_PATH),
        "source_file": relative(indicators_path),
        "rows_loaded": int(len(indicators)),
        "indicadores_rows_loaded": int(len(indicadores)),
        "semantic_observations_rows_loaded": int(len(semantic_observations)),
        "catalog_rows": int(len(catalog)),
        "silver_detail_tables": silver_detail_tables,
        "silver_detail_rows_loaded": int(sum(item["rows_loaded"] for item in silver_detail_tables)),
        "rows_by_city": rows_by_city,
        "rows_by_variable": rows_by_variable,
    }
    write_json(REPORTS_DIR / "sqlite_build.json", summary)
    copy_database_for_web(summary)

    print(f"SQLite Gold creado: {DB_PATH}")
    print(f"Filas indicators: {len(indicators)}")
    print(f"Filas indicadores/chatbot: {len(indicadores)}")
    print(f"Filas semantic_observations: {len(semantic_observations)}")
    print(f"Tablas Silver detalle: {len(silver_detail_tables)}")
    print(f"Filas Silver detalle: {summary['silver_detail_rows_loaded']}")
    print(f"SQLite web actualizado: {WEB_DB_PATH}")
    return 0


def load_silver_tables() -> dict[str, tuple[Path, pd.DataFrame]]:
    tables: dict[str, tuple[Path, pd.DataFrame]] = {}
    if not SILVER_DIR.exists():
        return tables
    for path in sorted(SILVER_DIR.rglob("*.csv")):
        table_name = "silver_" + safe_table_name(path.relative_to(SILVER_DIR).with_suffix("").as_posix())
        df = pd.read_csv(path, low_memory=False)
        df = prepare_sqlite_frame(df)
        tables[table_name] = (path, df)
    return tables


def write_silver_tables(conn: sqlite3.Connection, silver_tables: dict[str, tuple[Path, pd.DataFrame]]) -> list[dict[str, Any]]:
    detail_tables: list[dict[str, Any]] = []
    for table_name, (path, df) in silver_tables.items():
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        create_common_indexes(conn, table_name, df.columns)
        detail_tables.append(
            {
                "table_name": table_name,
                "source_file": relative(path),
                "rows_loaded": int(len(df)),
                "columns_loaded": int(len(df.columns)),
            }
        )
    return detail_tables


def build_semantic_observations(
    indicators: pd.DataFrame,
    silver_tables: dict[str, tuple[Path, pd.DataFrame]],
) -> pd.DataFrame:
    frames = [
        observations_from_gold(indicators),
        observations_from_ine(silver_tables),
        observations_from_sepe(silver_tables),
        observations_from_municipal_income(silver_tables),
        observations_from_municipal_mobility(silver_tables),
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return empty_observations()
    observations = pd.concat(frames, ignore_index=True, sort=False)
    expected = [
        "layer",
        "source_table",
        "source",
        "dataset",
        "city",
        "district",
        "neighborhood",
        "geo",
        "period",
        "variable",
        "metric",
        "value",
        "unit",
        "category",
        "granularity",
        "quality",
        "source_file",
        "notes",
        "extracted_at",
    ]
    for column in expected:
        if column not in observations.columns:
            observations[column] = ""
    observations = observations[expected].copy()
    observations["value"] = pd.to_numeric(observations["value"], errors="coerce")
    observations = observations.dropna(subset=["value"])
    for column in [col for col in expected if col != "value"]:
        observations[column] = observations[column].fillna("").astype(str)
    return observations


def observations_from_gold(indicators: pd.DataFrame) -> pd.DataFrame:
    if indicators.empty:
        return empty_observations()
    df = indicators.copy()
    proxy = df["source"].astype(str).str.contains("proxy", case=False, na=False)
    return pd.DataFrame(
        {
            "layer": "gold",
            "source_table": "indicators",
            "source": df["source"],
            "dataset": df["category"],
            "city": df["city"],
            "district": df["district"].fillna(""),
            "neighborhood": "",
            "geo": df.apply(lambda row: geo_text(row.get("city"), row.get("district"), ""), axis=1),
            "period": df["date"],
            "variable": df["variable"].map(variable_label),
            "metric": df["variable"].map(metric_label),
            "value": df["value"],
            "unit": df["unit"],
            "category": df["category"],
            "granularity": proxy.map(lambda value: "province_proxy" if value else "city"),
            "quality": df["quality_score"].map(quality_label),
            "source_file": "data_lake/gold/indicators.csv",
            "notes": proxy.map(
                lambda value: "Proxy provincial asociado a la ciudad; no debe interpretarse como medicion municipal."
                if value
                else "Indicador Gold con cobertura municipal o urbana comparable."
            ),
            "extracted_at": now(),
        }
    )


def observations_from_ine(silver_tables: dict[str, tuple[Path, pd.DataFrame]]) -> pd.DataFrame:
    frames = []
    specs = [
        ("silver_ine_poblacion_municipal", "population_total", "Poblacion total", "Poblacion total municipal", "persons"),
        (
            "silver_ine_poblacion_pais_nacimiento_total",
            "population_birthplace_total",
            "Poblacion por pais de nacimiento",
            "Poblacion total por pais de nacimiento",
            "persons",
        ),
    ]
    for table_name, value_col, variable, metric, unit in specs:
        item = silver_tables.get(table_name)
        if not item:
            continue
        path, df = item
        if value_col not in df.columns:
            continue
        values = pd.to_numeric(df[value_col], errors="coerce")
        frames.append(
            pd.DataFrame(
                {
                    "layer": "silver",
                    "source_table": table_name,
                    "source": "INE",
                    "dataset": table_name.removeprefix("silver_"),
                    "city": df.get("city", ""),
                    "district": "",
                    "neighborhood": "",
                    "geo": df.get("city", ""),
                    "period": df.get("date", ""),
                    "variable": variable,
                    "metric": metric,
                    "value": values,
                    "unit": unit,
                    "category": "demography",
                    "granularity": "city",
                    "quality": "alta",
                    "source_file": relative(path),
                    "notes": "Observacion Silver derivada de tabla INE limpia.",
                    "extracted_at": now(),
                }
            )
        )
    return pd.concat(frames, ignore_index=True) if frames else empty_observations()


def observations_from_sepe(silver_tables: dict[str, tuple[Path, pd.DataFrame]]) -> pd.DataFrame:
    frames = []
    variables = {
        "silver_sepe_paro_registrado": ("Paro registrado", "Personas en paro registrado", "persons"),
        "silver_sepe_contratos_registrados": ("Contratos registrados", "Contratos registrados por municipio", "contracts"),
        "silver_sepe_demandantes_empleo": ("Demandantes de empleo", "Demandantes de empleo por municipio", "persons"),
    }
    for table_name, (variable, metric, unit) in variables.items():
        item = silver_tables.get(table_name)
        if not item:
            continue
        path, df = item
        frames.append(
            pd.DataFrame(
                {
                    "layer": "silver",
                    "source_table": table_name,
                    "source": "SEPE",
                    "dataset": table_name.removeprefix("silver_"),
                    "city": df.get("city", ""),
                    "district": "",
                    "neighborhood": "",
                    "geo": df.get("city", ""),
                    "period": df.get("date", ""),
                    "variable": variable,
                    "metric": metric,
                    "value": pd.to_numeric(df.get("value"), errors="coerce"),
                    "unit": unit,
                    "category": "employment",
                    "granularity": "city",
                    "quality": "alta",
                    "source_file": relative(path),
                    "notes": "Registro Silver municipal filtrado a ciudades objetivo.",
                    "extracted_at": now(),
                }
            )
        )
    return pd.concat(frames, ignore_index=True) if frames else empty_observations()


def observations_from_municipal_income(silver_tables: dict[str, tuple[Path, pd.DataFrame]]) -> pd.DataFrame:
    item = silver_tables.get("silver_municipios_municipal_prioritario")
    if not item:
        return empty_observations()
    path, df = item
    if "dataset_family" not in df.columns:
        return empty_observations()
    income = df[df["dataset_family"].astype(str) == "income"].copy()
    frames = []
    for column, (variable, metric, unit, category) in MUNICIPAL_INCOME_MEASURES.items():
        if column not in income.columns:
            continue
        values = pd.to_numeric(income[column], errors="coerce")
        frame = pd.DataFrame(
            {
                "layer": "silver",
                "source_table": "silver_municipios_municipal_prioritario",
                "source": "Municipal Open Data",
                "dataset": "municipal_income",
                "city": income.get("city", ""),
                "district": income.get("nom_districte", ""),
                "neighborhood": income.get("nom_barri", ""),
                "geo": income.apply(lambda row: geo_text(row.get("city"), row.get("nom_districte"), row.get("nom_barri")), axis=1),
                "period": income.apply(infer_period_from_row, axis=1),
                "variable": variable,
                "metric": metric,
                "value": values,
                "unit": unit,
                "category": category,
                "granularity": income.apply(infer_granularity, axis=1),
                "quality": "alta",
                "source_file": income.get("source_file", relative(path)),
                "notes": f"Observacion economica municipal desde columna Silver `{column}`.",
                "extracted_at": now(),
            }
        )
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else empty_observations()


def observations_from_municipal_mobility(silver_tables: dict[str, tuple[Path, pd.DataFrame]]) -> pd.DataFrame:
    item = silver_tables.get("silver_municipios_municipal_prioritario")
    if not item:
        return empty_observations()
    path, df = item
    if "dataset_family" not in df.columns:
        return empty_observations()
    mobility = df[df["dataset_family"].astype(str) == "mobility"].copy()
    frames = []

    if {"city", "fecha", "tipo_gravedad"}.issubset(mobility.columns):
        accidents = mobility[mobility["fecha"].notna() & mobility["tipo_gravedad"].notna()].copy()
        if not accidents.empty:
            accidents["period"] = pd.to_datetime(accidents["fecha"], errors="coerce").dt.date.astype(str)
            grouped = (
                accidents.groupby(["city", "period", "tipo_gravedad", "tipo_accidente"], dropna=False)
                .size()
                .reset_index(name="value")
            )
            frames.append(
                pd.DataFrame(
                    {
                        "layer": "silver",
                        "source_table": "silver_municipios_municipal_prioritario",
                        "source": "Municipal Open Data",
                        "dataset": "municipal_accidents",
                        "city": grouped["city"],
                        "district": "",
                        "neighborhood": "",
                        "geo": grouped["city"],
                        "period": grouped["period"],
                        "variable": "Accidentes de trafico",
                        "metric": grouped.apply(
                            lambda row: "Accidentes por gravedad y tipo"
                            + optional_suffix(row.get("tipo_gravedad"))
                            + optional_suffix(row.get("tipo_accidente")),
                            axis=1,
                        ),
                        "value": grouped["value"],
                        "unit": "accidents",
                        "category": "mobility",
                        "granularity": "city_day",
                        "quality": "media",
                        "source_file": relative(path),
                        "notes": "Agregado diario desde registros municipales de movilidad para evitar exponer cada accidente como indicador final.",
                        "extracted_at": now(),
                    }
                )
            )

    if {"city", "genero", "edad"}.issubset(mobility.columns):
        users = mobility[mobility["edad"].notna()].copy()
        if not users.empty:
            grouped = users.groupby(["city", "source_file", "genero", "edad"], dropna=False).size().reset_index(name="value")
            frames.append(
                pd.DataFrame(
                    {
                        "layer": "silver",
                        "source_table": "silver_municipios_municipal_prioritario",
                        "source": "Municipal Open Data",
                        "dataset": "municipal_bike_users",
                        "city": grouped["city"],
                        "district": "",
                        "neighborhood": "",
                        "geo": grouped["city"],
                        "period": grouped["source_file"].map(infer_period_from_text),
                        "variable": "Usuarios bicicleta publica",
                        "metric": grouped.apply(lambda row: f"Usuarios por genero/edad: {row.get('genero', '')} {row.get('edad', '')}", axis=1),
                        "value": grouped["value"],
                        "unit": "users",
                        "category": "mobility",
                        "granularity": "city_demographic_group",
                        "quality": "media",
                        "source_file": grouped["source_file"],
                        "notes": "Agregado de usuarios de bicicleta publica municipal por genero y edad.",
                        "extracted_at": now(),
                    }
                )
            )

    return pd.concat(frames, ignore_index=True) if frames else empty_observations()


def build_compat_indicadores(indicators: pd.DataFrame, observations: pd.DataFrame) -> pd.DataFrame:
    rows = observations.rename(
        columns={
            "geo": "geo",
            "period": "period",
            "source_file": "raw_file",
        }
    ).copy()
    rows["notes"] = rows.apply(
        lambda row: f"{row.get('notes', '')} Capa: {row.get('layer', '')}; granularidad: {row.get('granularity', '')}; tabla: {row.get('source_table', '')}.",
        axis=1,
    )
    for column in INDICADORES_COLUMNS:
        if column not in rows.columns:
            rows[column] = ""
    rows = rows[INDICADORES_COLUMNS].copy()
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    rows = rows.dropna(subset=["source", "variable", "geo", "period", "value"])
    return rows.drop_duplicates()


def build_table_catalog(
    indicators: pd.DataFrame,
    catalog: pd.DataFrame,
    silver_tables: dict[str, tuple[Path, pd.DataFrame]],
    semantic_observations: pd.DataFrame,
    indicadores: pd.DataFrame,
) -> pd.DataFrame:
    rows = [
        {
            "table_name": "indicators",
            "layer": "gold",
            "source_file": "data_lake/gold/indicators.csv",
            "rows_loaded": int(len(indicators)),
            "columns_loaded": int(len(indicators.columns)),
            "description": "Indicadores Gold comparables por ciudad, variable y periodo.",
        },
        {
            "table_name": "indicator_catalog",
            "layer": "gold",
            "source_file": "data_lake/gold/indicator_catalog.csv",
            "rows_loaded": int(len(catalog)),
            "columns_loaded": int(len(catalog.columns)),
            "description": "Catalogo de variables Gold, fuentes, unidades y cobertura territorial.",
        },
        {
            "table_name": "semantic_observations",
            "layer": "silver_semantic",
            "source_file": "data_lake/silver",
            "rows_loaded": int(len(semantic_observations)),
            "columns_loaded": int(len(semantic_observations.columns)),
            "description": "Observaciones semanticas derivadas de Silver para consultas en lenguaje natural.",
        },
        {
            "table_name": "indicadores",
            "layer": "compatibility",
            "source_file": "data_lake/gold + data_lake/silver",
            "rows_loaded": int(len(indicadores)),
            "columns_loaded": int(len(indicadores.columns)),
            "description": "Tabla compatible con el chatbot local: une Gold y observaciones Silver consultables.",
        },
    ]
    for table_name, (path, df) in silver_tables.items():
        rows.append(
            {
                "table_name": table_name,
                "layer": "silver",
                "source_file": relative(path),
                "rows_loaded": int(len(df)),
                "columns_loaded": int(len(df.columns)),
                "description": f"Tabla Silver completa procedente de {relative(path)}.",
            }
        )
    return pd.DataFrame(rows)


def copy_database_for_web(summary: dict[str, Any]) -> None:
    WEB_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DB_PATH, WEB_DB_PATH)
    write_json(WEB_REPORT_PATH, summary)


def build_catalog(indicators: pd.DataFrame) -> pd.DataFrame:
    if indicators.empty:
        return pd.DataFrame(columns=["variable", "category", "unit", "sources", "cities", "rows"])
    return (
        indicators.groupby(["variable", "category", "unit"], as_index=False)
        .agg(
            sources=("source", lambda values: "|".join(sorted(set(map(str, values))))),
            cities=("city", lambda values: "|".join(sorted(set(map(str, values))))),
            rows=("variable", "size"),
        )
        .sort_values(["category", "variable"])
    )


def read_sql(conn: sqlite3.Connection, query: str) -> list[dict[str, object]]:
    return pd.read_sql_query(query, conn).to_dict(orient="records")


def prepare_sqlite_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [safe_column_name(column) for column in out.columns]
    for column in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[column]):
            out[column] = out[column].astype(str)
    return out


def create_common_indexes(conn: sqlite3.Connection, table_name: str, columns: pd.Index) -> None:
    candidates = [
        "city",
        "municipality_code",
        "date",
        "variable",
        "dataset_family",
        "source_file",
        "nom_districte",
        "nom_barri",
        "fecha",
        "tipo_gravedad",
        "genero",
    ]
    available = set(columns)
    for column in candidates:
        if column not in available:
            continue
        index_name = f"idx_{table_name}_{column}"[:60]
        conn.execute(f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ("{column}")')


def safe_table_name(value: str) -> str:
    text = re.sub(r"[^0-9a-zA-Z_]+", "_", value).strip("_").lower()
    if not text:
        return "dataset"
    if text[0].isdigit():
        return f"t_{text}"
    return text


def safe_column_name(value: object) -> str:
    text = re.sub(r"[^0-9a-zA-Z_]+", "_", str(value)).strip("_").lower()
    if not text:
        text = "column"
    if text[0].isdigit():
        text = f"c_{text}"
    return text


def empty_observations() -> pd.DataFrame:
    return pd.DataFrame()


def geo_text(city: object, district: object, neighborhood: object) -> str:
    parts = [clean_text(part) for part in (neighborhood, district, city) if clean_text(part)]
    return ", ".join(parts)


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text


def infer_period_from_row(row: pd.Series) -> str:
    for key in ("date", "fecha"):
        value = clean_text(row.get(key))
        if value:
            parsed = pd.to_datetime(value, errors="coerce")
            if not pd.isna(parsed):
                return parsed.date().isoformat()
            return value[:10]
    for key in ("any", "ano", "anio", "year", "periodo"):
        value = clean_text(row.get(key))
        match = re.search(r"(19\d{2}|20\d{2})", value)
        if match:
            return f"{match.group(1)}-01-01"
    return infer_period_from_text(row.get("source_file", ""))


def infer_period_from_text(value: object) -> str:
    text = clean_text(value)
    match = re.search(r"(19\d{2}|20\d{2})", text)
    return f"{match.group(1)}-01-01" if match else ""


def infer_granularity(row: pd.Series) -> str:
    if clean_text(row.get("seccio_censal")):
        return "census_section"
    if clean_text(row.get("nom_barri")):
        return "neighborhood"
    if clean_text(row.get("nom_districte")):
        return "district"
    return "city"


def optional_suffix(value: object) -> str:
    text = clean_text(value)
    return f" | {text}" if text else ""


def quality_label(score: object) -> str:
    try:
        number = int(score)
    except (TypeError, ValueError):
        return "media"
    if number >= 8:
        return "alta"
    if number >= 5:
        return "media"
    return "baja"


def variable_label(value: object) -> str:
    labels = {
        "population_total": "Poblacion total",
        "unemployed_registered": "Paro registrado",
        "contracts_registered": "Contratos registrados",
        "job_seekers": "Demandantes de empleo",
        "income": "Renta",
        "income_median": "Renta mediana",
        "income_per_household": "Renta por hogar",
        "income_per_person": "Renta por persona",
        "mobility_resources_records": "Registros de movilidad",
        "gini_inequality": "Desigualdad Gini",
        "inequality_p80p20": "Desigualdad P80/P20",
        "traffic_accidents": "Accidentes de trafico",
        "population_resident": "Poblacion residente",
        "median_age": "Edad mediana",
        "life_expectancy": "Esperanza de vida",
        "households_total": "Numero de hogares",
        "household_size": "Tamano medio del hogar",
        "vacant_dwellings_pct": "Viviendas vacias",
        "rent_mean_eur_m2_year": "Alquiler medio anual por m2",
        "rent_mean_monthly": "Alquiler medio mensual",
        "rent_median_monthly": "Mediana del alquiler mensual",
        "house_price_mean": "Precio medio de la vivienda",
        "house_price_mean_m2": "Precio medio de vivienda por m2",
        "unemployment_rate": "Tasa de desempleo",
        "activity_rate": "Tasa de actividad",
        "services_employment_share": "Empleo en servicios",
        "industry_employment_share": "Empleo en industria",
        "net_income_household": "Renta neta media por hogar",
        "net_income_per_capita": "Renta neta media por habitante",
        "net_income_consumption_unit": "Renta neta por unidad de consumo",
        "commute_car_pct": "Desplazamientos al trabajo en coche",
        "commute_walk_pct": "Desplazamientos al trabajo a pie",
        "commute_public_transport_pct": "Desplazamientos al trabajo en transporte publico",
        "commute_duration_minutes": "Duracion del desplazamiento al trabajo",
        "tourism_overnight_stays": "Pernoctaciones turisticas",
        "tourism_beds": "Plazas turisticas",
        "cpi_general_change_pct": "Variacion anual del IPC general",
        "cpi_food_change_pct": "Variacion anual del IPC de alimentos",
        "cpi_housing_energy_change_pct": "Variacion anual del IPC de vivienda y energia",
        "cpi_transport_change_pct": "Variacion anual del IPC de transporte",
        "cpi_hospitality_change_pct": "Variacion anual del IPC de restauracion y alojamiento",
        "rent_price_change_pct": "Variacion anual del precio del alquiler",
        "rent_price_index": "Indice del precio del alquiler",
        "business_local_units": "Locales empresariales activos",
        "business_local_units_no_employees": "Locales empresariales sin asalariados",
    }
    raw = str(value)
    return labels.get(raw, raw.replace("_", " ").capitalize())


def metric_label(value: object) -> str:
    labels = {
        "population_total": "Poblacion municipal total",
        "unemployed_registered": "Personas en paro registrado por ciudad y mes",
        "contracts_registered": "Contratos registrados por ciudad y mes",
        "job_seekers": "Demandantes de empleo por ciudad y mes",
        "income": "Indicador municipal de renta media",
        "income_median": "Indicador municipal de renta mediana",
        "income_per_household": "Renta por hogar",
        "income_per_person": "Renta por persona",
        "mobility_resources_records": "Numero de registros en recursos municipales de movilidad",
        "gini_inequality": "Indice de Gini de desigualdad de renta por ciudad y ano",
        "inequality_p80p20": "Ratio P80/P20 de desigualdad de renta por ciudad y ano",
        "traffic_accidents": "Accidentes de trafico registrados por ciudad y ano",
        "population_resident": "Poblacion residente anual de Indicadores Urbanos",
        "rent_mean_monthly": "Gasto medio mensual de alquiler de vivienda habitual",
        "rent_median_monthly": "Mediana mensual de alquiler de vivienda habitual",
        "house_price_mean": "Precio medio de compraventa de vivienda",
        "house_price_mean_m2": "Precio medio de compraventa por metro cuadrado",
        "unemployment_rate": "Porcentaje de poblacion activa desempleada",
        "activity_rate": "Tasa de actividad urbana",
        "services_employment_share": "Proporcion del empleo urbano en el sector servicios",
        "industry_employment_share": "Proporcion del empleo urbano en industria",
        "net_income_household": "Renta neta media anual de los hogares",
        "net_income_per_capita": "Renta neta media anual por habitante",
        "net_income_consumption_unit": "Renta neta media anual por unidad de consumo",
        "tourism_overnight_stays": "Numero anual de pernoctaciones turisticas",
        "tourism_beds": "Plazas disponibles en establecimientos turisticos",
        "cpi_general_change_pct": "Variacion de la media anual del IPC provincial general",
        "cpi_housing_energy_change_pct": "Variacion del IPC provincial de vivienda, agua, electricidad y gas",
        "rent_price_change_pct": "Variacion anual municipal del IPVA",
        "business_local_units": "Unidades locales activas en la provincia asociada",
    }
    raw = str(value)
    return labels.get(raw, variable_label(raw))


if __name__ == "__main__":
    raise SystemExit(main())
