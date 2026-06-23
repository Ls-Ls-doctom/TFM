from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from _common import BRONZE_DIR, REPORTS_DIR, count_csv_rows, ensure_dirs, now, relative, write_csv, write_json


def main() -> int:
    ensure_dirs()
    if not BRONZE_DIR.exists():
        raise FileNotFoundError(f"No existe Bronze: {BRONZE_DIR}. Ejecuta primero APIS/run_all.py.")

    rows: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    for path in sorted(BRONZE_DIR.rglob("*")):
        if not path.is_file():
            continue
        row = profile_file(path)
        rows.append(row)
        if path.name.endswith("manifest_raw.json") or path.name.endswith("_manifest.json"):
            manifests.append(read_manifest_summary(path))

    inventory = pd.DataFrame(rows)
    out_csv = REPORTS_DIR / "inventory_bronze.csv"
    write_csv(inventory, out_csv)

    summary = {
        "generated_at": now(),
        "bronze_dir": relative(BRONZE_DIR),
        "files_total": int(len(inventory)),
        "bytes_total": int(inventory["bytes"].sum()) if not inventory.empty else 0,
        "files_by_scope": inventory.groupby("scope").size().to_dict() if not inventory.empty else {},
        "files_by_source": inventory.groupby("source").size().to_dict() if not inventory.empty else {},
        "files_by_extension": inventory.groupby("extension").size().to_dict() if not inventory.empty else {},
        "csv_rows_detected": int(inventory["rows_detected"].fillna(0).sum()) if not inventory.empty else 0,
        "inventory_csv": relative(out_csv),
        "manifests": manifests,
    }
    write_json(REPORTS_DIR / "inventory_bronze.json", summary)

    print(f"Inventario Bronze: {out_csv}")
    print(f"Archivos: {summary['files_total']}")
    print(f"Filas CSV detectadas: {summary['csv_rows_detected']}")
    return 0


def profile_file(path: Path) -> dict[str, Any]:
    rel_parts = path.relative_to(BRONZE_DIR).parts
    scope = rel_parts[0] if rel_parts else ""
    source = rel_parts[1] if len(rel_parts) > 1 else ""
    extension = path.suffix.lower() or "sin_extension"
    rows_detected = None
    encoding = ""
    separator = ""
    columns: list[str] = []
    if extension == ".csv":
        rows_detected, encoding, separator, columns = count_csv_rows(path)
    return {
        "scope": scope,
        "source": source,
        "file": relative(path),
        "extension": extension,
        "bytes": path.stat().st_size,
        "rows_detected": rows_detected,
        "encoding_detected": encoding,
        "separator_detected": separator,
        "columns_detected": "|".join(columns[:80]),
        "columns_count": len(columns),
    }


def read_manifest_summary(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"file": relative(path), "status": "ERROR", "error": str(exc)}
    resources = payload.get("resources", [])
    return {
        "file": relative(path),
        "api": payload.get("api", ""),
        "status": payload.get("status", ""),
        "resources_total": len(resources) if isinstance(resources, list) else payload.get("resources_total", 0),
        "resources_ok": payload.get("resources_ok", ""),
        "timestamp": payload.get("timestamp", payload.get("generated_at", "")),
    }


if __name__ == "__main__":
    raise SystemExit(main())
