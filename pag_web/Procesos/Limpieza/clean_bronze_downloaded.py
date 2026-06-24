from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from clean_datasets import clean_dataframe, fix_text, read_csv, to_number


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BRONZE_DETAIL = PROJECT_ROOT / "pag_web" / "Procesos" / "Datasets" / "eda_bronze" / "descarga_recursos_bronze.csv"
SILVER_DIR = PROJECT_ROOT / "api_clients" / "intento 3" / "data_lake" / "silver" / "barcelona"
EDA_DIR = PROJECT_ROOT / "pag_web" / "Procesos" / "Datasets" / "eda_bronze"
SQLITE_PATH = EDA_DIR / "bronze_silver_staging.sqlite"
REPORT_PATH = SILVER_DIR / "catalogo_limpieza_silver.json"

COMMON_COLUMNS = [
    "source",
    "dataset_id",
    "dataset_title",
    "resource_name",
    "resource_url",
    "raw_file",
    "extracted_at",
]

INDICATOR_COLUMNS = [
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


def main() -> None:
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    EDA_DIR.mkdir(parents=True, exist_ok=True)

    manifest = pd.read_csv(BRONZE_DETAIL, low_memory=False)
    manifest = manifest[(manifest["status"] == "OK") & (manifest["download_kind"] == "csv")].copy()

    frames = {"censo": [], "aforos": [], "fotografias": []}
    report: list[dict[str, Any]] = []

    for _, resource in manifest.iterrows():
        path = PROJECT_ROOT / str(resource["output_file"])
        if not path.exists():
            report.append(report_item(resource, "SIN_ARCHIVO", 0, "No existe el archivo descargado"))
            continue

        raw = read_csv(path)
        df = clean_dataframe(raw)
        family = classify_resource(resource)
        cleaned = clean_by_family(df, resource, path, family)
        frames[family].append(cleaned)
        report.append(report_item(resource, "OK", len(cleaned), f"Familia silver: {family}"))

    censo = concat_frames(frames["censo"])
    aforos = concat_frames(frames["aforos"])
    fotografias = concat_frames(frames["fotografias"])
    indicators = build_indicators(censo, aforos, fotografias)

    outputs = {
        "barcelona_censo_locales_limpio.csv": censo,
        "barcelona_aforos_movilidad_limpio.csv": aforos,
        "barcelona_fotografias_edificios_limpio.csv": fotografias,
        "indicadores_silver_barcelona.csv": indicators,
    }
    for name, df in outputs.items():
        out = SILVER_DIR / name
        df.to_csv(out, index=False, encoding="utf-8")

    write_sqlite(outputs)

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "bronze_manifest": relative(BRONZE_DETAIL),
        "silver_dir": relative(SILVER_DIR),
        "sqlite_staging": relative(SQLITE_PATH),
        "resources_processed": len(report),
        "rows_by_table": {name: int(len(df)) for name, df in outputs.items()},
        "resources": report,
    }
    REPORT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Limpieza Silver Bronze descargado terminada")
    for name, df in outputs.items():
        print(f"{name}: {len(df)} filas")
    print(f"Reporte: {REPORT_PATH}")
    print(f"SQLite staging: {SQLITE_PATH}")


def classify_resource(resource: pd.Series) -> str:
    text = f"{resource.get('dataset_title', '')} {resource.get('resource_name', '')}".lower()
    if "censo" in text or "cens" in text or "locales" in text:
        return "censo"
    if "aforo" in text or "aforament" in text or "movilidad" in text:
        return "aforos"
    return "fotografias"


def clean_by_family(df: pd.DataFrame, resource: pd.Series, path: Path, family: str) -> pd.DataFrame:
    if family == "censo":
        return clean_censo(df, resource, path)
    if family == "aforos":
        return clean_aforos(df, resource, path)
    return clean_fotografias(df, resource, path)


