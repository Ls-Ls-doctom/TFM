from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EDA_DIR = PROJECT_ROOT / "pag_web" / "Procesos" / "Datasets" / "eda_bronze"
CATALOG_PATH = EDA_DIR / "catalogo_recursos_bronze.csv"
OUTPUT_DIR = PROJECT_ROOT / "api_clients" / "intento 3" / "data_lake" / "bronze" / "downloaded_resources"
REPORT_PATH = EDA_DIR / "descarga_recursos_bronze.json"
DETAIL_PATH = EDA_DIR / "descarga_recursos_bronze.csv"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ISEU-TFM-ResourceDownloader/1.0"

CSV_FORMAT_HINTS = ("csv", "text/csv", "comma-separated")
JSON_FORMAT_HINTS = ("json", "geojson", "application/json")
EXCEL_FORMAT_HINTS = ("xlsx", "xls", "spreadsheet", "excel")
ZIP_FORMAT_HINTS = ("zip", "compressed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga recursos tabulares desde el catalogo Bronze hasta un objetivo de filas.")
    parser.add_argument("--target-rows", type=int, default=300_000, help="Objetivo minimo de filas descargadas.")
    parser.add_argument("--max-resources", type=int, default=80, help="Maximo de recursos a intentar.")
    parser.add_argument("--max-file-mb", type=int, default=80, help="Tamano maximo por archivo descargado.")
    parser.add_argument("--min-year", type=int, default=2015, help="Descarta recursos con ano explicito anterior a este valor.")
    parser.add_argument("--min-resources-per-source", type=int, default=3, help="Minimo de recursos a intentar por fuente antes de cortar por filas.")
    parser.add_argument("--sources", default="", help="Fuentes separadas por coma. Por defecto usa todas las fuentes descargables.")
    parser.add_argument("--all", action="store_true", help="Intenta descargar todos los candidatos disponibles desde min-year, sin cortar por filas.")
    parser.add_argument("--force", action="store_true", help="Vuelve a descargar aunque el archivo exista.")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    catalog = pd.read_csv(CATALOG_PATH, low_memory=False)
    selected_sources = [item.strip() for item in args.sources.split(",") if item.strip()]
    candidates = prepare_candidates(catalog, min_year=args.min_year, selected_sources=selected_sources)
    if args.all:
        args.target_rows = 10**18
        args.max_resources = len(candidates)
        args.min_resources_per_source = 0

    results: list[dict[str, Any]] = []
    rows_total = 0
    attempted = 0

    attempts_by_source = {source: 0 for source in candidates["source"].dropna().astype(str).unique()}

    for candidate in iter_balanced_candidates(candidates, args.target_rows, args.max_resources, args.min_resources_per_source, lambda: rows_total, attempts_by_source):
        attempted += 1
        result = download_candidate(candidate, max_file_mb=args.max_file_mb, force=args.force)
        results.append(result)
        source = str(result.get("source", ""))
        attempts_by_source[source] = attempts_by_source.get(source, 0) + 1
        if result.get("status") == "OK":
            rows_total += int(result.get("rows_detected") or 0)
        print(f"{attempted:03d} {result['status']:>9} filas={result.get('rows_detected', 0):>8} total={rows_total:>8} {result['source']}/{result['dataset_title'][:70]}")

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target_rows": args.target_rows,
        "all_mode": args.all,
        "rows_downloaded": rows_total,
        "target_reached": rows_total >= args.target_rows,
        "resources_attempted": attempted,
        "resources_ok": sum(1 for item in results if item.get("status") == "OK"),
        "resources_error": sum(1 for item in results if item.get("status") == "ERROR"),
        "min_year": args.min_year,
        "min_resources_per_source": args.min_resources_per_source,
        "sources": sorted(attempts_by_source),
        "attempts_by_source": attempts_by_source,
        "rows_by_source": rows_by_source(results),
        "output_dir": relative(OUTPUT_DIR),
        "details_csv": relative(DETAIL_PATH),
        "results": results,
    }
    REPORT_PATH.write_text(json.dumps(to_jsonable(summary), ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(results).to_csv(DETAIL_PATH, index=False, encoding="utf-8")

    print("\nResumen descarga Bronze")
    print(f"Filas descargadas: {rows_total}")
    print(f"Objetivo alcanzado: {rows_total >= args.target_rows}")
    print(f"Recursos OK: {summary['resources_ok']} | errores: {summary['resources_error']}")
    print(f"Informe: {REPORT_PATH}")


def prepare_candidates(catalog: pd.DataFrame, min_year: int, selected_sources: list[str]) -> pd.DataFrame:
    df = catalog.copy()
    for column in ("resource_url", "resource_format", "relevance_score", "scope", "source", "dataset_title"):
        if column not in df.columns:
            df[column] = ""

    df["resource_url"] = df["resource_url"].fillna("").astype(str)
    df = df[df["resource_url"].str.len() > 0]
    df["resource_url"] = df.apply(lambda row: normalize_url(row["resource_url"], row.get("source", "")), axis=1)
    df = df[df["resource_url"].str.startswith(("http://", "https://"))]

    fmt = df["resource_format"].fillna("").astype(str).str.lower()
    url = df["resource_url"].str.lower()
    df["download_kind"] = ""
    df.loc[fmt.apply(lambda value: any(hint in value for hint in CSV_FORMAT_HINTS)) | url.str.contains(r"\.csv(?:$|[?#])"), "download_kind"] = "csv"
    df.loc[fmt.apply(lambda value: any(hint in value for hint in JSON_FORMAT_HINTS)) | url.str.contains(r"\.(?:json|geojson)(?:$|[?#])"), "download_kind"] = "json"
    df.loc[fmt.apply(lambda value: any(hint in value for hint in EXCEL_FORMAT_HINTS)) | url.str.contains(r"\.(?:xlsx|xls)(?:$|[?#])"), "download_kind"] = "excel"
    df.loc[fmt.apply(lambda value: any(hint in value for hint in ZIP_FORMAT_HINTS)) | url.str.contains(r"\.zip(?:$|[?#])"), "download_kind"] = "zip"
    df = df[df["download_kind"].isin(["csv", "json", "excel", "zip"])]

    df["relevance_score"] = pd.to_numeric(df["relevance_score"], errors="coerce").fillna(0)
    df = df[df["relevance_score"] > 0]
    df = df.drop_duplicates(subset=["resource_url"])
    if selected_sources:
        df = df[df["source"].isin(selected_sources)]

    df["explicit_year"] = df.apply(infer_candidate_year, axis=1)
    df = df[df["explicit_year"].isna() | (df["explicit_year"] >= min_year)]

    kind_priority = {"csv": 0, "excel": 1, "json": 2, "zip": 3}
    df["kind_priority"] = df["download_kind"].map(kind_priority).fillna(9)
    df["topic_count"] = df.get("iseu_topics", "").fillna("").astype(str).str.count(r"\|") + (df.get("iseu_topics", "").fillna("").astype(str).str.len() > 0).astype(int)

    return df.sort_values(
        ["source", "kind_priority", "relevance_score", "topic_count", "explicit_year"],
        ascending=[True, True, False, False, False],
    )


def iter_balanced_candidates(
    candidates: pd.DataFrame,
    target_rows: int,
    max_resources: int,
    min_resources_per_source: int,
    rows_total_getter,
    attempts_by_source: dict[str, int],
):
    groups = {
        source: group.reset_index(drop=True)
        for source, group in candidates.groupby("source", sort=True)
    }
    positions = {source: 0 for source in groups}
    attempted = 0

    while attempted < max_resources:
        progressed = False
        min_pending = any(
            attempts_by_source.get(source, 0) < min_resources_per_source and positions[source] < len(group)
            for source, group in groups.items()
        )
        if rows_total_getter() >= target_rows and not min_pending:
            break

        for source in sorted(groups):
            group = groups[source]
            if positions[source] >= len(group):
                continue
            if rows_total_getter() >= target_rows and attempts_by_source.get(source, 0) >= min_resources_per_source:
                continue
            candidate = group.iloc[positions[source]]
            positions[source] += 1
            attempted += 1
            progressed = True
            yield candidate
            if attempted >= max_resources:
                break
        if not progressed:
            break


def download_candidate(candidate: pd.Series, max_file_mb: int, force: bool) -> dict[str, Any]:
    source = str(candidate.get("source", "unknown"))
    dataset_title = str(candidate.get("dataset_title", ""))
    resource_name = str(candidate.get("resource_name", ""))
    url = str(candidate.get("resource_url", ""))
    kind = str(candidate.get("download_kind", ""))
    extension = extension_for(candidate, kind)
    filename = safe_filename(f"{source}_{stable_id(url)}_{dataset_title}_{resource_name}{extension}")
    output_path = OUTPUT_DIR / source / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    base = base_result(candidate, output_path)

    try:
        if force or not output_path.exists():
            download_file(url, output_path, max_file_mb=max_file_mb)
        rows_detected = count_rows(output_path, kind)
        metadata_path = output_path.with_suffix(output_path.suffix + ".metadata.json")
        metadata_path.write_text(
            json.dumps(to_jsonable(base | {"status": "OK", "rows_detected": rows_detected, "bytes": output_path.stat().st_size}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return base | {"status": "OK", "rows_detected": rows_detected, "bytes": output_path.stat().st_size}
    except Exception as exc:
        error_path = output_path.with_suffix(output_path.suffix + ".error.json")
        error_path.parent.mkdir(parents=True, exist_ok=True)
        error_payload = base | {"status": "ERROR", "error": str(exc)}
        error_path.write_text(json.dumps(to_jsonable(error_payload), ensure_ascii=False, indent=2), encoding="utf-8")
        if output_path.exists() and output_path.stat().st_size == 0:
            output_path.unlink()
        return error_payload


def download_file(url: str, output_path: Path, max_file_mb: int) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/csv,application/json,application/geo+json,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        },
    )
    max_bytes = max_file_mb * 1024 * 1024
    try:
        response_handle = urllib.request.urlopen(request, timeout=120, context=ssl.create_default_context())
    except urllib.error.URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        fallback_context = ssl.create_default_context()
        fallback_context.check_hostname = False
        fallback_context.verify_mode = ssl.CERT_NONE
        response_handle = urllib.request.urlopen(request, timeout=120, context=fallback_context)

    with response_handle as response:
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > max_bytes:
            raise ValueError(f"Archivo demasiado grande segun Content-Length: {content_length} bytes")
        with output_path.open("wb") as file:
            copied = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > max_bytes:
                    raise ValueError(f"Archivo supera el limite de {max_file_mb} MB")
                file.write(chunk)


def count_rows(path: Path, kind: str) -> int:
    if kind == "json":
        return count_json_rows(path)
    if kind == "excel":
        return count_excel_rows(path)
    if kind == "zip":
        return count_zip_rows(path)
    return count_csv_rows(path)


def count_csv_rows(path: Path) -> int:
    for encoding in ("utf-8", "utf-8-sig", "latin1"):
        try:
            rows = 0
            for chunk in pd.read_csv(path, sep=None, engine="python", chunksize=50_000, encoding=encoding, on_bad_lines="skip"):
                rows += len(chunk)
            return rows
        except Exception:
            continue
    with path.open("r", encoding="utf-8", errors="replace") as file:
        return max(sum(1 for _ in file) - 1, 0)


def count_json_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as file:
        payload = json.load(file)
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("features", "result", "results", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
            if isinstance(value, dict):
                nested = value.get("features") or value.get("results") or value.get("items")
                if isinstance(nested, list):
                    return len(nested)
    return 1


def count_excel_rows(path: Path) -> int:
    try:
        sheets = pd.read_excel(path, sheet_name=None)
    except Exception:
        return 0
    return int(sum(len(sheet) for sheet in sheets.values()))


def count_zip_rows(path: Path) -> int:
    rows = 0
    try:
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                if not member.lower().endswith(".csv"):
                    continue
                with archive.open(member) as file:
                    rows += max(sum(1 for _ in file) - 1, 0)
    except zipfile.BadZipFile:
        return 0
    return rows


def extension_for(candidate: pd.Series, kind: str) -> str:
    url_path = urllib.parse.urlparse(str(candidate.get("resource_url", ""))).path.lower()
    suffix = Path(url_path).suffix
    if suffix in {".csv", ".json", ".geojson", ".xlsx", ".xls", ".zip"}:
        return suffix
    return {"csv": ".csv", "json": ".json", "excel": ".xlsx", "zip": ".zip"}.get(kind, ".dat")


def infer_candidate_year(candidate: pd.Series) -> float:
    text = " ".join(
        str(candidate.get(column, ""))
        for column in ("dataset_title", "dataset_description", "resource_name", "resource_url", "modified_at")
    )
    years = [int(match) for match in re.findall(r"\b(20\d{2}|19\d{2})\b", text)]
    return float(max(years)) if years else float("nan")


def rows_by_source(results: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for item in results:
        if item.get("status") != "OK":
            continue
        source = str(item.get("source", "unknown"))
        totals[source] = totals.get(source, 0) + int(item.get("rows_detected") or 0)
    return totals


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def base_result(candidate: pd.Series, output_path: Path) -> dict[str, Any]:
    return {
        "scope": candidate.get("scope", ""),
        "source": candidate.get("source", ""),
        "dataset_id": candidate.get("dataset_id", ""),
        "dataset_title": candidate.get("dataset_title", ""),
        "resource_name": candidate.get("resource_name", ""),
        "resource_format": candidate.get("resource_format", ""),
        "resource_url": candidate.get("resource_url", ""),
        "iseu_topics": candidate.get("iseu_topics", ""),
        "relevance_score": candidate.get("relevance_score", ""),
        "download_kind": candidate.get("download_kind", ""),
        "output_file": relative(output_path),
        "downloaded_at": datetime.now().isoformat(timespec="seconds"),
    }


def normalize_url(url: str, source: str) -> str:
    url = url.strip()
    if source == "zaragoza" and url.startswith("/"):
        url = "https://www.zaragoza.es" + url
    return urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%")


def safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    if len(value) <= 95:
        return value
    suffix = Path(value).suffix
    stem = value[: max(30, 95 - len(suffix))].rstrip("._")
    return stem + suffix


def stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()[:10]


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()