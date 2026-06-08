from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASETS_DIR = PROJECT_ROOT / "pag_web" / "Procesos" / "Datasets"
CLEAN_DIR = DATASETS_DIR / "limpios"
DB_PATH = DATASETS_DIR / "iseu_datos.sqlite"
REPORT_PATH = DATASETS_DIR / "sqlite_carga.json"


SCHEMA = """
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

CREATE INDEX IF NOT EXISTS idx_indicadores_variable ON indicadores(variable);
CREATE INDEX IF NOT EXISTS idx_indicadores_dataset ON indicadores(dataset);
CREATE INDEX IF NOT EXISTS idx_indicadores_geo ON indicadores(geo);
CREATE INDEX IF NOT EXISTS idx_indicadores_period ON indicadores(period);

CREATE TABLE IF NOT EXISTS cargas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loaded_at TEXT NOT NULL,
    source_file TEXT NOT NULL,
    rows_loaded INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cargas_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loaded_at TEXT NOT NULL,
    table_name TEXT NOT NULL,
    source_file TEXT NOT NULL,
    rows_loaded INTEGER NOT NULL,
    columns_loaded INTEGER NOT NULL
);
"""


def main() -> None:
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    input_path = CLEAN_DIR / "indicadores_limpios.csv"
    if not input_path.exists():
        raise FileNotFoundError(
            f"No existe {input_path}. Ejecuta primero pag_web/Procesos/Limpieza/clean_datasets.py"
        )

    df = pd.read_csv(input_path, low_memory=False)
    expected = [
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
    for column in expected:
        if column not in df.columns:
            df[column] = ""
    df = df[expected]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])

    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM indicadores")
        df.to_sql("indicadores", conn, if_exists="append", index=False)
        conn.execute(
            "INSERT INTO cargas (loaded_at, source_file, rows_loaded) VALUES (?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), relative(input_path), int(len(df))),
        )
        detail_tables = load_detail_tables(conn)
        derived = build_derived_indicators(conn)
        if not derived.empty:
            derived = normalize_indicator_frame(derived)
            derived.to_sql("indicadores", conn, if_exists="append", index=False)
        counts = pd.read_sql_query(
            """
            SELECT source, COUNT(*) AS rows
            FROM indicadores
            GROUP BY source
            ORDER BY rows DESC
            """,
            conn,
        )

    report = {
        "loaded_at": datetime.now().isoformat(timespec="seconds"),
        "database": relative(DB_PATH),
        "source_file": relative(input_path),
        "rows_loaded": int(len(df)),
        "derived_indicator_rows_loaded": int(len(derived)),
        "rows_by_source": counts.to_dict(orient="records"),
        "detail_tables": detail_tables,
        "detail_rows_loaded": sum(item["rows_loaded"] for item in detail_tables),
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"SQLite creado/cargado: {DB_PATH}")
    print(f"Filas insertadas: {len(df)}")
    print(f"Indicadores derivados insertados: {len(derived)}")
    print(counts.to_string(index=False))
    print(f"Tablas detalle cargadas: {len(detail_tables)}")
    print(f"Filas detalle cargadas: {report['detail_rows_loaded']}")


def load_detail_tables(conn: sqlite3.Connection) -> list[dict]:
    loaded_at = datetime.now().isoformat(timespec="seconds")
    conn.execute("DELETE FROM cargas_detalle")
    results = []

    for path in sorted(CLEAN_DIR.glob("*.csv")):
        if path.name == "indicadores_limpios.csv":
            continue

        table_name = f"detalle_{safe_table_name(path.stem.replace('_limpio', '').replace('_limpios', ''))}"
        df = pd.read_csv(path, low_memory=False)
        df = prepare_detail_dataframe(df)
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        create_detail_indexes(conn, table_name, df.columns)
        conn.execute(
            """
            INSERT INTO cargas_detalle
                (loaded_at, table_name, source_file, rows_loaded, columns_loaded)
            VALUES (?, ?, ?, ?, ?)
            """,
            (loaded_at, table_name, relative(path), int(len(df)), int(len(df.columns))),
        )
        results.append(
            {
                "table_name": table_name,
                "source_file": relative(path),
                "rows_loaded": int(len(df)),
                "columns_loaded": int(len(df.columns)),
            }
        )

    return results


