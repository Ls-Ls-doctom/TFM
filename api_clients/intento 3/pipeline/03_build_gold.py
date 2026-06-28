from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from _common import GOLD_DIR, REPORTS_DIR, SILVER_DIR, ensure_dirs, gold_frame, now, relative, to_number, write_csv, write_json


def main() -> int:
    ensure_dirs()
    if not SILVER_DIR.exists():
        raise FileNotFoundError(f"No existe Silver: {SILVER_DIR}. Ejecuta primero pipeline/02_clean_silver.py.")

    rows: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []

    rows.extend(gold_from_ine(sources))
    rows.extend(gold_from_sepe(sources))
    rows.extend(gold_from_municipal(sources))

    indicators = gold_frame(rows).drop_duplicates()
    indicators = indicators.sort_values(["city", "variable", "date", "district"]).reset_index(drop=True)
    out = GOLD_DIR / "indicators.csv"
    write_csv(indicators, out)

    catalog = build_catalog(indicators)
    write_csv(catalog, GOLD_DIR / "indicator_catalog.csv")

    summary = {
        "generated_at": now(),
        "gold_dir": relative(GOLD_DIR),
        "indicator_file": relative(out),
        "rows_total": int(len(indicators)),
        "rows_by_city": indicators.groupby("city").size().to_dict() if not indicators.empty else {},
        "rows_by_variable": indicators.groupby("variable").size().to_dict() if not indicators.empty else {},
        "sources": sources,
    }
    write_json(REPORTS_DIR / "gold_build.json", summary)

    print(f"Gold generado: {out}")
    print(f"Indicadores: {len(indicators)}")
    return 0


