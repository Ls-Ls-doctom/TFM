"""
Paso 5 del pipeline: exporta a Parquet en S3 y registra en Glue:
  - gold/athena/indicadores → iseu_indicadores  (Silver unificada, ~94k filas)
  - gold/athena/semantic_obs → iseu_semantic_obs (~106k filas)
  - silver/athena/<name> → iseu_<name>  (tablas brutas Silver, ~182k filas)
Se ejecuta después de 04_build_sqlite.py.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import boto3
import pandas as pd

from _common import BASE_DIR, GOLD_DIR, REPORTS_DIR, now, relative, write_json


DATABASE = os.getenv("ATHENA_DATABASE", "iseu")
REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "eu-west-1"))
BUCKET = os.getenv("ISEU_BUCKET", "")

DB_PATH = GOLD_DIR / "iseu_indicadores.sqlite"
ATHENA_DIR = GOLD_DIR / "athena"

# Logical table name → (s3 subfolder, glue table name)
EXPORT_TABLES: dict[str, tuple[str, str]] = {
    "indicadores":           ("indicadores",  "iseu_indicadores"),
    "semantic_observations": ("semantic_obs", "iseu_semantic_obs"),
}

# Parquet/Glue type mapping from pandas dtype
_DTYPE_MAP = {
    "object":  "string",
    "int64":   "bigint",
    "int32":   "int",
    "float64": "double",
    "float32": "float",
    "bool":    "boolean",
}


def pandas_to_glue_type(dtype: str) -> str:
    return _DTYPE_MAP.get(str(dtype), "string")


def glue_columns(df: pd.DataFrame) -> list[dict[str, str]]:
    return [{"Name": col, "Type": pandas_to_glue_type(str(dtype))} for col, dtype in df.dtypes.items()]


def upsert_glue_table(glue_client: Any, s3_location: str, table_name: str, columns: list[dict[str, str]]) -> None:
    table_input: dict[str, Any] = {
        "Name": table_name,
        "StorageDescriptor": {
            "Columns": columns,
            "Location": s3_location,
            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "SerdeInfo": {
                "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                "Parameters": {"serialization.format": "1"},
            },
            "Compressed": False,
            "StoredAsSubDirectories": False,
        },
        "PartitionKeys": [],
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {"classification": "parquet", "parquet.compression": "SNAPPY"},
    }
    try:
        glue_client.update_table(DatabaseName=DATABASE, TableInput=table_input)
    except glue_client.exceptions.EntityNotFoundException:
        glue_client.create_table(DatabaseName=DATABASE, TableInput=table_input)


def export_table(conn: sqlite3.Connection, sql_table: str, parquet_dir: Path) -> pd.DataFrame:
    df = pd.read_sql_query(f"SELECT * FROM {sql_table}", conn)  # noqa: S608
    # Drop autoincrement id — not useful in Athena
    df = df.drop(columns=["id"], errors="ignore")
    # Coerce value column to float
    if "value" in df.columns:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    parquet_dir.mkdir(parents=True, exist_ok=True)
    out = parquet_dir / "data.parquet"
    df.to_parquet(out, index=False, compression="snappy")
    return df


def export_and_register(
    conn: sqlite3.Connection,
    glue_client: Any,
    sql_table: str,
    parquet_dir: Path,
    s3_location: str,
    glue_name: str,
    report: dict[str, Any],
) -> None:
    df = export_table(conn, sql_table, parquet_dir)
    cols = glue_columns(df)
    if glue_client and s3_location:
        upsert_glue_table(glue_client, s3_location, glue_name, cols)
        print(f"  Glue {glue_name}: {len(df)} filas, {len(cols)} columnas — {s3_location}")
    else:
        print(f"  (sin ISEU_BUCKET) Parquet generado: {parquet_dir / 'data.parquet'}")
    report["tables"].append({
        "sql_table": sql_table,
        "glue_table": glue_name,
        "s3_location": s3_location,
        "rows": int(len(df)),
        "columns": len(cols),
        "parquet": relative(parquet_dir / "data.parquet"),
    })


def main() -> int:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"No existe {DB_PATH}. Ejecuta primero pipeline/04_build_sqlite.py con ISEU_BUILD_SQLITE=true."
        )

    glue_client = boto3.client("glue", region_name=REGION) if BUCKET else None
    report: dict[str, Any] = {"generated_at": now(), "tables": []}

    with sqlite3.connect(DB_PATH) as conn:
        # Fixed Gold tables
        for sql_table, (s3_subfolder, glue_name) in EXPORT_TABLES.items():
            parquet_dir = ATHENA_DIR / s3_subfolder
            s3_location = f"s3://{BUCKET}/gold/athena/{s3_subfolder}/" if BUCKET else ""
            export_and_register(conn, glue_client, sql_table, parquet_dir, s3_location, glue_name, report)

        # Silver raw tables (any silver_* in SQLite)
        silver_names: list[str] = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'silver_%' ORDER BY name"
            ).fetchall()
        ]
        for sql_table in silver_names:
            glue_name = f"iseu_{sql_table}"
            parquet_dir = ATHENA_DIR.parent.parent / "silver" / "athena" / sql_table
            s3_location = f"s3://{BUCKET}/silver/athena/{sql_table}/" if BUCKET else ""
            export_and_register(conn, glue_client, sql_table, parquet_dir, s3_location, glue_name, report)

    write_json(REPORTS_DIR / "athena_export.json", report)
    total = sum(t["rows"] for t in report["tables"])
    print(f"Export Athena completado: {total} filas en {len(report['tables'])} tablas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