def build_derived_indicators(conn: sqlite3.Connection) -> pd.DataFrame:
    frames = [
        derive_mitma_municipal(conn),
        derive_bcn_licencias(conn),
        derive_bcn_zonas_verdes(conn),
        derive_bcn_seguridad(conn),
        derive_bcn_movilidad(conn),
        derive_bcn_equipamientos(conn),
        derive_bcn_transporte(conn),
        derive_bcn_turismo(conn),
        derive_bcn_aire(conn),
        derive_bcn_renta(conn),
        derive_bcn_locales_precio(conn),
        derive_bcn_compraventa_numero(conn),
        derive_bcn_compraventa_superficie(conn),
        derive_bcn_ruido_poblacion(conn),
        derive_bcn_terrazas(conn),
        derive_bcn_iae(conn),
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def derive_mitma_municipal(conn: sqlite3.Connection) -> pd.DataFrame:
    if not table_exists(conn, "detalle_mitma_precio_m2_vivienda"):
        return pd.DataFrame()
    prices = pd.read_sql_query(
        """
        SELECT
            'MITMA/MIVAU' AS source,
            'precio_m2_vivienda_municipios' AS dataset,
            'Precio vivienda m2' AS variable,
            'Valor tasado de vivienda total por municipio' AS metric,
            municipio || ', ' || provincia AS geo,
            periodo AS period,
            precio_m2_eur AS value,
            'EUR/m2' AS unit,
            'alta' AS quality,
            'Indicador derivado desde detalle MITMA/MIVAU; conserva todos los municipios disponibles para comparativa territorial.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\mitma_precio_m2_vivienda_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_mitma_precio_m2_vivienda
        WHERE precio_m2_eur IS NOT NULL
        GROUP BY provincia, municipio, periodo, precio_m2_eur
        """,
        conn,
    )
    appraisals = pd.read_sql_query(
        """
        SELECT
            'MITMA/MIVAU' AS source,
            'tasaciones_vivienda_municipios' AS dataset,
            'Tasaciones vivienda' AS variable,
            'Numero de tasaciones de vivienda por municipio' AS metric,
            municipio || ', ' || provincia AS geo,
            periodo AS period,
            tasaciones AS value,
            'tasaciones' AS unit,
            'alta' AS quality,
            'Indicador derivado desde detalle MITMA/MIVAU; permite medir cobertura y actividad de tasacion por municipio.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\mitma_precio_m2_vivienda_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_mitma_precio_m2_vivienda
        WHERE tasaciones IS NOT NULL
        GROUP BY provincia, municipio, periodo, tasaciones
        """,
        conn,
    )
    return pd.concat([prices, appraisals], ignore_index=True)


def derive_bcn_licencias(conn: sqlite3.Connection) -> pd.DataFrame:
    if not table_exists(conn, "detalle_bcn_licencias"):
        return pd.DataFrame()
    by_district = pd.read_sql_query(
        """
        SELECT
            'Open Data BCN' AS source,
            'bcn_licencias_agregado' AS dataset,
            'Licencias comerciales' AS variable,
            'Locales de actividad economica por distrito' AS metric,
            COALESCE(nom_districte, 'Barcelona') AS geo,
            COALESCE(SUBSTR(data_revisio, 1, 7), '') AS period,
            COUNT(*) AS value,
            'locales' AS unit,
            'media' AS quality,
            'Conteo agregado desde censo de locales en planta baja; periodo basado en fecha de revision del registro.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\bcn_licencias_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_bcn_licencias
        GROUP BY nom_districte, SUBSTR(data_revisio, 1, 7)
        """,
        conn,
    )
    by_sector = pd.read_sql_query(
        """
        SELECT
            'Open Data BCN' AS source,
            'bcn_licencias_sector_agregado' AS dataset,
            'Densidad empresarial' AS variable,
            'Locales por sector de actividad y distrito' AS metric,
            COALESCE(nom_districte, 'Barcelona') || ' | ' || COALESCE(nom_sector_activitat, 'Sector no informado') AS geo,
            COALESCE(SUBSTR(data_revisio, 1, 7), '') AS period,
            COUNT(*) AS value,
            'locales' AS unit,
            'media' AS quality,
            'Conteo sectorial derivado desde censo de locales; util para dinamismo economico y entorno empresarial.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\bcn_licencias_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_bcn_licencias
        GROUP BY nom_districte, nom_sector_activitat, SUBSTR(data_revisio, 1, 7)
        """,
        conn,
    )
    return pd.concat([by_district, by_sector], ignore_index=True)


def derive_bcn_zonas_verdes(conn: sqlite3.Connection) -> pd.DataFrame:
    if not table_exists(conn, "detalle_bcn_zonas_verdes"):
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT
            'Open Data BCN' AS source,
            'bcn_zonas_verdes_agregado' AS dataset,
            'Zonas verdes por habitante' AS variable,
            'Elementos verdes registrados por barrio' AS metric,
            COALESCE(nom_barri, 'Barrio no informado') || ', ' || COALESCE(nom_districte, 'Distrito no informado') AS geo,
            SUBSTR(MAX(extraido_en), 1, 10) AS period,
            COUNT(*) AS value,
            'elementos' AS unit,
            'media' AS quality,
            'Conteo de arbolado/elementos verdes. Pendiente normalizar por poblacion para ratio por habitante.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\bcn_zonas_verdes_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_bcn_zonas_verdes
        GROUP BY nom_districte, nom_barri
        """,
        conn,
    )


def derive_bcn_seguridad(conn: sqlite3.Connection) -> pd.DataFrame:
    if not table_exists(conn, "detalle_bcn_seguridad"):
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT
            'Open Data BCN' AS source,
            'bcn_seguridad_agregado' AS dataset,
            'Seguridad ciudadana' AS variable,
            'Accidentes gestionados por Guardia Urbana' AS metric,
            COALESCE(nom_districte, 'Distrito no informado') AS geo,
            printf('%04d-%02d', CAST(nk_any AS INTEGER), CAST(mes_any AS INTEGER)) AS period,
            COUNT(*) AS value,
            'accidentes' AS unit,
            'media' AS quality,
            'Conteo mensual por distrito desde registros de accidentes; pendiente normalizar por poblacion.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\bcn_seguridad_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_bcn_seguridad
        WHERE nk_any IS NOT NULL AND mes_any IS NOT NULL
        GROUP BY nom_districte, nk_any, mes_any
        """,
        conn,
    )


