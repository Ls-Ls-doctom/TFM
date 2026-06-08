"""
diagnostico_datos.py
====================
Muestra en consola el flujo completo de datos del TFM:
  1. Archivos RAW  -> filas brutas por fuente
  2. Limpieza      -> filas limpias y registros descartados
  3. SQLite        -> filas en tabla indicadores + tablas detalle

Ejecutar desde la raiz del proyecto:
    python diagnostico_datos.py
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "api_clients" / "data"
CLEAN_DIR = ROOT / "pag_web" / "Procesos" / "Datasets" / "limpios"
DB_PATH = ROOT / "pag_web" / "Procesos" / "Datasets" / "iseu_datos.sqlite"

SEP = "=" * 72

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def count_csv(path: Path) -> int:
    """Cuenta filas de un CSV sin cargar todo en memoria."""
    if not path.exists():
        return -1
    try:
        df = pd.read_csv(path, low_memory=False)
        return len(df)
    except Exception:
        return -1


def fmt(n: int) -> str:
    return f"{n:>10,}" if n >= 0 else f"{'N/A':>10}"


def pct(clean: int, raw: int) -> str:
    if raw <= 0 or clean < 0:
        return ""
    p = clean / raw * 100
    return f"  ({p:.1f}% del bruto)"


# ---------------------------------------------------------------------------
# 1. Datos RAW
# ---------------------------------------------------------------------------
RAW_FILES = [
    ("INE",         RAW_DIR / "ine"         / "ine_raw.csv"),
    ("Idescat",     RAW_DIR / "idescat"     / "idescat_raw.csv"),
    ("REE precios", RAW_DIR / "ree"         / "ree_precios_raw.csv"),
    ("REE demanda", RAW_DIR / "ree"         / "ree_demanda_raw.csv"),
    ("SEPE paro",   RAW_DIR / "empleo"      / "sepe_paro_raw.csv"),
    ("SEPE contra", RAW_DIR / "empleo"      / "sepe_contratos_raw.csv"),
    ("BCN aire",    RAW_DIR / "opendata_bcn"/ "bcn_aire_raw.csv"),
    ("BCN alquiler",RAW_DIR / "opendata_bcn"/ "bcn_taxa_lloguer_od.csv"),  # GPKG converted if present
    ("BCN equip.",  RAW_DIR / "opendata_bcn"/ "bcn_equipamientos_raw.csv"),
    ("BCN licenc.", RAW_DIR / "opendata_bcn"/ "bcn_licencias_raw.csv"),
    ("BCN movil.",  RAW_DIR / "opendata_bcn"/ "bcn_movilidad_raw.csv"),
    ("BCN pobla.",  RAW_DIR / "opendata_bcn"/ "bcn_poblacion_raw.csv"),
    ("BCN segur.",  RAW_DIR / "opendata_bcn"/ "bcn_seguridad_raw.csv"),
    ("BCN transp.", RAW_DIR / "opendata_bcn"/ "bcn_transporte_raw.csv"),
    ("BCN turismo", RAW_DIR / "opendata_bcn"/ "bcn_turismo_raw.csv"),
    ("BCN z.verde", RAW_DIR / "opendata_bcn"/ "bcn_zonas_verdes_raw.csv"),
    ("MITMA XLS",   RAW_DIR / "mitma"       / "precio_m2_venta_raw.xls"),
]

# ---------------------------------------------------------------------------
# 2. Datos LIMPIOS (CSV en limpios/)
# ---------------------------------------------------------------------------
CLEAN_FILES = [
    ("INE",          CLEAN_DIR / "ine_limpio.csv"),
    ("Idescat",      CLEAN_DIR / "idescat_limpio.csv"),
    ("REE precios",  CLEAN_DIR / "ree_precios_limpio.csv"),
    ("REE demanda",  CLEAN_DIR / "ree_demanda_limpio.csv"),
    ("SEPE paro",    CLEAN_DIR / "sepe_paro_limpio.csv"),
    ("SEPE contra.", CLEAN_DIR / "sepe_contratos_limpio.csv"),
    ("BCN aire",     CLEAN_DIR / "bcn_aire_limpio.csv"),
    ("BCN alquiler", CLEAN_DIR / "bcn_alquiler_limpio.csv"),
    ("BCN equip.",   CLEAN_DIR / "bcn_equipamientos_limpio.csv"),
    ("BCN licenc.",  CLEAN_DIR / "bcn_licencias_limpio.csv"),
    ("BCN movil.",   CLEAN_DIR / "bcn_movilidad_limpio.csv"),
    ("BCN pobla.",   CLEAN_DIR / "bcn_poblacion_limpio.csv"),
    ("BCN segur.",   CLEAN_DIR / "bcn_seguridad_limpio.csv"),
    ("BCN transp.",  CLEAN_DIR / "bcn_transporte_limpio.csv"),
    ("BCN turismo",  CLEAN_DIR / "bcn_turismo_limpio.csv"),
    ("BCN z.verde",  CLEAN_DIR / "bcn_zonas_verdes_limpio.csv"),
    ("MITMA m2",     CLEAN_DIR / "mitma_precio_m2_vivienda_limpio.csv"),
]

# Mapa nombre -> raw rows para calcular descarte
RAW_MAP = {label: count_csv(path) for label, path in RAW_FILES if path.suffix == ".csv"}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def build_diagnostic() -> dict:
    raw_counts: dict[str, int] = {}
    total_raw = 0
    for label, path in RAW_FILES:
        if path.suffix in (".xls", ".xlsx", ".gpkg"):
            raw_counts[label] = -1
            continue
        n = count_csv(path)
        raw_counts[label] = n
        if n >= 0:
            total_raw += n

    clean_counts: dict[str, int] = {}
    total_raw_paired = 0
    total_clean = 0
    for label, path in CLEAN_FILES:
        clean_n = count_csv(path)
        clean_counts[label] = clean_n
        raw_n = raw_counts.get(label, -1)
        if raw_n >= 0 and clean_n >= 0:
            total_raw_paired += raw_n
            total_clean += clean_n

    sqlite_payload = {
        "ready": DB_PATH.exists(),
        "indicadores_rows": 0,
        "detail_tables": [],
        "detail_rows": 0,
        "by_source": [],
    }
    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as conn:
            sqlite_payload["indicadores_rows"] = conn.execute("SELECT COUNT(*) FROM indicadores").fetchone()[0]
            sqlite_payload["by_source"] = [
                {"source": source, "rows": rows}
                for source, rows in conn.execute(
                    "SELECT source, COUNT(*) FROM indicadores GROUP BY source ORDER BY COUNT(*) DESC"
                ).fetchall()
            ]
            sqlite_payload["detail_tables"] = [
                {"table": table, "rows": rows, "columns": cols, "source_file": source_file}
                for table, rows, cols, source_file in conn.execute(
                    """
                    SELECT table_name, rows_loaded, columns_loaded, source_file
                    FROM cargas_detalle
                    ORDER BY rows_loaded DESC
                    """
                ).fetchall()
            ]
            sqlite_payload["detail_rows"] = sum(item["rows"] for item in sqlite_payload["detail_tables"])

    return {
        "raw": {
            "total_csv_rows": total_raw,
            "files": [{"label": label, "path": str(path), "rows": raw_counts.get(label, -1)} for label, path in RAW_FILES],
        },
        "clean": {
            "total_paired_raw_rows": total_raw_paired,
            "total_clean_rows": total_clean,
            "retention_pct": round((total_clean / total_raw_paired * 100), 2) if total_raw_paired else None,
            "files": [{"label": label, "path": str(path), "rows": clean_counts.get(label, -1)} for label, path in CLEAN_FILES],
            "indicadores_rows": count_csv(CLEAN_DIR / "indicadores_limpios.csv"),
        },
        "sqlite": sqlite_payload,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnostico de datos TFM ISEU")
    parser.add_argument("--json", action="store_true", help="Imprime el diagnostico en formato JSON.")
    args = parser.parse_args()

    diagnostic = build_diagnostic()
    if args.json:
        print(json.dumps(diagnostic, ensure_ascii=False, indent=2))
        return

    print()
    print(SEP)
    print("  DIAGNOSTICO DE DATOS  -  TFM ISEU")
    print(SEP)

    # ------------------------------------------------------------------
    # BLOQUE 1: RAW
    # ------------------------------------------------------------------
    print()
    print("[ 1 ]  ARCHIVOS BRUTOS (RAW)")
    print("-" * 72)
    print(f"  {'Fuente':<20} {'Filas':>10}  {'Ruta'}")
    print(f"  {'-'*20} {'-'*10}  {'-'*38}")

    total_raw = diagnostic["raw"]["total_csv_rows"]
    raw_counts: dict[str, int] = {item["label"]: item["rows"] for item in diagnostic["raw"]["files"]}
    for label, path in RAW_FILES:
        if path.suffix in (".xls", ".xlsx", ".gpkg"):
            mark = "  (binario, ver limpio)"
            print(f"  {label:<20} {'---':>10}  {mark}")
            continue
        n = raw_counts.get(label, -1)
        estado = "" if n >= 0 else "  [NO ENCONTRADO]"
        print(f"  {label:<20} {fmt(n)}  {estado}")

    print(f"  {'TOTAL CSV brutos':<20} {fmt(total_raw)}")

    # ------------------------------------------------------------------
    # BLOQUE 2: LIMPIEZA
    # ------------------------------------------------------------------
    print()
    print("[ 2 ]  ARCHIVOS LIMPIOS  (tras proceso clean_datasets.py)")
    print("-" * 72)
    print(f"  {'Fuente':<20} {'Bruto':>10} {'Limpio':>10} {'Descartados':>12}  {'Retenc.'}")
    print(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*12}  {'-'*8}")

    total_raw_paired = 0
    total_clean = 0
    clean_counts: dict[str, int] = {}
    for label, path in CLEAN_FILES:
        clean_n = count_csv(path)
        clean_counts[label] = clean_n
        # busca coincidencia en raw (etiqueta puede diferir ligeramente)
        raw_n = raw_counts.get(label, -1)
        if raw_n >= 0 and clean_n >= 0:
            discarded = raw_n - clean_n
            retention = f"{clean_n/raw_n*100:.1f}%"
            total_raw_paired += raw_n
            total_clean += clean_n
        else:
            discarded = -1
            retention = "---"

        disc_str = f"{discarded:>12,}" if discarded >= 0 else f"{'---':>12}"
        print(f"  {label:<20} {fmt(raw_n)} {fmt(clean_n)} {disc_str}  {retention}")

    total_discarded = total_raw_paired - total_clean
    ret_total = f"{total_clean/total_raw_paired*100:.1f}%" if total_raw_paired else "---"
    print(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*12}  {'-'*8}")
    print(f"  {'TOTAL (pares CSV)':<20} {fmt(total_raw_paired)} {fmt(total_clean)} {total_discarded:>12,}  {ret_total}")

    # Tabla de indicadores unificada
    ind_path = CLEAN_DIR / "indicadores_limpios.csv"
    ind_n = count_csv(ind_path)
    print()
    print(f"  indicadores_limpios.csv  ->  {ind_n:,} filas  (union normalizada de todos los facts)")

    # ------------------------------------------------------------------
    # BLOQUE 3: SQLITE
    # ------------------------------------------------------------------
    print()
    print("[ 3 ]  BASE DE DATOS SQLITE  (iseu_datos.sqlite)")
    print("-" * 72)

    if not DB_PATH.exists():
        print("  [!] No existe la base de datos. Ejecuta build_sqlite.py primero.")
        print()
        return

    with sqlite3.connect(DB_PATH) as conn:
        # Tabla indicadores por fuente
        rows_indicadores = conn.execute("SELECT COUNT(*) FROM indicadores").fetchone()[0]
        by_source = conn.execute(
            "SELECT source, COUNT(*) AS filas FROM indicadores GROUP BY source ORDER BY filas DESC"
        ).fetchall()

        # Tablas detalle
        detail_tables = conn.execute(
            """
            SELECT table_name, rows_loaded, columns_loaded, source_file
            FROM cargas_detalle
            ORDER BY rows_loaded DESC
            """
        ).fetchall()

    print()
    print(f"  TABLA: indicadores   ->  {rows_indicadores:,} filas totales")
    print(f"  {'Fuente':<25} {'Filas en SQL':>12}  {'% del total':>10}")
    print(f"  {'-'*25} {'-'*12}  {'-'*10}")
    for source, n in by_source:
        p = n / rows_indicadores * 100
        print(f"  {source:<25} {n:>12,}  {p:>9.1f}%")

    print()
    print(f"  TABLAS DETALLE  ({len(detail_tables)} tablas)")
    print(f"  {'Tabla':<40} {'Filas':>10} {'Cols':>6}")
    print(f"  {'-'*40} {'-'*10} {'-'*6}")
    total_detail = 0
    for tbl, rows, cols, _ in detail_tables:
        total_detail += rows
        print(f"  {tbl:<40} {rows:>10,} {cols:>6}")
    print(f"  {'-'*40} {'-'*10}")
    print(f"  {'TOTAL filas detalle':<40} {total_detail:>10,}")

    # ------------------------------------------------------------------
    # RESUMEN FINAL
    # ------------------------------------------------------------------
    print()
    print(SEP)
    print("  RESUMEN EJECUTIVO")
    print(SEP)
    print(f"  Filas brutas CSV             : {total_raw:>10,}")
    print(f"  Filas limpias CSV (pares)    : {total_clean:>10,}  ({ret_total} de retención)")
    print(f"  Indicadores en SQLite        : {rows_indicadores:>10,}")
    print(f"  Filas detalle en SQLite      : {total_detail:>10,}")
    print(f"  TOTAL filas en SQLite        : {rows_indicadores + total_detail:>10,}")
    print()
    print("  Fuentes que LLEGAN a SQL:", len(by_source))
    for source, _ in by_source:
        print(f"    - {source}")
    print()
    print(SEP)


if __name__ == "__main__":
    main()
