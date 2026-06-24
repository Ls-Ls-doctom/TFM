from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.api.types import is_object_dtype, is_string_dtype


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DATA_DIR = PROJECT_ROOT / "api_clients" / "data"
DATASETS_DIR = PROJECT_ROOT / "pag_web" / "Procesos" / "Datasets"
CLEAN_DIR = DATASETS_DIR / "limpios"
REPORT_PATH = CLEAN_DIR / "catalogo_limpieza.json"


MOJIBAKE_REPLACEMENTS = {
    "Ã¡": "á",
    "Ã©": "é",
    "Ã­": "í",
    "Ã³": "ó",
    "Ãº": "ú",
    "Ã±": "ñ",
    "Ã¼": "ü",
    "Ã ": "à",
    "Ã¨": "è",
    "Ã²": "ò",
    "Ã§": "ç",
    "Ã": "Á",
    "Ã‰": "É",
    "Ã": "Í",
    "Ã“": "Ó",
    "Ãš": "Ú",
    "Ã‘": "Ñ",
    "Ãœ": "Ü",
    "Ã": "Í",
    "Âº": "º",
    "Âª": "ª",
    "Â·": "·",
    "â‚¬": "€",
    "â€“": "-",
    "â€”": "-",
    "â€™": "'",
    "â€œ": '"',
    "â€": '"',
}


LOW_VALUE_COLUMNS_BY_FILE = {
    "bcn_equipamientos_limpio.csv": [
        "addresses_roadtype_name",
        "addresses_type",
        "end_date",
        "estimated_dates",
        "start_date",
        "timetable",
    ],
    "bcn_turismo_limpio.csv": [
        "addresses_roadtype_name",
        "addresses_type",
        "end_date",
        "estimated_dates",
        "institution_name",
        "start_date",
        "timetable",
    ],
    "bcn_licencias_limpio.csv": [
        "nom_mercat",
        "nom_galeria",
        "nom_ccomercial",
        "lletra_inicial",
        "lletra_final",
    ],
    "bcn_zonas_verdes_limpio.csv": [
        "catalogacio",
        "tipus_aigua",
    ],
}


def main() -> None:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    report: list[dict[str, Any]] = []
    facts: list[pd.DataFrame] = []

    for cleaner in (
        clean_ine,
        clean_idescat,
        clean_ree,
        clean_sepe,
        clean_bcn_csvs,
        clean_mitma_xls,
        clean_alquiler_gpkg,
    ):
        result = cleaner()
        report.extend(result["report"])
        facts.extend(result["facts"])

    if facts:
        unified = pd.concat(facts, ignore_index=True)
        unified = unified.dropna(how="all")
        unified = drop_incomplete_indicators(unified)
        unified = unified.drop_duplicates()
        unified.to_csv(CLEAN_DIR / "indicadores_limpios.csv", index=False, encoding="utf-8")
        report.append(
            {
                "dataset": "indicadores_limpios",
                "estado": "OK",
                "filas": int(len(unified)),
                "salida": relative(CLEAN_DIR / "indicadores_limpios.csv"),
            }
        )
    else:
        report.append({"dataset": "indicadores_limpios", "estado": "SIN_DATOS", "filas": 0})

    payload = {
        "generado_en": datetime.now().isoformat(timespec="seconds"),
        "raw_data_dir": relative(RAW_DATA_DIR),
        "clean_dir": relative(CLEAN_DIR),
        "resultados": report,
    }
    REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for item in report if item.get("estado") == "OK")
    pending = sum(1 for item in report if item.get("estado") == "PENDIENTE")
    print(f"Limpieza terminada: {ok} OK | {pending} pendientes")
    print(f"Salida: {REPORT_PATH}")