def clean_censo(df: pd.DataFrame, resource: pd.Series, path: Path) -> pd.DataFrame:
    year = infer_year(resource)
    out = pd.DataFrame(index=df.index)
    add_common(out, resource, path)
    out["year"] = year
    out["local_id"] = coalesce(df, ["id_global", "id_bcn_2019", "id_bcn", "id_bcn_2016", "id_princip"])
    out["activity_status"] = normalize_text(coalesce(df, ["nom_principal_activitat", "n_princip"]))
    out["sector_code"] = coalesce(df, ["codi_sector_activitat", "id_sector"])
    out["sector_name"] = normalize_text(coalesce(df, ["nom_sector_activitat", "n_sector"]))
    out["activity_group_code"] = coalesce(df, ["codi_grup_activitat", "id_grupact"])
    out["activity_group_name"] = normalize_text(coalesce(df, ["nom_grup_activitat", "n_grupact"]))
    out["activity_code"] = coalesce(df, ["codi_activitat_2022", "codi_activitat_2019", "codi_activitat_2016", "id_act"])
    out["activity_name"] = normalize_text(coalesce(df, ["nom_activitat", "n_act"]))
    out["local_name"] = normalize_text(coalesce(df, ["nom_local", "n_local"]))
    out["district_code"] = normalize_code(coalesce(df, ["codi_districte"]))
    out["district_name"] = normalize_text(coalesce(df, ["nom_districte", "n_distri"]))
    out["neighborhood_code"] = normalize_code(coalesce(df, ["codi_barri"]))
    out["neighborhood_name"] = normalize_text(coalesce(df, ["nom_barri"]))
    out["street_name"] = normalize_text(coalesce(df, ["nom_via", "n_carrer"]))
    out["address"] = normalize_text(coalesce(df, ["direccio_unica"]))
    out["latitude"] = to_number(coalesce(df, ["latitud", "latitud_1"]))
    out["longitude"] = to_number(coalesce(df, ["longitud", "longitud_1"]))
    out["utm_x"] = to_number(coalesce(df, ["x_utm_etrs89", "x_utm_etrs"]))
    out["utm_y"] = to_number(coalesce(df, ["y_utm_etrs89", "y_utm_etrs"]))
    out["is_street"] = parse_yes_no(coalesce(df, ["sn_carrer"]))
    out["is_market"] = parse_yes_no(coalesce(df, ["sn_mercat"]))
    out["is_gallery"] = parse_yes_no(coalesce(df, ["sn_galeria"]))
    out["is_shopping_center"] = parse_yes_no(coalesce(df, ["sn_ccomercial", "sn_ccomerc"]))
    out["is_axis"] = parse_yes_no(coalesce(df, ["sn_eix"]))
    out["review_date"] = parse_date(coalesce(df, ["data_revisio", "data"]))
    return finalize(out, ["year", "district_name", "neighborhood_name", "activity_name"])


def clean_aforos(df: pd.DataFrame, resource: pd.Series, path: Path) -> pd.DataFrame:
    year = infer_year(resource)
    out = pd.DataFrame(index=df.index)
    add_common(out, resource, path)
    out["year"] = year
    out["counter_id"] = normalize_text(coalesce(df, ["id_aforament"]))
    out["counter_description"] = normalize_text(coalesce(df, ["desc_aforament"]))
    out["counter_type_code"] = coalesce(df, ["codi_tipus_aforament"])
    out["counter_type"] = normalize_text(coalesce(df, ["desc_tipus_aforament"]))
    out["lanes"] = to_number(coalesce(df, ["num_carrils"]))
    out["district_code"] = normalize_code(coalesce(df, ["codi_districte"]))
    out["neighborhood_code"] = normalize_code(coalesce(df, ["codi_barri"]))
    out["equipment_type_code"] = coalesce(df, ["codi_tipus_equip_mesura"])
    out["equipment_type"] = normalize_text(coalesce(df, ["desc_tipus_equip_mesura"]))
    out["latitude"] = to_number(coalesce(df, ["latitud"]))
    out["longitude"] = to_number(coalesce(df, ["longitud"]))
    out["utm_x"] = to_number(coalesce(df, ["x_etrs89"]))
    out["utm_y"] = to_number(coalesce(df, ["y_etrs89"]))
    return finalize(out, ["year", "counter_id", "counter_description"])


