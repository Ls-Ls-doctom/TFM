from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from _common import (
    BRONZE_DIR,
    REPORTS_DIR,
    SILVER_DIR,
    TARGET_CITIES,
    clean_columns,
    ensure_dirs,
    infer_city_from_path,
    municipality_code,
    now,
    read_csv_flexible,
    read_sepe_csv,
    relative,
    to_month_date,
    to_number,
    to_year_date,
    write_csv,
    write_json,
)


PRIORITY_MUNICIPAL_KEYWORDS = [
    "renda",
    "renta",
    "income",
    "poblacion",
    "demografic",
    "demograf",
    "trafic",
    "transit",
    "bizi",
    "bicic",
    "sostenibilidad",
]


def main() -> int:
    ensure_dirs()
    if not BRONZE_DIR.exists():
        raise FileNotFoundError(f"No existe Bronze: {BRONZE_DIR}. Ejecuta primero las APIs.")

    report: list[dict[str, Any]] = []
    outputs: dict[str, pd.DataFrame] = {}

    outputs.update(clean_ine(report))
    outputs.update(clean_sepe(report))
    outputs.update(clean_mitma(report))
    outputs.update(clean_municipal_priority(report))

    for key, df in outputs.items():
        write_csv(df, SILVER_DIR / key)

    summary = {
        "generated_at": now(),
        "silver_dir": relative(SILVER_DIR),
        "tables_total": len(outputs),
        "rows_by_table": {key: int(len(df)) for key, df in outputs.items()},
        "resources": report,
    }
    write_json(REPORTS_DIR / "cleaning_silver.json", summary)

    print(f"Silver generado en: {SILVER_DIR}")
    for key, df in outputs.items():
        print(f"{key}: {len(df)} filas")
    return 0


