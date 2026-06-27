from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(os.getenv("ISEU_PROJECT_ROOT", "/app")).resolve()
PIPELINE_ROOT = PROJECT_ROOT / "api_clients" / "intento 3"
SILVER_DIR = PIPELINE_ROOT / "data_lake" / "silver"
GOLD_DIR = PIPELINE_ROOT / "data_lake" / "gold"
REPORTS_DIR = PIPELINE_ROOT / "reports"


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    silver_tables = publish_silver()
    gold_tables = publish_gold()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "format": "parquet",
        "compression": "snappy",
        "silver_tables": silver_tables,
        "gold_tables": gold_tables,
        "athena_locations": {
            "silver": "silver/athena/",
            "gold_indicators": "gold/athena/indicators/",
            "gold_catalog": "gold/athena/catalog/",
        },
    }
    path = REPORTS_DIR / "cloud_publish.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Publicacion cloud generada: {path}")
    return 0


def publish_silver() -> list[dict[str, object]]:
    destination_root = SILVER_DIR / "athena"
    if destination_root.exists():
        shutil.rmtree(destination_root)
    published = []
    source_files = [path for path in SILVER_DIR.rglob("*.csv") if destination_root not in path.parents]
    for source in source_files:
        relative = source.relative_to(SILVER_DIR).with_suffix(".parquet")
        destination = destination_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        frame = pd.read_csv(source, low_memory=False)
        frame.to_parquet(destination, index=False, compression="snappy")
        published.append({
            "source": source.relative_to(PIPELINE_ROOT).as_posix(),
            "output": destination.relative_to(PIPELINE_ROOT).as_posix(),
            "rows": int(len(frame)),
            "columns": int(len(frame.columns)),
        })
    return published


def publish_gold() -> list[dict[str, object]]:
    destination_root = GOLD_DIR / "athena"
    if destination_root.exists():
        shutil.rmtree(destination_root)
    published = []

    indicators_path = GOLD_DIR / "indicators.csv"
    if not indicators_path.exists():
        raise FileNotFoundError(f"No existe Gold: {indicators_path}")
    indicators = pd.read_csv(indicators_path, low_memory=False)
    parsed_dates = pd.to_datetime(indicators.get("date"), errors="coerce")
    indicators["year"] = parsed_dates.dt.year.astype("Int64")
    indicators["month"] = parsed_dates.dt.month.astype("Int64")
    destination = destination_root / "indicators" / "data.parquet"
    destination.parent.mkdir(parents=True, exist_ok=True)
    indicators.to_parquet(destination, index=False, compression="snappy")
    published.append({
        "table": "indicators",
        "output": destination.relative_to(PIPELINE_ROOT).as_posix(),
        "rows": int(len(indicators)),
        "first_year": int(indicators["year"].dropna().min()) if indicators["year"].notna().any() else None,
        "latest_year": int(indicators["year"].dropna().max()) if indicators["year"].notna().any() else None,
    })

    catalog_path = GOLD_DIR / "indicator_catalog.csv"
    if catalog_path.exists():
        catalog = pd.read_csv(catalog_path, low_memory=False)
        destination = destination_root / "catalog" / "indicator_catalog.parquet"
        destination.parent.mkdir(parents=True, exist_ok=True)
        catalog.to_parquet(destination, index=False, compression="snappy")
        published.append({
            "table": "indicator_catalog",
            "output": destination.relative_to(PIPELINE_ROOT).as_posix(),
            "rows": int(len(catalog)),
        })
    return published


if __name__ == "__main__":
    raise SystemExit(main())
