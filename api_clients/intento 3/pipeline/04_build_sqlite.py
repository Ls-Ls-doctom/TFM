from __future__ import annotations

import sqlite3

import pandas as pd

from _common import GOLD_COLUMNS, GOLD_DIR, REPORTS_DIR, ensure_dirs, now, relative, sqlite_connect, write_json


DB_PATH = GOLD_DIR / "iseu_indicadores.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT NOT NULL,
    district TEXT,
    variable TEXT NOT NULL,
    value REAL NOT NULL,
    date TEXT NOT NULL,
    source TEXT NOT NULL,
    quality_score INTEGER,
    category TEXT,
    unit TEXT
);

CREATE INDEX IF NOT EXISTS idx_indicators_city ON indicators(city);
CREATE INDEX IF NOT EXISTS idx_indicators_variable ON indicators(variable);
CREATE INDEX IF NOT EXISTS idx_indicators_date ON indicators(date);
CREATE INDEX IF NOT EXISTS idx_indicators_category ON indicators(category);

CREATE TABLE IF NOT EXISTS indicator_catalog (
    variable TEXT PRIMARY KEY,
    category TEXT,
    unit TEXT,
    sources TEXT,
    cities TEXT,
    rows INTEGER
);

CREATE TABLE IF NOT EXISTS load_report (
    loaded_at TEXT,
    source_file TEXT,
    rows_loaded INTEGER
);
"""


def main() -> int:
    ensure_dirs()
    indicators_path = GOLD_DIR / "indicators.csv"
    if not indicators_path.exists():
        raise FileNotFoundError(f"No existe {indicators_path}. Ejecuta primero pipeline/03_build_gold.py.")

    indicators = pd.read_csv(indicators_path, low_memory=False)
    for column in GOLD_COLUMNS:
        if column not in indicators.columns:
            indicators[column] = ""
    indicators = indicators[GOLD_COLUMNS].copy()
    indicators["value"] = pd.to_numeric(indicators["value"], errors="coerce")
    indicators["quality_score"] = pd.to_numeric(indicators["quality_score"], errors="coerce").fillna(0).astype(int)
    indicators = indicators.dropna(subset=["city", "variable", "value", "date", "source"])

    catalog_path = GOLD_DIR / "indicator_catalog.csv"
    catalog = pd.read_csv(catalog_path, low_memory=False) if catalog_path.exists() else build_catalog(indicators)

    with sqlite_connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM indicators")
        conn.execute("DELETE FROM indicator_catalog")
        conn.execute("DELETE FROM load_report")
        indicators.to_sql("indicators", conn, if_exists="append", index=False)
        catalog.to_sql("indicator_catalog", conn, if_exists="append", index=False)
        conn.execute(
            "INSERT INTO load_report (loaded_at, source_file, rows_loaded) VALUES (?, ?, ?)",
            (now(), relative(indicators_path), int(len(indicators))),
        )
        rows_by_city = read_sql(conn, "SELECT city, COUNT(*) AS rows FROM indicators GROUP BY city ORDER BY rows DESC")
        rows_by_variable = read_sql(
            conn, "SELECT variable, COUNT(*) AS rows FROM indicators GROUP BY variable ORDER BY rows DESC"
        )

    summary = {
        "loaded_at": now(),
        "database": relative(DB_PATH),
        "source_file": relative(indicators_path),
        "rows_loaded": int(len(indicators)),
        "catalog_rows": int(len(catalog)),
        "rows_by_city": rows_by_city,
        "rows_by_variable": rows_by_variable,
    }
    write_json(REPORTS_DIR / "sqlite_build.json", summary)

    print(f"SQLite Gold creado: {DB_PATH}")
    print(f"Filas indicators: {len(indicators)}")
    return 0


def build_catalog(indicators: pd.DataFrame) -> pd.DataFrame:
    if indicators.empty:
        return pd.DataFrame(columns=["variable", "category", "unit", "sources", "cities", "rows"])
    return (
        indicators.groupby(["variable", "category", "unit"], as_index=False)
        .agg(
            sources=("source", lambda values: "|".join(sorted(set(map(str, values))))),
            cities=("city", lambda values: "|".join(sorted(set(map(str, values))))),
            rows=("variable", "size"),
        )
        .sort_values(["category", "variable"])
    )


def read_sql(conn: sqlite3.Connection, query: str) -> list[dict[str, object]]:
    return pd.read_sql_query(query, conn).to_dict(orient="records")


if __name__ == "__main__":
    raise SystemExit(main())