def clean_fotografias(df: pd.DataFrame, resource: pd.Series, path: Path) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    add_common(out, resource, path)
    out["created_date"] = parse_date(coalesce(df, ["dc_date_created"]))
    out["issued_date"] = parse_date(coalesce(df, ["dc_date_issued"]))
    out["issued_year"] = pd.to_datetime(out["issued_date"], errors="coerce").dt.year.astype("Int64")
    out["spatial"] = normalize_text(coalesce(df, ["dc_coverage_spatial"]))
    out["district_name"] = out["spatial"].map(extract_photo_district)
    out["title"] = normalize_text(coalesce(df, ["dc_title"]))
    out["subject"] = normalize_text(coalesce(df, ["dc_subject_imagurb", "dc_subject"]))
    out["format"] = normalize_text(coalesce(df, ["dc_format"]))
    out["uri"] = normalize_text(coalesce(df, ["dc_identifier_uri"]))
    out["rights"] = normalize_text(coalesce(df, ["dc_rights"]))
    return finalize(out, ["issued_year", "title", "uri"])


def add_common(out: pd.DataFrame, resource: pd.Series, path: Path) -> None:
    out["source"] = resource.get("source", "")
    out["dataset_id"] = resource.get("dataset_id", "")
    out["dataset_title"] = resource.get("dataset_title", "")
    out["resource_name"] = resource.get("resource_name", "")
    out["resource_url"] = resource.get("resource_url", "")
    out["raw_file"] = relative(path)
    out["extracted_at"] = resource.get("downloaded_at", "")


def build_indicators(censo: pd.DataFrame, aforos: pd.DataFrame, fotografias: pd.DataFrame) -> pd.DataFrame:
    frames = [
        censo_count_indicators(censo),
        aforos_count_indicators(aforos),
        aforos_lanes_indicators(aforos),
        fotografias_count_indicators(fotografias),
    ]
    result = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True)
    if result.empty:
        return pd.DataFrame(columns=INDICATOR_COLUMNS)
    return result[INDICATOR_COLUMNS].drop_duplicates()


def censo_count_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=INDICATOR_COLUMNS)
    grouped = df.groupby(["year", "district_name", "sector_name"], dropna=False).size().reset_index(name="value")
    grouped["geo"] = grouped["district_name"].fillna("Barcelona").map(lambda value: f"Barcelona - {value}" if value else "Barcelona")
    return indicator_frame(
        grouped,
        dataset="barcelona_censo_locales",
        variable="actividad_economica",
        metric_prefix="Locales comerciales por sector",
        metric_column="sector_name",
        period_column="year",
        geo_column="geo",
        unit="locales",
        notes="Indicador derivado del censo de locales en planta baja de Barcelona.",
        raw_file="api_clients/intento 3/data_lake/silver/barcelona/barcelona_censo_locales_limpio.csv",
    )


def aforos_count_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=INDICATOR_COLUMNS)
    grouped = df.groupby(["year", "district_code", "counter_type"], dropna=False).size().reset_index(name="value")
    grouped["geo"] = grouped["district_code"].fillna("Barcelona").map(lambda value: f"Barcelona distrito {value}" if value else "Barcelona")
    return indicator_frame(
        grouped,
        dataset="barcelona_aforos_movilidad",
        variable="movilidad",
        metric_prefix="Equipamientos de aforo por tipo",
        metric_column="counter_type",
        period_column="year",
        geo_column="geo",
        unit="equipamientos",
        notes="Indicador derivado de equipamientos de medida de aforo de movilidad.",
        raw_file="api_clients/intento 3/data_lake/silver/barcelona/barcelona_aforos_movilidad_limpio.csv",
    )


def aforos_lanes_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "lanes" not in df.columns:
        return pd.DataFrame(columns=INDICATOR_COLUMNS)
    grouped = df.groupby(["year", "district_code"], dropna=False)["lanes"].sum().reset_index(name="value")
    grouped["geo"] = grouped["district_code"].fillna("Barcelona").map(lambda value: f"Barcelona distrito {value}" if value else "Barcelona")
    grouped["metric_name"] = "Carriles cubiertos por equipamientos de aforo"
    return indicator_frame(
        grouped,
        dataset="barcelona_aforos_movilidad",
        variable="movilidad",
        metric_prefix="",
        metric_column="metric_name",
        period_column="year",
        geo_column="geo",
        unit="carriles",
        notes="Suma de carriles asociados a equipamientos de aforo por distrito.",
        raw_file="api_clients/intento 3/data_lake/silver/barcelona/barcelona_aforos_movilidad_limpio.csv",
    )


