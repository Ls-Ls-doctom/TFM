from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EDA_DIR = PROJECT_ROOT / "pag_web" / "Procesos" / "Datasets" / "eda_bronze"
DOWNLOAD_DETAIL_PATH = EDA_DIR / "descarga_recursos_bronze.csv"
OUTPUT_PATH = EDA_DIR / "filas_descargadas_unificadas.csv"
REPORT_PATH = EDA_DIR / "filas_descargadas_unificadas.json"

OUTPUT_COLUMNS = [
    "source",
    "dataset_id",
    "dataset_title",
    "resource_name",
    "resource_format",
    "iseu_topics",
    "resource_url",
    "raw_file",
    "row_number",
    "record_json",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Une los CSV descargados desde Bronze en una tabla raw de staging.")
    parser.add_argument("--limit", type=int, default=0, help="Limite opcional de filas totales para pruebas.")
    args = parser.parse_args()

    details = pd.read_csv(DOWNLOAD_DETAIL_PATH, low_memory=False)
    ok = details[(details["status"] == "OK") & (details["download_kind"] == "csv")].copy()

    rows_written = 0
    resources_loaded = 0
    errors: list[dict[str, Any]] = []

    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()

        for _, resource in ok.iterrows():
            path = PROJECT_ROOT / str(resource["output_file"])
            if not path.exists():
                errors.append({"resource": resource.get("resource_name", ""), "error": f"No existe {path}"})
                continue
            try:
                loaded = write_resource_rows(writer, resource, path, args.limit, rows_written)
                rows_written += loaded
                resources_loaded += 1
                if args.limit and rows_written >= args.limit:
                    break
            except Exception as exc:
                errors.append({"resource": resource.get("resource_name", ""), "file": str(path), "error": str(exc)})

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_detail": relative(DOWNLOAD_DETAIL_PATH),
        "output_file": relative(OUTPUT_PATH),
        "resources_loaded": resources_loaded,
        "rows_written": rows_written,
        "errors": errors,
    }
    REPORT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Dataset unificado: {OUTPUT_PATH}")
    print(f"Recursos cargados: {resources_loaded}")
    print(f"Filas escritas: {rows_written}")
    print(f"Errores: {len(errors)}")


def write_resource_rows(
    writer: csv.DictWriter,
    resource: pd.Series,
    path: Path,
    limit: int,
    rows_written_before: int,
) -> int:
    loaded = 0
    for encoding in ("utf-8", "utf-8-sig", "latin1"):
        try:
            for chunk in pd.read_csv(path, sep=None, engine="python", chunksize=25_000, encoding=encoding, on_bad_lines="skip"):
                chunk = chunk.where(pd.notna(chunk), None)
                for record in chunk.to_dict(orient="records"):
                    if limit and rows_written_before + loaded >= limit:
                        return loaded
                    loaded += 1
                    writer.writerow(
                        {
                            "source": resource.get("source", ""),
                            "dataset_id": resource.get("dataset_id", ""),
                            "dataset_title": resource.get("dataset_title", ""),
                            "resource_name": resource.get("resource_name", ""),
                            "resource_format": resource.get("resource_format", ""),
                            "iseu_topics": resource.get("iseu_topics", ""),
                            "resource_url": resource.get("resource_url", ""),
                            "raw_file": relative(path),
                            "row_number": loaded,
                            "record_json": json.dumps(record, ensure_ascii=False, default=str),
                        }
                    )
            return loaded
        except Exception:
            loaded = 0
            continue
    raise ValueError("No se pudo leer el CSV con codificaciones conocidas")


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()