def gold_from_ine(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    path = SILVER_DIR / "ine" / "poblacion_municipal.csv"
    if path.exists():
        df = pd.read_csv(path, low_memory=False)
        for _, row in df.iterrows():
            rows.append(
                indicator(
                    row["city"],
                    "",
                    "population_total",
                    row["population_total"],
                    row["date"],
                    "INE",
                    9,
                    "demography",
                    "persons",
                )
            )
        sources.append(source_item(path, len(df), "INE poblacion total municipal"))
    return rows


def gold_from_sepe(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    mapping = {
        "paro_registrado.csv": ("unemployed_registered", "employment", "persons"),
        "contratos_registrados.csv": ("contracts_registered", "employment", "contracts"),
        "demandantes_empleo.csv": ("job_seekers", "employment", "persons"),
    }
    for filename, (variable, category, unit) in mapping.items():
        path = SILVER_DIR / "sepe" / filename
        if not path.exists():
            continue
        df = pd.read_csv(path, low_memory=False)
        if df.empty:
            continue
        grouped = (
            df.groupby(["city", "date"], as_index=False)["value"]
            .sum(min_count=1)
            .dropna(subset=["value"])
        )
        for _, row in grouped.iterrows():
            rows.append(indicator(row["city"], "", variable, row["value"], row["date"], "SEPE", 8, category, unit))
        sources.append(source_item(path, len(grouped), f"SEPE {variable} agregado por ciudad/mes"))
    return rows


def gold_from_municipal(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    path = SILVER_DIR / "municipios" / "municipal_prioritario.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path, low_memory=False)
    rows: list[dict[str, Any]] = []

    rows.extend(extract_income(df))
    rows.extend(extract_income_by_district(df))
    rows.extend(extract_inequality(df))
    rows.extend(extract_traffic_accidents(df))
    rows.extend(extract_mobility_counts(df))
    sources.append(source_item(path, len(rows), "Municipal prioritario extraido a indicadores"))
    return rows


def _income_detail_rows(income: pd.DataFrame) -> pd.DataFrame:
    """Extrae columnas de renta e indicadores de desigualdad en formato largo."""
    income_tokens = ("renda", "renta", "income")
    skip = {"dataset_family", "source_file"}
    records = []
    for _, row in income.iterrows():
        date = infer_date(row)
        city = str(row.get("city", ""))
        district = str(row.get("nom_districte", "") or "")
        for column in income.columns:
            if column in skip or not any(t in column for t in income_tokens):
                continue
            value = to_number(row.get(column))
            if value is None:
                continue
            records.append({
                "city": city,
                "district": district,
                "variable": normalize_income_variable(column),
                "value": value,
                "date": date,
                "source": "Municipal Open Data",
                "quality_score": 7,
                "category": "economy",
                "unit": "eur",
            })
    return pd.DataFrame(records) if records else pd.DataFrame()


def extract_income(df: pd.DataFrame) -> list[dict[str, Any]]:
    income = df[df.get("dataset_family", "") == "income"].copy()
    if income.empty:
        return []
    detail = _income_detail_rows(income)
    if detail.empty:
        return []
    grouped = detail.groupby(["city", "variable", "date", "source", "category", "unit"], as_index=False).agg(
        value=("value", "mean"),
        quality_score=("quality_score", "max"),
    )
    return grouped.assign(district="").to_dict(orient="records")


def extract_income_by_district(df: pd.DataFrame) -> list[dict[str, Any]]:
    income = df[df.get("dataset_family", "") == "income"].copy()
    if income.empty or "nom_districte" not in income.columns:
        return []
    income = income[income["nom_districte"].notna() & (income["nom_districte"].astype(str).str.strip() != "")]
    if income.empty:
        return []
    detail = _income_detail_rows(income)
    if detail.empty:
        return []
    grouped = detail.groupby(["city", "district", "variable", "date", "source", "category", "unit"], as_index=False).agg(
        value=("value", "mean"),
        quality_score=("quality_score", "max"),
    )
    return grouped.to_dict(orient="records")


def extract_inequality(df: pd.DataFrame) -> list[dict[str, Any]]:
    income = df[df.get("dataset_family", "") == "income"].copy()
    if income.empty:
        return []
    col_map = {
        "index_gini": ("gini_inequality", "economy", "index"),
        "distribucio_p80_20": ("inequality_p80p20", "economy", "ratio"),
    }
    records = []
    for col, (variable, category, unit) in col_map.items():
        if col not in income.columns:
            continue
        for _, row in income.iterrows():
            value = to_number(row.get(col))
            if value is None:
                continue
            district = str(row.get("nom_districte", "") or "")
            records.append({
                "city": str(row.get("city", "")),
                "district": district,
                "variable": variable,
                "value": value,
                "date": infer_date(row),
                "source": "Municipal Open Data",
                "quality_score": 7,
                "category": category,
                "unit": unit,
            })
    if not records:
        return []
    detail = pd.DataFrame(records)
    # Ciudad + distrito
    by_district = detail.groupby(["city", "district", "variable", "date", "source", "category", "unit"], as_index=False).agg(
        value=("value", "mean"), quality_score=("quality_score", "max"),
    )
    # Ciudad (agrupado sin distrito)
    by_city = detail.groupby(["city", "variable", "date", "source", "category", "unit"], as_index=False).agg(
        value=("value", "mean"), quality_score=("quality_score", "max"),
    ).assign(district="")
    return pd.concat([by_city, by_district], ignore_index=True).to_dict(orient="records")


def extract_traffic_accidents(df: pd.DataFrame) -> list[dict[str, Any]]:
    mobility = df[df.get("dataset_family", "") == "mobility"].copy()
    if mobility.empty or "fecha" not in mobility.columns:
        return []
    accidents = mobility[mobility["fecha"].notna()].copy()
    if accidents.empty:
        return []
    accidents["_year"] = pd.to_datetime(accidents["fecha"], errors="coerce").dt.year
    accidents = accidents.dropna(subset=["_year"])
    accidents["_date"] = accidents["_year"].astype(int).astype(str) + "-01-01"
    grouped = accidents.groupby(["city", "_date"]).size().reset_index(name="value")
    return [
        indicator(row["city"], "", "traffic_accidents", row["value"], row["_date"], "Municipal Open Data", 6, "mobility", "incidents")
        for _, row in grouped.iterrows()
    ]


def extract_mobility_counts(df: pd.DataFrame) -> list[dict[str, Any]]:
    mobility = df[df.get("dataset_family", "") == "mobility"].copy()
    if mobility.empty:
        return []
    rows: list[dict[str, Any]] = []
    grouped = mobility.groupby(["city", "source_file"], dropna=False).size().reset_index(name="value")
    for _, row in grouped.iterrows():
        rows.append(
            indicator(
                row["city"],
                "",
                "mobility_resources_records",
                row["value"],
                infer_date(row),
                "Municipal Open Data",
                5,
                "mobility",
                "records",
            )
        )
    return rows


def infer_date(row: pd.Series) -> str:
    for key in ("date", "any", "ano", "anio", "year", "periodo"):
        if key in row.index and pd.notna(row.get(key)):
            text = str(row.get(key))
            if len(text) >= 4:
                return f"{text[:4]}-01-01"
    text = str(row.get("source_file", ""))
    for token in text.replace("\\", "/").split("/"):
        if token[:4].isdigit():
            return f"{token[:4]}-01-01"
    return "2026-01-01"


def first_value(row: pd.Series, columns: list[str]) -> str:
    for column in columns:
        if column in row.index and pd.notna(row.get(column)):
            return str(row.get(column))
    return ""


def normalize_income_variable(column: str) -> str:
    if "persona" in column or "person" in column:
        return "income_per_person"
    if "llar" in column or "hogar" in column or "household" in column:
        return "income_per_household"
    if "mediana" in column or "median" in column:
        return "income_median"
    return "income"


def indicator(
    city: object,
    district: object,
    variable: str,
    value: object,
    date: object,
    source: str,
    quality_score: int,
    category: str,
    unit: str,
) -> dict[str, Any]:
    return {
        "city": str(city),
        "district": "" if pd.isna(district) else str(district),
        "variable": variable,
        "value": value,
        "date": str(date),
        "source": source,
        "quality_score": quality_score,
        "category": category,
        "unit": unit,
    }


def source_item(path: Path, rows: int, note: str) -> dict[str, Any]:
    return {"file": relative(path), "rows_used": int(rows), "note": note}


def build_catalog(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["variable", "category", "unit", "sources", "cities", "rows"])
    return (
        df.groupby(["variable", "category", "unit"], as_index=False)
        .agg(
            sources=("source", lambda values: "|".join(sorted(set(map(str, values))))),
            cities=("city", lambda values: "|".join(sorted(set(map(str, values))))),
            rows=("variable", "size"),
        )
        .sort_values(["category", "variable"])
    )


if __name__ == "__main__":
    raise SystemExit(main())