def derive_bcn_movilidad(conn: sqlite3.Connection) -> pd.DataFrame:
    if not table_exists(conn, "detalle_bcn_movilidad"):
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT
            'Open Data BCN' AS source,
            'bcn_movilidad_agregado' AS dataset,
            'Movilidad urbana' AS variable,
            'Media diaria de bicicletas Bicing en uso' AS metric,
            'Barcelona' AS geo,
            SUBSTR(datetime, 1, 10) AS period,
            AVG(CAST(bikesinusage AS REAL)) AS value,
            'bicicletas' AS unit,
            'media' AS quality,
            'Media diaria derivada desde uso de Bicing; proxy parcial de movilidad urbana.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\bcn_movilidad_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_bcn_movilidad
        WHERE bikesinusage IS NOT NULL
        GROUP BY SUBSTR(datetime, 1, 10)
        """,
        conn,
    )


def derive_bcn_equipamientos(conn: sqlite3.Connection) -> pd.DataFrame:
    if not table_exists(conn, "detalle_bcn_equipamientos"):
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT
            'Open Data BCN' AS source,
            'bcn_equipamientos_agregado' AS dataset,
            'Acceso a educacion' AS variable,
            'Equipamientos educativos por distrito y tipo' AS metric,
            COALESCE(addresses_district_name, 'Distrito no informado') || ' | ' || COALESCE(secondary_filters_name, 'Tipo no informado') AS geo,
            SUBSTR(MAX(extraido_en), 1, 10) AS period,
            COUNT(DISTINCT COALESCE(register_id, id)) AS value,
            'equipamientos' AS unit,
            'media' AS quality,
            'Conteo derivado desde dataset de equipamientos educativos; pendiente cruzar con poblacion.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\bcn_equipamientos_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_bcn_equipamientos
        GROUP BY addresses_district_name, secondary_filters_name
        """,
        conn,
    )