def clean_ine() -> dict[str, Any]:
    path = RAW_DATA_DIR / "ine" / "ine_raw.csv"
    report: list[dict[str, Any]] = []
    if not path.exists():
        return missing("ine", path)

    df = read_csv(path)
    df = clean_dataframe(df)
    df["fecha"] = parse_ine_datetime(df.get("fecha"))
    df["valor"] = to_number(df.get("valor"))
    df["fuente"] = "INE"
    out = CLEAN_DIR / "ine_limpio.csv"
    write_clean_csv(df, out)

    geo_col = df["geo_config"].fillna("") if "geo_config" in df.columns else empty_series(df)
    geo_col = geo_col.mask(geo_col.astype(str).str.strip() == "", infer_geo_series(df.get("nombre", empty_series(df))))
    unit_col = df["unidad"].fillna("") if "unidad" in df.columns else ""
    facts = pd.DataFrame(
        {
            "source": "INE",
            "dataset": df.get("clave_config", ""),
            "variable": df.get("variable_iseu", ""),
            "metric": df.get("nombre", ""),
            "geo": geo_col,
            "period": df["fecha"].dt.date.astype(str),
            "value": df["valor"],
            "unit": unit_col,
            "quality": "media",
            "notes": "Serie INE normalizada desde API Tempus.",
            "raw_file": relative(path),
            "extracted_at": df.get("extraido_en", ""),
        }
    )
    facts = facts.dropna(subset=["value"])
    report.append(ok("ine", path, out, len(df), "Series temporales INE"))
    return {"report": report, "facts": [facts]}


def clean_idescat() -> dict[str, Any]:
    path = RAW_DATA_DIR / "idescat" / "idescat_raw.csv"
    report: list[dict[str, Any]] = []
    if not path.exists():
        return missing("idescat", path)

    df = read_csv(path)
    df = clean_dataframe(df)
    for column in ("barcelona", "comarca", "catalunya"):
        if column in df:
            df[column] = to_number(df[column])
    out = CLEAN_DIR / "idescat_limpio.csv"
    write_clean_csv(df, out)

    fact_frames: list[pd.DataFrame] = []
    for column, geo_label in (
        ("barcelona", "Barcelona"),
        ("comarca", "Barcelones"),
        ("catalunya", "Catalunya"),
    ):
        if column not in df:
            continue
        fact_frames.append(
            pd.DataFrame(
                {
                    "source": "Idescat",
                    "dataset": df.get("clave_config", ""),
                    "variable": df.get("variable_iseu", ""),
                    "metric": df.get("nombre", ""),
                    "geo": geo_label,
                    "period": df.get("referencia", ""),
                    "value": df.get(column, ""),
                    "unit": "",
                    "quality": "alta",
                    "notes": f"Indicador territorial extraido de Idescat ({geo_label}).",
                    "raw_file": relative(path),
                    "extracted_at": df.get("extraido_en", ""),
                }
            )
        )
    facts = pd.concat(fact_frames, ignore_index=True).dropna(subset=["value"]) if fact_frames else pd.DataFrame()
    report.append(ok("idescat", path, out, len(df), "Indicadores municipales Idescat"))
    return {"report": report, "facts": [facts]}


def clean_ree() -> dict[str, Any]:
    report: list[dict[str, Any]] = []
    facts: list[pd.DataFrame] = []

    configs = [
        ("ree_precios_raw.csv", "ree_precios_limpio.csv", "valor_eur_mwh", "Precio electricidad", "EUR/MWh"),
        ("ree_demanda_raw.csv", "ree_demanda_limpio.csv", "valor_mwh", "Demanda electrica", "MWh"),
    ]
    for raw_name, clean_name, value_column, default_variable, unit in configs:
        path = RAW_DATA_DIR / "ree" / raw_name
        if not path.exists():
            report.append({"dataset": raw_name, "estado": "SIN_DATOS", "entrada": str(path)})
            continue

        df = read_csv(path)
        df = clean_dataframe(df)
        df["fecha"] = pd.to_datetime(df.get("fecha"), errors="coerce", utc=True)
        df[value_column] = to_number(df.get(value_column))
        out = CLEAN_DIR / clean_name
        write_clean_csv(df, out)

        fact = pd.DataFrame(
            {
                "source": "REE",
                "dataset": raw_name.replace("_raw.csv", ""),
                "variable": df.get("variable_iseu", default_variable),
                "metric": df.get("concepto", default_variable),
                "geo": "España",
                "period": df["fecha"].astype(str),
                "value": df[value_column],
                "unit": unit,
                "quality": "media",
                "notes": "Dato energetico nacional usado como proxy para coste energetico.",
                "raw_file": relative(path),
                "extracted_at": df.get("extraido_en", ""),
            }
        )
        facts.append(fact.dropna(subset=["value"]))
        report.append(ok(raw_name, path, out, len(df), "Serie REE normalizada"))

    return {"report": report, "facts": facts}


