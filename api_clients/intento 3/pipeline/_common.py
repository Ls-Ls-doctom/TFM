from __future__ import annotations

import csv
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
BRONZE_DIR = BASE_DIR / "data_lake" / "bronze"
SILVER_DIR = BASE_DIR / "data_lake" / "silver"
GOLD_DIR = BASE_DIR / "data_lake" / "gold"
REPORTS_DIR = BASE_DIR / "reports"

TARGET_CITIES = {
    "08019": "Barcelona",
    "28079": "Madrid",
    "46250": "Valencia",
    "41091": "Sevilla",
    "48020": "Bilbao",
    "29067": "Malaga",
    "50297": "Zaragoza",
}

CITY_ALIASES = {
    "barcelona": "Barcelona",
    "madrid": "Madrid",
    "valencia": "Valencia",
    "sevilla": "Sevilla",
    "bilbao": "Bilbao",
    "malaga": "Malaga",
    "málaga": "Malaga",
    "zaragoza": "Zaragoza",
}

GOLD_COLUMNS = [
    "city",
    "district",
    "variable",
    "value",
    "date",
    "source",
    "quality_score",
    "category",
    "unit",
]


def ensure_dirs() -> None:
    for path in (SILVER_DIR, GOLD_DIR, REPORTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(BASE_DIR.resolve()))
    except ValueError:
        return str(path)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_column(value: object) -> str:
    text = str(value).strip().lower()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "à": "a",
        "è": "e",
        "ï": "i",
        "ü": "u",
        "ñ": "n",
        "ç": "c",
        "€": "eur",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "column"


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    seen: dict[str, int] = {}
    columns = []
    for column in out.columns:
        name = normalize_column(column)
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        columns.append(name)
    out.columns = columns
    return out


def read_csv_flexible(path: Path, nrows: int | None = None, header: int | str | None = "infer") -> pd.DataFrame:
    best_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        for separator in (";", ",", "|", "\t"):
            try:
                df = pd.read_csv(
                    path,
                    sep=separator,
                    encoding=encoding,
                    nrows=nrows,
                    header=header,
                    low_memory=False,
                )
                if df.shape[1] > 1 or separator == ",":
                    return df
            except Exception as exc:  # noqa: BLE001
                best_error = exc
    if best_error:
        raise best_error
    raise ValueError(f"No se pudo leer CSV: {path}")


def read_sepe_csv(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, sep=";", encoding="latin1", header=None, low_memory=False)
    if len(raw) < 2:
        return pd.DataFrame()
    header = [str(value).strip() for value in raw.iloc[1].tolist()]
    df = raw.iloc[2:].copy()
    df.columns = header
    df = df.dropna(how="all")
    return clean_columns(df)


def to_number(value: object) -> float | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("<"):
        text = text[1:].strip()
    text = text.replace(".", "").replace(",", ".")
    text = re.sub(r"[^0-9.\-]", "", text)
    if text in {"", "-", "."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_year_date(value: object) -> str:
    text = str(value)
    match = re.search(r"(20\d{2}|19\d{2})", text)
    return f"{match.group(1)}-01-01" if match else ""


def to_month_date(value: object) -> str:
    text = re.sub(r"\D", "", str(value))
    if len(text) >= 6:
        return f"{text[:4]}-{text[4:6]}-01"
    return to_year_date(value)


def municipality_code(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    match = re.search(r"(\d{5})", text)
    if match:
        return match.group(1)
    digits = re.sub(r"\D", "", text)
    return digits.zfill(5) if digits else ""


def infer_city_from_path(path: Path) -> str:
    parts = [part.lower() for part in path.parts]
    for key, city in CITY_ALIASES.items():
        if key in parts:
            return city
    text = str(path).lower()
    for key, city in CITY_ALIASES.items():
        if key in text:
            return city
    return ""


def gold_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for column in GOLD_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df = df[GOLD_COLUMNS].copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["quality_score"] = pd.to_numeric(df["quality_score"], errors="coerce").fillna(7).astype(int)
    df = df.dropna(subset=["value"])
    df = df[(df["city"].astype(str) != "") & (df["variable"].astype(str) != "") & (df["date"].astype(str) != "")]
    return df


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")


def count_csv_rows(path: Path) -> tuple[int | None, str, str, list[str]]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            sample = path.read_text(encoding=encoding, errors="strict")[:8192]
        except UnicodeDecodeError:
            continue
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t")
            sep = dialect.delimiter
        except csv.Error:
            sep = ","
        try:
            df = pd.read_csv(path, sep=sep, encoding=encoding, nrows=5, low_memory=False)
            rows = sum(1 for _ in path.open("r", encoding=encoding, errors="ignore")) - 1
            return max(rows, 0), encoding, sep, [str(column) for column in df.columns]
        except Exception:
            continue
    return None, "", "", []


def run_python(script: Path, args: list[str] | None = None) -> dict[str, Any]:
    command = [sys.executable, str(script)]
    if args:
        command.extend(args)
    started = now()
    proc = subprocess.run(command, cwd=BASE_DIR, text=True, capture_output=True)
    return {
        "script": relative(script),
        "args": args or [],
        "started_at": started,
        "finished_at": now(),
        "returncode": proc.returncode,
        "stdout": proc.stdout[-6000:],
        "stderr": proc.stderr[-6000:],
        "status": "OK" if proc.returncode == 0 else "ERROR",
    }


def sqlite_connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)