def derive_bcn_transporte(conn: sqlite3.Connection) -> pd.DataFrame:
    if not table_exists(conn, "detalle_bcn_transporte"):
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT
            'Open Data BCN' AS source,
            'bcn_transporte_tarifas' AS dataset,
            'Transporte publico coste' AS variable,
            COALESCE(desc_curta, descripcio, 'Tarifa movilidad') AS metric,
            'Barcelona' AS geo,
            SUBSTR(MAX(extraido_en), 1, 10) AS period,
            import_fraccio AS value,
            'EUR/fraccion' AS unit,
            'media' AS quality,
            'Tarifa de movilidad urbana derivada desde Open Data BCN.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\bcn_transporte_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_bcn_transporte
        WHERE import_fraccio IS NOT NULL
        GROUP BY id_tarifa, desc_curta, descripcio, import_fraccio
        """,
        conn,
    )


def derive_bcn_turismo(conn: sqlite3.Connection) -> pd.DataFrame:
    if not table_exists(conn, "detalle_bcn_turismo"):
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT
            'Open Data BCN' AS source,
            'bcn_turismo_agregado' AS dataset,
            'Turismo (nº visitantes)' AS variable,
            'Alojamientos turisticos por distrito y categoria' AS metric,
            COALESCE(addresses_district_name, 'Distrito no informado') || ' | ' || COALESCE(secondary_filters_name, 'Categoria no informada') AS geo,
            SUBSTR(MAX(extraido_en), 1, 10) AS period,
            COUNT(DISTINCT COALESCE(register_id, id)) AS value,
            'alojamientos' AS unit,
            'media' AS quality,
            'Conteo de alojamientos/hoteles; proxy de capacidad turistica, no numero de visitantes.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\bcn_turismo_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_bcn_turismo
        GROUP BY addresses_district_name, secondary_filters_name
        """,
        conn,
    )


def derive_bcn_aire(conn: sqlite3.Connection) -> pd.DataFrame:
    if not table_exists(conn, "detalle_bcn_aire"):
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT
            'Open Data BCN' AS source,
            'bcn_aire_rangos' AS dataset,
            'Calidad del aire' AS variable,
            'Tramos del mapa de inmisiones por rango' AS metric,
            COALESCE(rang, 'Rango no informado') AS geo,
            SUBSTR(MAX(extraido_en), 1, 10) AS period,
            COUNT(*) AS value,
            'tramos' AS unit,
            'baja' AS quality,
            'Conteo de tramos por rango de mapa de inmisiones; no equivale a medicion temporal de estaciones.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\bcn_aire_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_bcn_aire
        GROUP BY rang
        """,
        conn,
    )


def derive_bcn_renta(conn: sqlite3.Connection) -> pd.DataFrame:
    if not table_exists(conn, "detalle_bcn_renta"):
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT
            'Open Data BCN' AS source,
            'bcn_renta' AS dataset,
            'Ingreso disponible per capita' AS variable,
            'Renta disponible de los hogares per capita por seccion censal' AS metric,
            COALESCE(nom_barri, 'Barrio no informado') || ', ' || COALESCE(nom_districte, 'Distrito no informado') || ' | seccion ' || COALESCE(CAST(seccio_censal AS TEXT), '') AS geo,
            CAST(any AS TEXT) AS period,
            import_euros AS value,
            'EUR/persona' AS unit,
            'alta' AS quality,
            'Renta disponible per capita por seccion censal desde Open Data BCN.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\bcn_renta_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_bcn_renta
        WHERE import_euros IS NOT NULL
        GROUP BY nom_districte, nom_barri, seccio_censal, any, import_euros
        """,
        conn,
    )


def derive_bcn_locales_precio(conn: sqlite3.Connection) -> pd.DataFrame:
    if not table_exists(conn, "detalle_bcn_locales_precio"):
        return pd.DataFrame()
    df = pd.read_sql_query("SELECT * FROM detalle_bcn_locales_precio", conn)
    year_columns = {
        "doszerozerovuit": "2008",
        "doszerozeronou": "2009",
        "doszerodeu": "2010",
        "doszeroonze": "2011",
    }
    frames = []
    for column, year in year_columns.items():
        if column not in df:
            continue
        frame = pd.DataFrame(
            {
                "source": "Open Data BCN",
                "dataset": "bcn_locales_precio",
                "variable": "Precio alquiler comercial",
                "metric": "Precio estimado de locales comerciales por barrio",
                "geo": df.get("barris", "Barcelona"),
                "period": year,
                "value": pd.to_numeric(df[column], errors="coerce"),
                "unit": "EUR/m2",
                "quality": "media",
                "notes": "Serie historica de precio estimado de locales; fuente antigua con cambio metodologico.",
                "raw_file": "pag_web\\Procesos\\Datasets\\limpios\\bcn_locales_precio_limpio.csv",
                "extracted_at": df.get("extraido_en", ""),
            }
        )
        frames.append(frame)
    return pd.concat(frames, ignore_index=True).dropna(subset=["value"]) if frames else pd.DataFrame()