def clean_sepe() -> dict[str, Any]:
    folder = RAW_DATA_DIR / "empleo"
    specs = [
        {
            "raw": folder / "sepe_paro_raw.csv",
            "out": CLEAN_DIR / "sepe_paro_limpio.csv",
            "dataset": "sepe_paro",
            "variable": "Paro registrado",
            "metric": "Paro registrado municipal total",
            "value_col": "paro_total",
            "unit": "personas",
            "note": "SEPE municipal; los valores '<5' se conservan como estimacion 2.5 y marca de censura.",
        },
        {
            "raw": folder / "sepe_contratos_raw.csv",
            "out": CLEAN_DIR / "sepe_contratos_limpio.csv",
            "dataset": "sepe_contratos",
            "variable": "Contratos registrados",
            "metric": "Contratos registrados municipales total",
            "value_col": "contratos_total",
            "unit": "contratos",
            "note": "SEPE municipal; contratos registrados por mes y municipio.",
        },
    ]

    report: list[dict[str, Any]] = []
    facts: list[pd.DataFrame] = []

    for spec in specs:
        path = spec["raw"]
        if not path.exists():
            report.extend(missing(spec["dataset"], path)["report"])
            continue

        df = clean_dataframe(read_csv(path))
        if "codigo_municipio" in df:
            df["codigo_municipio"] = df["codigo_municipio"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
        if spec["value_col"] in df:
            df[spec["value_col"]] = to_number(df[spec["value_col"]])
        if "es_total_provincia" in df:
            df["es_total_provincia"] = df["es_total_provincia"].astype(str).str.lower().isin({"true", "1", "si"})

        write_clean_csv(df, spec["out"])
        report.append(ok(spec["dataset"], path, spec["out"], len(df), "SEPE municipal normalizado desde XLS"))

        municipalities = df.copy()
        if "es_total_provincia" in municipalities:
            municipalities = municipalities[~municipalities["es_total_provincia"]]
        if spec["value_col"] not in municipalities:
            continue

        fact = pd.DataFrame(
            {
                "source": "SEPE",
                "dataset": spec["dataset"],
                "variable": spec["variable"],
                "metric": spec["metric"],
                "geo": municipalities.get("municipio", "") + ", " + municipalities.get("provincia", ""),
                "period": municipalities.get("periodo", ""),
                "value": municipalities.get(spec["value_col"], ""),
                "unit": spec["unit"],
                "quality": "alta",
                "notes": spec["note"],
                "raw_file": relative(path),
                "extracted_at": municipalities.get("extraido_en", ""),
            }
        ).dropna(subset=["value"])
        facts.append(fact)

    return {"report": report, "facts": facts}


def clean_bcn_csvs() -> dict[str, Any]:
    folder = RAW_DATA_DIR / "opendata_bcn"
    report: list[dict[str, Any]] = []
    facts: list[pd.DataFrame] = []
    if not folder.exists():
        return missing("opendata_bcn", folder)

    for path in sorted(folder.glob("bcn_*_raw.csv")):
        df = read_csv(path)
        df = clean_dataframe(df)
        out = CLEAN_DIR / path.name.replace("_raw.csv", "_limpio.csv")
        write_clean_csv(df, out)
        report.append(ok(path.stem, path, out, len(df), "CSV Open Data BCN normalizado"))

        value_col = first_existing(
            df,
            [
                "valor",
                "value",
                "import",
                "preu",
                "precio",
                "price",
                "numero",
                "nombre",
                "total",
                "renda",
                "income",
                "superficie",
                "area",
                "poblacio",
                "population",
                "quota",
                "cuota",
            ],
        )
        if value_col is None:
            continue
        fact = build_bcn_facts(df, path, value_col)
        if not fact.empty:
            facts.append(fact)

    return {"report": report, "facts": facts}


def build_bcn_facts(df: pd.DataFrame, path: Path, value_col: str) -> pd.DataFrame:
    dataset_key = path.stem.replace("_raw", "")
    if dataset_key == "bcn_ruido_poblacion":
        return build_bcn_noise_facts(df, path)

    values = to_number(df[value_col])
    geo = first_existing(df, ["nom_barri", "barri", "nom_districte", "districte", "addresses_district_name"])
    period = first_existing(df, ["data_referencia", "data_revisio", "data", "datetime", "fecha", "periodo", "any", "year", "mes", "extraido_en"])
    metric = first_existing(df, ["_variable_iseu", "variable_iseu", "nom", "name", "descripcio"])
    dataset = first_existing(df, ["_dataset_key", "dataset_key"])
    extracted_at = first_existing(df, ["_extraido_en", "extraido_en"])

    geo_values = df[geo].fillna("") if geo else empty_series(df)
    geo_values = geo_values.mask(geo_values.astype(str).str.strip() == "", "Barcelona")
    period_values = df[period].fillna("") if period else empty_series(df)
    if period == "extraido_en":
        period_values = period_values.astype(str).str.slice(0, 10)

    fact = pd.DataFrame(
        {
            "source": "Open Data BCN",
            "dataset": df[dataset] if dataset else path.stem.replace("_raw", ""),
            "variable": df[metric] if metric else path.stem.replace("_raw", ""),
            "metric": df[metric] if metric else path.stem.replace("_raw", ""),
            "geo": geo_values,
            "period": period_values,
            "value": values,
            "unit": "",
            "quality": "media",
            "notes": "Dato municipal normalizado; revisar si es proxy antes de usar en conclusiones.",
            "raw_file": relative(path),
            "extracted_at": df[extracted_at] if extracted_at else "",
        }
    )
    return fact.dropna(subset=["value"])


def build_bcn_noise_facts(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    value_columns = [column for column in ("percentatge_poblacio_exposada", "valor") if column in df.columns]
    if not value_columns:
        return pd.DataFrame()

    values = to_number(df[value_columns[0]])
    for value_column in value_columns[1:]:
        values = values.fillna(to_number(df[value_column]))
    source_noise = coalesce_columns(df, ["font_soroll", "concepte"], "Fuente no informada")
    time_slot = coalesce_columns(df, ["periode_horari"], "Periodo no informado")
    noise_range = coalesce_columns(df, ["rang", "rang_soroll"], "Rango no informado")
    district = coalesce_columns(df, ["nom_districte", "nom_districte_2"], "")
    neighborhood = coalesce_columns(df, ["nom_barri", "nom_barri_2", "barri"], "")
    extracted_at = first_existing(df, ["_extraido_en", "extraido_en"])

    geo = source_noise + " | " + time_slot + " | " + noise_range
    place = (neighborhood + ", " + district).str.strip(" ,")
    geo = geo.mask(place.astype(str).str.strip() != "", geo + " | " + place)

    fact = pd.DataFrame(
        {
            "source": "Open Data BCN",
            "dataset": "bcn_ruido_poblacion",
            "variable": "Ruido urbano",
            "metric": "Porcentaje de poblacion expuesta por fuente y rango acustico",
            "geo": geo,
            "period": "2022",
            "value": values,
            "unit": "%",
            "quality": "alta",
            "notes": "Porcentaje de poblacion expuesta a niveles de ruido del mapa estrategico municipal.",
            "raw_file": relative(path),
            "extracted_at": df[extracted_at] if extracted_at else "",
        }
    )
    return fact.dropna(subset=["value"])


def clean_mitma_xls() -> dict[str, Any]:
    path = RAW_DATA_DIR / "mitma" / "precio_m2_venta_raw.xls"
    if not path.exists():
        return missing("mitma_precio_m2_vivienda", path)

    try:
        xls = pd.ExcelFile(path)
    except ImportError as exc:
        return {
            "report": [
                {
                    "dataset": "mitma_precio_m2_vivienda",
                    "estado": "PENDIENTE",
                    "entrada": relative(path),
                    "motivo": f"Falta dependencia para leer .xls: {exc}",
                }
            ],
            "facts": [],
        }

    rows: list[dict[str, Any]] = []
    for sheet in xls.sheet_names:
        period = parse_mitma_sheet_period(sheet)
        if not period:
            continue

        raw = pd.read_excel(path, sheet_name=sheet, header=None)
        value_col = 5 if raw.shape[1] >= 10 else 3
        appraisals_col = 9 if raw.shape[1] >= 10 else 5
        current_province = None

        for _, row in raw.iterrows():
            province = fix_text(row.get(1))
            municipality = fix_text(row.get(2))
            if isinstance(province, str) and province and province.lower() != "nan":
                current_province = province
            if not isinstance(municipality, str) or not municipality or municipality.lower() == "nan":
                continue

            value = parse_number(row.get(value_col))
            appraisals = parse_number(row.get(appraisals_col))
            if value is None and appraisals is None:
                continue
            if municipality.lower() in {"municipio", "total"}:
                continue

            rows.append(
                {
                    "periodo": period["period"],
                    "anio": period["year"],
                    "trimestre": period["quarter"],
                    "provincia": current_province,
                    "municipio": municipality,
                    "precio_m2_eur": value,
                    "tasaciones": appraisals,
                    "fuente": "MITMA/MIVAU",
                    "variable_iseu": "Precio vivienda m2",
                    "extraido_en": datetime.now().isoformat(timespec="seconds"),
                }
            )

    df = clean_dataframe(pd.DataFrame(rows))
    out = CLEAN_DIR / "mitma_precio_m2_vivienda_limpio.csv"
    write_clean_csv(df, out)

    barcelona = df[
        (df["provincia"].astype(str).str.lower() == "barcelona")
        & (df["municipio"].astype(str).str.lower() == "barcelona")
    ].copy()
    price_facts = pd.DataFrame(
        {
            "source": "MITMA/MIVAU",
            "dataset": "precio_m2_vivienda",
            "variable": "Precio vivienda m2",
            "metric": "Valor tasado de vivienda total",
            "geo": "Barcelona",
            "period": barcelona.get("periodo", ""),
            "value": barcelona.get("precio_m2_eur", ""),
            "unit": "EUR/m2",
            "quality": "alta",
            "notes": "Precio tasado de vivienda; serie trimestral municipal.",
            "raw_file": relative(path),
            "extracted_at": barcelona.get("extraido_en", ""),
        }
    ).dropna(subset=["value"])
    appraisal_facts = pd.DataFrame(
        {
            "source": "MITMA/MIVAU",
            "dataset": "tasaciones_vivienda",
            "variable": "Tasaciones vivienda",
            "metric": "Numero de tasaciones de vivienda",
            "geo": "Barcelona",
            "period": barcelona.get("periodo", ""),
            "value": barcelona.get("tasaciones", ""),
            "unit": "tasaciones",
            "quality": "alta",
            "notes": "Numero de tasaciones de vivienda asociado al valor tasado MITMA/MIVAU.",
            "raw_file": relative(path),
            "extracted_at": barcelona.get("extraido_en", ""),
        }
    ).dropna(subset=["value"])
    facts = pd.concat([price_facts, appraisal_facts], ignore_index=True)

    return {
        "report": [ok("mitma_precio_m2_vivienda", path, out, len(df), "XLS MITMA/MIVAU normalizado")],
        "facts": [facts],
    }


def clean_alquiler_gpkg() -> dict[str, Any]:
    path = RAW_DATA_DIR / "opendata_bcn" / "2017_taxa_lloguer_od.gpkg"
    if not path.exists():
        return missing("bcn_alquiler_gpkg", path)

    try:
        import geopandas as gpd
    except ImportError as exc:
        return {
            "report": [
                {
                    "dataset": "bcn_alquiler_gpkg",
                    "estado": "PENDIENTE",
                    "entrada": relative(path),
                    "motivo": f"Falta geopandas/pyogrio para leer .gpkg: {exc}",
                }
            ],
            "facts": [],
        }

    gdf = gpd.read_file(path, layer="taxa_lloguer_od")
    gdf = gdf.rename(
        columns={
            "sc_Codi": "seccion_censal",
            "AlqSum_Ren": "tasa_alquiler_renta",
            "Alq_perc": "percentil_alquiler",
        }
    )
    gdf["geometry_wkt"] = gdf.geometry.to_wkt()
    df = clean_dataframe(pd.DataFrame(gdf.drop(columns=["geometry"])))
    df["variable_iseu"] = "Precio alquiler medio"
    df["fuente"] = "Open Data BCN"
    df["nota_calidad"] = "Proxy: tasa/esfuerzo de alquiler por seccion censal, no renta mensual en euros."
    df["extraido_en"] = datetime.now().isoformat(timespec="seconds")

    out = CLEAN_DIR / "bcn_alquiler_limpio.csv"
    write_clean_csv(df, out)

    facts = pd.DataFrame(
        {
            "source": "Open Data BCN",
            "dataset": "bcn_alquiler",
            "variable": "Precio alquiler medio",
            "metric": "Tasa alquiler/renta por seccion censal",
            "geo": df.get("seccion_censal", ""),
            "period": "2017",
            "value": df.get("tasa_alquiler_renta", ""),
            "unit": "ratio",
            "quality": "media",
            "notes": "Proxy: mide carga relativa de alquiler, no precio mensual en euros.",
            "raw_file": relative(path),
            "extracted_at": df.get("extraido_en", ""),
        }
    ).dropna(subset=["value"])

    return {
        "report": [ok("bcn_alquiler_gpkg", path, out, len(df), "GeoPackage Open Data BCN convertido a CSV")],
        "facts": [facts],
    }


def parse_mitma_sheet_period(sheet_name: str) -> dict[str, Any] | None:
    match = re.search(r"T([1-4])A(20\d{2})", sheet_name.strip(), re.IGNORECASE)
    if not match:
        return None
    quarter = int(match.group(1))
    year = int(match.group(2))
    return {
        "year": year,
        "quarter": quarter,
        "period": f"{year}-T{quarter}",
    }


def read_csv(path: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return pd.read_csv(path, low_memory=False)


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = unique_columns([snake_case(fix_text(str(column))) for column in df.columns])
    for column in df.columns:
        if is_object_dtype(df[column]) or is_string_dtype(df[column]):
            df[column] = df[column].map(fix_text)
    df = df.drop_duplicates()
    return df


def drop_low_value_columns(df: pd.DataFrame, output_name: str) -> pd.DataFrame:
    columns = LOW_VALUE_COLUMNS_BY_FILE.get(output_name, [])
    existing = [column for column in columns if column in df.columns]
    if not existing:
        return df
    return df.drop(columns=existing)


def write_clean_csv(df: pd.DataFrame, out: Path) -> None:
    df = drop_low_value_columns(df, out.name)
    df.to_csv(out, index=False, encoding="utf-8")


def fix_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    for source, target in MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(source, target)
    return text


def snake_case(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower()
    return text or "columna"


def unique_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique = []
    for column in columns:
        count = seen.get(column, 0) + 1
        seen[column] = count
        unique.append(column if count == 1 else f"{column}_{count}")
    return unique


def to_number(series: Any) -> pd.Series:
    if not isinstance(series, pd.Series):
        return pd.Series(dtype="float64")
    return series.map(parse_number)


def parse_number(value: Any) -> float | None:
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = fix_text(str(value))
    text = text.replace("€", "").replace("%", "").replace(" ", "").strip()
    if not text:
        return None

    has_comma = "," in text
    has_dot = "." in text
    if has_comma and has_dot:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


def parse_ine_datetime(series: Any) -> pd.Series:
    if not isinstance(series, pd.Series):
        return pd.Series(dtype="datetime64[ns]")

    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().any() and numeric.dropna().abs().median() > 10_000_000_000:
        return pd.to_datetime(numeric, errors="coerce", unit="ms")
    return pd.to_datetime(series, errors="coerce")


def empty_series(df: pd.DataFrame, default: str = "") -> pd.Series:
    return pd.Series(default, index=df.index, dtype="object")


def infer_geo(series: Any) -> str:
    if isinstance(series, pd.Series):
        sample = " ".join(series.dropna().astype(str).head(10).tolist()).lower()
        if "barcelona" in sample:
            return "Barcelona"
        if "catalu" in sample:
            return "Catalunya"
    return "España"


def infer_geo_series(series: Any) -> pd.Series:
    if not isinstance(series, pd.Series):
        return pd.Series(dtype="object")

    normalized = series.fillna("").astype(str).str.lower()
    result = pd.Series("España", index=series.index, dtype="object")
    result = result.mask(normalized.str.contains("barcelona", na=False), "Barcelona")
    result = result.mask(normalized.str.contains("catalu|cataluña|catalunya", na=False), "Cataluña")
    return result


def coalesce_columns(df: pd.DataFrame, names: list[str], default: str) -> pd.Series:
    result = empty_series(df, default)
    for name in names:
        if name not in df.columns:
            continue
        candidate = df[name].fillna("").astype(str)
        result = result.mask(result.astype(str).str.strip() == "", candidate)
    return result.mask(result.astype(str).str.strip() == "", default)


def drop_incomplete_indicators(df: pd.DataFrame) -> pd.DataFrame:
    required = ["source", "dataset", "variable", "metric", "geo", "period", "value"]
    clean = df.copy()
    for column in required:
        if column not in clean.columns:
            clean[column] = pd.NA
        clean[column] = clean[column].replace(r"^\s*$", pd.NA, regex=True)
    return clean.dropna(subset=required)


def first_existing(df: pd.DataFrame, names: list[str]) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def ok(dataset: str, source: Path, out: Path, rows: int, note: str) -> dict[str, Any]:
    return {
        "dataset": dataset,
        "estado": "OK",
        "filas": int(rows),
        "entrada": relative(source),
        "salida": relative(out),
        "nota": note,
    }


def missing(dataset: str, path: Path) -> dict[str, Any]:
    return {
        "report": [{"dataset": dataset, "estado": "SIN_DATOS", "entrada": str(path)}],
        "facts": [],
    }


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