def fotografias_count_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=INDICATOR_COLUMNS)
    grouped = df.groupby(["issued_year", "district_name"], dropna=False).size().reset_index(name="value")
    grouped = grouped.dropna(subset=["issued_year"])
    grouped["geo"] = grouped["district_name"].fillna("Barcelona").map(lambda value: f"Barcelona - {value}" if value else "Barcelona")
    grouped["metric_name"] = "Fotografias de edificios catalogadas"
    return indicator_frame(
        grouped,
        dataset="barcelona_fotografias_edificios",
        variable="vivienda_servicios_urbanos",
        metric_prefix="",
        metric_column="metric_name",
        period_column="issued_year",
        geo_column="geo",
        unit="fotografias",
        notes="Conteo documental derivado del catalogo BCNROC de fotografias de edificios.",
        raw_file="api_clients/intento 3/data_lake/silver/barcelona/barcelona_fotografias_edificios_limpio.csv",
    )


def indicator_frame(
    grouped: pd.DataFrame,
    dataset: str,
    variable: str,
    metric_prefix: str,
    metric_column: str,
    period_column: str,
    geo_column: str,
    unit: str,
    notes: str,
    raw_file: str,
) -> pd.DataFrame:
    metric = grouped[metric_column].fillna("sin clasificar").astype(str)
    if metric_prefix:
        metric = metric_prefix + ": " + metric
    return pd.DataFrame(
        {
            "source": "Barcelona Open Data",
            "dataset": dataset,
            "variable": variable,
            "metric": metric,
            "geo": grouped[geo_column].fillna("Barcelona"),
            "period": grouped[period_column].astype("Int64").astype(str),
            "value": grouped["value"],
            "unit": unit,
            "quality": "media",
            "notes": notes,
            "raw_file": raw_file,
            "extracted_at": datetime.now().isoformat(timespec="seconds"),
        }
    ).dropna(subset=["value"])


def concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates()


def finalize(df: pd.DataFrame, subset: list[str]) -> pd.DataFrame:
    df = df.copy()
    for column in COMMON_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    existing_subset = [column for column in subset if column in df.columns]
    if existing_subset:
        df = df.dropna(how="all", subset=existing_subset)
    return df.drop_duplicates()


def coalesce(df: pd.DataFrame, names: list[str], default: str = "") -> pd.Series:
    result = pd.Series(default, index=df.index, dtype="object")
    for name in names:
        if name not in df.columns:
            continue
        candidate = df[name].fillna("")
        result = result.mask(result.astype(str).str.strip() == "", candidate)
    return result


def normalize_text(series: pd.Series) -> pd.Series:
    return series.map(fix_text).fillna("").astype(str).str.strip().replace({"nan": "", "None": ""})


def normalize_code(series: pd.Series) -> pd.Series:
    values = normalize_text(series)
    values = values.str.replace(r"\.0$", "", regex=True).str.zfill(2)
    return values.mask(values == "00", "")


def parse_yes_no(series: pd.Series) -> pd.Series:
    values = normalize_text(series).str.lower()
    result = pd.Series(pd.NA, index=series.index, dtype="boolean")
    result = result.mask(values.isin(["si", "sí", "s", "1", "true", "yes"]), True)
    result = result.mask(values.isin(["no", "n", "0", "false"]), False)
    return result


def parse_date(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    return parsed.dt.date.astype("string")


def infer_year(resource: pd.Series) -> int | None:
    text = f"{resource.get('resource_name', '')} {resource.get('dataset_title', '')}"
    match = re.search(r"\b(20\d{2}|19\d{2})\b", text)
    return int(match.group(1)) if match else None


def extract_photo_district(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"Districte\s+\d+\.\s*([^\.]+)", text, flags=re.IGNORECASE)
    return fix_text(match.group(1).strip()) if match else "Barcelona"


def write_sqlite(outputs: dict[str, pd.DataFrame]) -> None:
    with sqlite3.connect(SQLITE_PATH) as conn:
        for filename, df in outputs.items():
            table = Path(filename).stem
            df.to_sql(table, conn, if_exists="replace", index=False)


def report_item(resource: pd.Series, status: str, rows: int, note: str) -> dict[str, Any]:
    return {
        "dataset": resource.get("dataset_title", ""),
        "resource": resource.get("resource_name", ""),
        "estado": status,
        "filas": int(rows),
        "entrada": resource.get("output_file", ""),
        "nota": note,
    }


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()