def derive_bcn_compraventa_numero(conn: sqlite3.Connection) -> pd.DataFrame:
    if not table_exists(conn, "detalle_bcn_compraventa_numero"):
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT
            'Open Data BCN' AS source,
            'bcn_compraventa_numero' AS dataset,
            'Compraventa inmobiliaria' AS variable,
            'Transacciones inmobiliarias por barrio y uso' AS metric,
            COALESCE(nom_barri, 'Barrio no informado') || ', ' || COALESCE(nom_districte, 'Distrito no informado') || ' | ' || COALESCE(tipologia_us_desc, 'Uso no informado') AS geo,
            printf('%04d-%02d', CAST(any AS INTEGER), CAST(mes AS INTEGER)) AS period,
            CAST(REPLACE(nombre, ',', '.') AS REAL) AS value,
            'transacciones' AS unit,
            'alta' AS quality,
            'Numero de transmisiones inmobiliarias por compraventa segun registros notariales.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\bcn_compraventa_numero_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_bcn_compraventa_numero
        WHERE nombre IS NOT NULL AND nombre NOT IN ('..', '')
        GROUP BY nom_districte, nom_barri, tipologia_us_desc, any, mes, nombre
        """,
        conn,
    )


def derive_bcn_compraventa_superficie(conn: sqlite3.Connection) -> pd.DataFrame:
    if not table_exists(conn, "detalle_bcn_compraventa_superficie"):
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT
            'Open Data BCN' AS source,
            'bcn_compraventa_superficie' AS dataset,
            'Superficie inmobiliaria transmitida' AS variable,
            'Superficie transmitida por compraventa y uso' AS metric,
            COALESCE(nom_barri, 'Barrio no informado') || ', ' || COALESCE(nom_districte, 'Distrito no informado') || ' | ' || COALESCE(tipologia_us_desc, 'Uso no informado') AS geo,
            printf('%04d-%02d', CAST(any AS INTEGER), CAST(mes AS INTEGER)) AS period,
            superficie_m2 AS value,
            'm2' AS unit,
            'alta' AS quality,
            'Superficie inmobiliaria transmitida por compraventa segun registros notariales.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\bcn_compraventa_superficie_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_bcn_compraventa_superficie
        WHERE superficie_m2 IS NOT NULL
        GROUP BY nom_districte, nom_barri, tipologia_us_desc, any, mes, superficie_m2
        """,
        conn,
    )