def clean_ine(report: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    outputs: dict[str, pd.DataFrame] = {}
    ine_dir = BRONZE_DIR / "apis" / "ine"
    population_path = ine_dir / "poblacion_municipio_sexo" / "poblacion_municipio_sexo_csv_semicolon.csv"
    birthplace_path = ine_dir / "poblacion_municipio_pais_nacimiento" / "poblacion_municipio_pais_nacimiento_csv_semicolon.csv"

    if population_path.exists():
        df = clean_columns(read_csv_flexible(population_path))
        df["municipality_code"] = df["municipios"].map(municipality_code)
        df = df[(df["municipality_code"].isin(TARGET_CITIES)) & (df["sexo"].astype(str).str.lower() == "total")].copy()
        df["city"] = df["municipality_code"].map(TARGET_CITIES)
        df["date"] = df["periodo"].map(to_year_date)
        df["population_total"] = df["total"].map(to_number)
        out = df[["city", "municipality_code", "date", "population_total", "total_nacional", "municipios"]].dropna(
            subset=["population_total"]
        )
        outputs["ine/poblacion_municipal.csv"] = out
        report.append(item(population_path, "OK", len(out), "INE poblacion municipal filtrada a ciudades objetivo"))

    if birthplace_path.exists():
        df = clean_columns(read_csv_flexible(birthplace_path))
        df["municipality_code"] = df["municipios"].map(municipality_code)
        if "pais_de_nacimiento" not in df.columns:
            country_col = next((col for col in df.columns if "nacimiento" in col), "")
        else:
            country_col = "pais_de_nacimiento"
        df = df[
            (df["municipality_code"].isin(TARGET_CITIES))
            & (df["sexo"].astype(str).str.lower() == "total")
            & (df[country_col].astype(str).str.lower() == "total")
        ].copy()
        df["city"] = df["municipality_code"].map(TARGET_CITIES)
        df["date"] = df["periodo"].map(to_year_date)
        df["population_birthplace_total"] = df["total"].map(to_number)
        out = df[["city", "municipality_code", "date", "population_birthplace_total", "provincias", "municipios"]].dropna(
            subset=["population_birthplace_total"]
        )
        outputs["ine/poblacion_pais_nacimiento_total.csv"] = out
        report.append(item(birthplace_path, "OK", len(out), "INE poblacion por pais nacimiento filtrada"))

    return outputs


def clean_sepe(report: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    outputs: dict[str, pd.DataFrame] = {}
    configs = {
        "paro_registrado": ("total_paro_registrado", "unemployed_registered"),
        "contratos_registrados": ("total_contratos", "contracts_registered"),
        "demandantes_empleo": ("total_dtes_empleo", "job_seekers"),
    }
    for folder, (total_col, variable) in configs.items():
        frames = []
        for path in sorted((BRONZE_DIR / "apis" / "sepe" / folder / "resources").glob("*.csv")):
            df = read_sepe_csv(path)
            if df.empty:
                report.append(item(path, "EMPTY", 0, f"SEPE {folder} sin filas"))
                continue
            code_col = next((col for col in df.columns if "codigo_municipio" in col), "")
            if not code_col or total_col not in df.columns:
                report.append(item(path, "SKIPPED_SCHEMA", 0, f"Columnas no compatibles para {folder}"))
                continue
            df["municipality_code"] = df[code_col].map(municipality_code)
            df = df[df["municipality_code"].isin(TARGET_CITIES)].copy()
            df["city"] = df["municipality_code"].map(TARGET_CITIES)
            df["date"] = df["codigo_mes"].map(to_month_date)
            df["value"] = df[total_col].map(to_number)
            df["variable"] = variable
            keep = ["city", "municipality_code", "date", "variable", "value", "municipio", "provincia", "comunidad_autonoma"]
            frames.append(df[[col for col in keep if col in df.columns]].dropna(subset=["value"]))
            report.append(item(path, "OK", int(len(df)), f"SEPE {folder} filtrado a ciudades objetivo"))
        if frames:
            outputs[f"sepe/{folder}.csv"] = pd.concat(frames, ignore_index=True).drop_duplicates()
    return outputs


def clean_mitma(report: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    outputs: dict[str, pd.DataFrame] = {}
    path = BRONZE_DIR / "apis" / "mitma" / "relaciones_distrito_mitma.csv"
    if not path.exists():
        return outputs
    df = clean_columns(read_csv_flexible(path))
    out = df.copy()
    outputs["mitma/relaciones_distrito_mitma.csv"] = out
    report.append(item(path, "OK", len(out), "MITMA relacion distrito normalizada"))
    return outputs


def clean_municipal_priority(report: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    outputs: dict[str, pd.DataFrame] = {}
    rows = []
    for path in sorted((BRONZE_DIR / "municipios").rglob("*.csv")):
        text = str(path).lower()
        if not any(keyword in text for keyword in PRIORITY_MUNICIPAL_KEYWORDS):
            continue
        city = infer_city_from_path(path)
        if not city:
            continue
        try:
            df = clean_columns(read_csv_flexible(path))
        except Exception as exc:  # noqa: BLE001
            report.append(item(path, "ERROR", 0, str(exc)))
            continue
        df = df.dropna(how="all").drop_duplicates()
        if df.empty:
            report.append(item(path, "EMPTY", 0, "Municipal prioritario sin filas"))
            continue
        df["city"] = city
        df["source_file"] = relative(path)
        df["dataset_family"] = classify_municipal(path)
        rows.append(df)
        report.append(item(path, "OK", len(df), f"Municipal prioritario {city}"))
    if rows:
        outputs["municipios/municipal_prioritario.csv"] = pd.concat(rows, ignore_index=True, sort=False)
    return outputs


def classify_municipal(path: Path) -> str:
    text = str(path).lower()
    if any(token in text for token in ("renda", "renta", "income")):
        return "income"
    if any(token in text for token in ("poblacion", "demografic", "demograf")):
        return "demography"
    if any(token in text for token in ("trafic", "transit", "bizi", "bicic")):
        return "mobility"
    if "sostenibilidad" in text:
        return "environment"
    return "other"


def item(path: Path, status: str, rows: int, note: str) -> dict[str, Any]:
    return {
        "file": relative(path),
        "status": status,
        "rows": int(rows),
        "note": note,
    }


if __name__ == "__main__":
    raise SystemExit(main())