def derive_bcn_ruido_poblacion(conn: sqlite3.Connection) -> pd.DataFrame:
    if not table_exists(conn, "detalle_bcn_ruido_poblacion"):
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT
            'Open Data BCN' AS source,
            'bcn_ruido_poblacion' AS dataset,
            'Ruido urbano' AS variable,
            'Porcentaje de poblacion expuesta por fuente y rango acustico' AS metric,
            COALESCE(font_soroll, 'Fuente no informada') || ' | ' || COALESCE(periode_horari, 'Periodo no informado') || ' | ' || COALESCE(rang, 'Rango no informado') AS geo,
            '2022' AS period,
            percentatge_poblacio_exposada AS value,
            '%' AS unit,
            'alta' AS quality,
            'Porcentaje de poblacion expuesta a niveles de ruido del mapa estrategico municipal.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\bcn_ruido_poblacion_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_bcn_ruido_poblacion
        WHERE percentatge_poblacio_exposada IS NOT NULL
          AND font_soroll IS NOT NULL
          AND periode_horari IS NOT NULL
          AND rang IS NOT NULL
        GROUP BY font_soroll, periode_horari, rang, percentatge_poblacio_exposada
        """,
        conn,
    )


def derive_bcn_terrazas(conn: sqlite3.Connection) -> pd.DataFrame:
    if not table_exists(conn, "detalle_bcn_terrazas"):
        return pd.DataFrame()
    by_area = pd.read_sql_query(
        """
        SELECT
            'Open Data BCN' AS source,
            'bcn_terrazas_superficie' AS dataset,
            'Terrazas actividad economica' AS variable,
            'Superficie autorizada de terrazas por barrio' AS metric,
            COALESCE(nom_barri, 'Barrio no informado') || ', ' || COALESCE(nom_districte, 'Distrito no informado') AS geo,
            SUBSTR(data_explo, 1, 10) AS period,
            SUM(superficie_ocupada) AS value,
            'm2' AS unit,
            'alta' AS quality,
            'Superficie ocupada por autorizaciones ordinarias de terrazas.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\bcn_terrazas_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_bcn_terrazas
        WHERE superficie_ocupada IS NOT NULL
        GROUP BY nom_districte, nom_barri, SUBSTR(data_explo, 1, 10)
        """,
        conn,
    )
    by_count = pd.read_sql_query(
        """
        SELECT
            'Open Data BCN' AS source,
            'bcn_terrazas_conteo' AS dataset,
            'Terrazas actividad economica' AS variable,
            'Autorizaciones de terrazas por barrio' AS metric,
            COALESCE(nom_barri, 'Barrio no informado') || ', ' || COALESCE(nom_districte, 'Distrito no informado') AS geo,
            SUBSTR(data_explo, 1, 10) AS period,
            COUNT(*) AS value,
            'autorizaciones' AS unit,
            'alta' AS quality,
            'Conteo de autorizaciones ordinarias de terrazas en espacio publico.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\bcn_terrazas_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_bcn_terrazas
        GROUP BY nom_districte, nom_barri, SUBSTR(data_explo, 1, 10)
        """,
        conn,
    )
    return pd.concat([by_area, by_count], ignore_index=True)


def derive_bcn_iae(conn: sqlite3.Connection) -> pd.DataFrame:
    if not table_exists(conn, "detalle_bcn_iae"):
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT
            'Open Data BCN' AS source,
            'bcn_iae' AS dataset,
            'Presion fiscal actividad economica' AS variable,
            COALESCE(descripcio_seccio, 'Seccion no informada') || ' | ' || COALESCE(descripcio_epigraf, 'Epigrafe no informado') AS metric,
            'Barcelona' AS geo,
            COALESCE(SUBSTR(resource_name, 1, 4), '2025') AS period,
            total_quota_ajuntament AS value,
            'EUR' AS unit,
            'alta' AS quality,
            'Cuota del padron del impuesto de actividades economicas por epigrafe.' AS notes,
            'pag_web\\Procesos\\Datasets\\limpios\\bcn_iae_limpio.csv' AS raw_file,
            MAX(extraido_en) AS extracted_at
        FROM detalle_bcn_iae
        WHERE total_quota_ajuntament IS NOT NULL
        GROUP BY descripcio_seccio, descripcio_epigraf, total_quota_ajuntament, SUBSTR(resource_name, 1, 4)
        """,
        conn,
    )


def normalize_indicator_frame(df: pd.DataFrame) -> pd.DataFrame:
    expected = [
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
    df = df.copy()
    for column in expected:
        if column not in df.columns:
            df[column] = ""
    df = df[expected]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["value"])


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def prepare_detail_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [safe_column_name(column) for column in df.columns]
    for column in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[column]):
            df[column] = df[column].astype(str)
    return df


def create_detail_indexes(conn: sqlite3.Connection, table_name: str, columns: pd.Index) -> None:
    candidates = [
        "dataset_key",
        "variable_iseu",
        "clave_config",
        "fecha",
        "periodo",
        "anio",
        "municipio",
        "provincia",
        "codi_districte",
        "nom_districte",
        "codi_barri",
        "nom_barri",
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
        text = f"t_{text}"
    return text


def safe_column_name(value: object) -> str:
    text = re.sub(r"[^0-9a-zA-Z_]+", "_", str(value)).strip("_").lower()
    if not text:
        text = "columna"
    if text[0].isdigit():
        text = f"c_{text}"
    return text


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
