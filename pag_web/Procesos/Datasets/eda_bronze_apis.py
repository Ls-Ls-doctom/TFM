from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BRONZE_DIR = PROJECT_ROOT / "api_clients" / "intento 3" / "data_lake" / "bronze"
SILVER_REPORT = PROJECT_ROOT / "api_clients" / "intento 3" / "data_lake" / "silver" / "barcelona" / "catalogo_limpieza_silver.json"
OUTPUT_DIR = PROJECT_ROOT / "pag_web" / "Procesos" / "Datasets" / "eda_bronze"

SQL_INDICATOR_COLUMNS = [
    "source",
    "dataset",
    "variable",
    "metric",
    "geo",
    "period",
    "value",
    "unit",
    "quality",
    "notes",
    "raw_file",
    "extracted_at",
]

ISEU_TOPICS = {
    "empleo": ["empleo", "paro", "desempleo", "contrato", "afiliacion", "trabajo", "ocupacion"],
    "vivienda": ["vivienda", "alquiler", "renta", "hipoteca", "tasacion", "m2", "inmueble"],
    "coste_vida": ["ipc", "precio", "coste", "consumo", "alimentos", "supermercado"],
    "movilidad": ["movilidad", "trafico", "transporte", "bicicleta", "metro", "bus", "aparcamiento"],
    "ambiente": ["aire", "ruido", "zonas verdes", "contaminacion", "clima", "temperatura", "emisiones"],
    "turismo": ["turismo", "hotel", "pernoctaciones", "visitantes", "alojamiento"],
    "actividad_economica": ["actividad economica", "licencias", "comercio", "empresa", "industria", "locales"],
    "poblacion": ["poblacion", "demografia", "habitantes", "censo", "padron"],
    "seguridad": ["seguridad", "accidentes", "delitos", "incidencias"],
    "servicios": ["equipamientos", "servicios", "escuela", "hospital", "centro civico"],
}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    inventory: list[dict[str, Any]] = []
    catalog_rows: list[dict[str, Any]] = []
    observation_rows: list[dict[str, Any]] = []

    for path in sorted(BRONZE_DIR.rglob("*")):
        if not path.is_file():
            continue
        scope, source = infer_scope_source(path)
        inventory.append(build_inventory_row(path, scope, source))

        if path.suffix.lower() == ".rdf" and scope == "municipios" and source == "madrid":
            catalog_rows.extend(extract_madrid_rdf_rows(path))
            continue

        if path.suffix.lower() == ".json" and not path.name.endswith(".metadata.json"):
            payload = read_json(path)
            if payload is None:
                continue
            catalog_rows.extend(extract_catalog_rows(path, scope, source, payload))
            observation_rows.extend(extract_observation_rows(path, scope, source, payload))

    inventory_df = pd.DataFrame(inventory)
    catalog_df = pd.DataFrame(catalog_rows)
    observations_df = pd.DataFrame(observation_rows)
    sql_ready_df = build_sql_ready_indicators(observations_df)
    resource_profile_df = build_resource_profile(catalog_df)
    column_profile_df = build_column_profile(
        {
            "inventario_bronze": inventory_df,
            "catalogo_recursos_bronze": catalog_df,
            "observaciones_bronze_unificadas": observations_df,
            "indicadores_bronze_limpios": sql_ready_df,
        }
    )

    write_csv(inventory_df, OUTPUT_DIR / "inventario_bronze.csv")
    write_csv(catalog_df, OUTPUT_DIR / "catalogo_recursos_bronze.csv")
    write_csv(observations_df, OUTPUT_DIR / "observaciones_bronze_unificadas.csv")
    write_csv(sql_ready_df, OUTPUT_DIR / "indicadores_bronze_limpios.csv")
    write_csv(resource_profile_df, OUTPUT_DIR / "perfil_recursos_iseu.csv")
    write_csv(column_profile_df, OUTPUT_DIR / "perfil_columnas_eda.csv")

    summary = build_summary(inventory_df, catalog_df, observations_df, sql_ready_df, resource_profile_df)
    (OUTPUT_DIR / "resumen_bronze.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_DIR / "reporte_eda_bronze.md").write_text(build_markdown(summary), encoding="utf-8")

    print(f"EDA Bronze generado en: {OUTPUT_DIR}")
    print(f"Archivos inventariados: {summary['archivos_bronze']}")
    print(f"Recursos catalogados: {summary['recursos_catalogados']}")
    print(f"Observaciones unificadas: {summary['observaciones_unificadas']}")
    print(f"Indicadores SQL-ready: {summary['indicadores_sql_ready']}")


def build_inventory_row(path: Path, scope: str, source: str) -> dict[str, Any]:
    payload = read_json(path) if path.suffix.lower() == ".json" else None
    status = "OK"
    source_name = ""
    collected_at = ""
    source_url = ""
    records_detected = None
    observations_detected = None
    fields_detected = ""

    if isinstance(payload, dict):
        status = str(payload.get("status") or payload.get("estado") or "OK")
        source_name = str(payload.get("source_name") or "")
        collected_at = str(payload.get("collected_at") or payload.get("generado_en") or "")
        source_url = str(payload.get("source_url") or payload.get("endpoint") or "")
        records_detected, observations_detected, fields_detected = detect_json_shape(payload)
    elif path.suffix.lower() == ".csv":
        records_detected, fields_detected = detect_csv_shape(path)
        observations_detected = None
    elif path.suffix.lower() in {".html", ".rdf", ".txt"}:
        fields_detected = "texto/html/rdf"

    return {
        "scope": scope,
        "source": source,
        "source_name": source_name,
        "file": relative(path),
        "extension": path.suffix.lower(),
        "bytes": path.stat().st_size,
        "status": status,
        "records_detected": records_detected,
        "observations_detected": observations_detected,
        "fields_detected": fields_detected,
        "collected_at": collected_at,
        "source_url": source_url,
    }


def extract_catalog_rows(path: Path, scope: str, source: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if scope == "municipios" and path.name == "catalog_search_raw.json":
        return extract_ckan_search_rows(path, source, payload)
    if scope == "municipios" and source == "zaragoza" and path.name == "catalog_raw.json":
        return extract_zaragoza_rows(path, payload)
    if scope == "apis" and source == "catalogos":
        return extract_datos_gob_rows(path, payload)
    if scope == "apis" and source == "ine" and isinstance(payload.get("data"), list):
        return extract_ine_catalog_rows(path, payload)
    return []


def extract_observation_rows(path: Path, scope: str, source: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if scope == "apis" and source == "ine" and path.name == "ipc_tabla_50902_raw.json":
        return extract_ine_observations(path, payload)
    return []


def extract_ckan_search_rows(path: Path, city: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for search in payload.get("results", []):
        term = search.get("term", "")
        result = ((search.get("data") or {}).get("result") or {}) if isinstance(search, dict) else {}
        packages = result.get("results") or []
        for package in packages:
            resources = package.get("resources") or []
            if not resources:
                rows.append(catalog_row(path, "municipios", city, term, package))
            for resource in resources:
                rows.append(catalog_row(path, "municipios", city, term, package, resource))
    return rows


def extract_zaragoza_rows(path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    data = payload.get("data") or {}
    for item in data.get("result", []):
        formats = item.get("formato") or []
        if not formats:
            rows.append(catalog_row(path, "municipios", "zaragoza", "catalogo", item))
        for resource in formats:
            rows.append(catalog_row(path, "municipios", "zaragoza", "catalogo", item, resource))
    return rows


def extract_madrid_rdf_rows(path: Path) -> list[dict[str, Any]]:
    namespaces = {
        "dcat": "http://www.w3.org/ns/dcat#",
        "dct": "http://purl.org/dc/terms/",
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    }
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return []
    rows: list[dict[str, Any]] = []
    for dataset in root.findall(".//dcat:Dataset", namespaces):
        dataset_title = element_text(dataset.find("dct:title", namespaces))
        dataset_description = element_text(dataset.find("dct:description", namespaces))
        dataset_id = element_text(dataset.find("dct:identifier", namespaces)) or dataset.attrib.get(f"{{{namespaces['rdf']}}}about", "")
        dataset_url = dataset.attrib.get(f"{{{namespaces['rdf']}}}about", dataset_id)
        modified_at = element_text(dataset.find("dct:modified", namespaces))
        topics, relevance_score = detect_topics(" ".join([dataset_title, dataset_description]))
        distributions = dataset.findall("dcat:distribution/dcat:Distribution", namespaces)
        if not distributions:
            rows.append(
                madrid_catalog_row(path, dataset_id, dataset_title, dataset_description, dataset_url, "", "", "", "", modified_at, topics, relevance_score)
            )
        for distribution in distributions:
            resource_id = distribution.attrib.get(f"{{{namespaces['rdf']}}}about", "")
            resource_name = element_text(distribution.find("dct:title", namespaces)) or Path(resource_id).name
            resource_url = resource_attr(distribution.find("dcat:accessURL", namespaces), namespaces)
            resource_format = resource_attr(distribution.find("dct:format", namespaces), namespaces) or resource_attr(distribution.find("dcat:mediaType", namespaces), namespaces)
            resource_modified = element_text(distribution.find("dct:modified", namespaces)) or modified_at
            rows.append(
                madrid_catalog_row(
                    path,
                    dataset_id,
                    dataset_title,
                    dataset_description,
                    dataset_url,
                    resource_id,
                    resource_name,
                    resource_format,
                    resource_url,
                    resource_modified,
                    topics,
                    relevance_score,
                )
            )
    return rows


def madrid_catalog_row(
    path: Path,
    dataset_id: str,
    dataset_title: str,
    dataset_description: str,
    dataset_url: str,
    resource_id: str,
    resource_name: str,
    resource_format: str,
    resource_url: str,
    modified_at: str,
    topics: str,
    relevance_score: int,
) -> dict[str, Any]:
    return {
        "scope": "municipios",
        "source": "madrid",
        "search_term": "catalogo_rdf",
        "dataset_id": dataset_id,
        "dataset_title": dataset_title,
        "dataset_description": dataset_description,
        "dataset_url": dataset_url,
        "resource_id": resource_id,
        "resource_name": resource_name,
        "resource_format": resource_format,
        "resource_url": resource_url,
        "modified_at": modified_at,
        "iseu_topics": topics,
        "relevance_score": relevance_score,
        "raw_file": relative(path),
    }


def element_text(element: ET.Element | None) -> str:
    return "" if element is None or element.text is None else element.text.strip()


def resource_attr(element: ET.Element | None, namespaces: dict[str, str]) -> str:
    if element is None:
        return ""
    return element.attrib.get(f"{{{namespaces['rdf']}}}resource", element_text(element))


def extract_datos_gob_rows(path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    data = payload.get("data") or {}
    items = ((data.get("result") or {}).get("items") or []) if isinstance(data, dict) else []
    for item in items:
        distributions = as_list(item.get("distribution"))
        if not distributions:
            rows.append(catalog_row(path, "apis", "catalogos", "datos.gob.es", item))
        for resource in distributions:
            rows.append(catalog_row(path, "apis", "catalogos", "datos.gob.es", item, resource))
    return rows


def extract_ine_catalog_rows(path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    data = payload.get("data") or []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = text_value(item.get("Nombre"))
        topics, relevance_score = detect_topics(" ".join([title, item.get("COD", ""), item.get("Codigo", "")]))
        rows.append(
            {
                "scope": "apis",
                "source": "ine",
                "search_term": "catalogo_ine",
                "dataset_id": item.get("Id") or item.get("COD") or item.get("Codigo"),
                "dataset_title": title,
                "dataset_description": "",
                "dataset_url": item.get("Url", ""),
                "resource_id": item.get("COD") or item.get("Codigo") or "",
                "resource_name": item.get("COD") or item.get("Codigo") or "",
                "resource_format": "JSON",
                "resource_url": item.get("Url", ""),
                "modified_at": "",
                "iseu_topics": topics,
                "relevance_score": relevance_score,
                "raw_file": relative(path),
            }
        )
    return rows


def extract_ine_observations(path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    collected_at = payload.get("collected_at", "")
    for series in payload.get("data", []):
        if not isinstance(series, dict):
            continue
        metadata = series.get("MetaData") or []
        geo = metadata_name(metadata, "Totales Territoriales") or "España"
        metric = text_value(series.get("Nombre"))
        unit = text_value(series.get("T3_Unidad"))
        for observation in series.get("Data", []):
            value = observation.get("Valor")
            rows.append(
                {
                    "source": "INE",
                    "dataset": "ipc_tabla_50902",
                    "variable": "IPC",
                    "metric": metric,
                    "geo": geo,
                    "period": observation.get("Fecha") or f"{observation.get('Anyo', '')}-{observation.get('T3_Periodo', '')}",
                    "value": value,
                    "unit": unit,
                    "quality": "alta",
                    "notes": "Observacion normalizada desde INE Tempus en Bronze intento 3.",
                    "raw_file": relative(path),
                    "extracted_at": collected_at,
                    "series_code": series.get("COD", ""),
                    "year": observation.get("Anyo", ""),
                    "period_code": observation.get("T3_Periodo", ""),
                }
            )
    return rows


def catalog_row(
    path: Path,
    scope: str,
    source: str,
    search_term: str,
    package: dict[str, Any],
    resource: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resource = resource or {}
    title = text_value(package.get("title_translated")) or text_value(package.get("title")) or text_value(package.get("name"))
    description = clean_text(
        text_value(package.get("notes_translated"))
        or text_value(package.get("description_basic"))
        or text_value(package.get("description"))
    )
    resource_name = text_value(resource.get("name")) or text_value(resource.get("title"))
    topics, relevance_score = detect_topics(" ".join([search_term, title, description, resource_name]))
    return {
        "scope": scope,
        "source": source,
        "search_term": search_term,
        "dataset_id": package.get("id") or package.get("identifier") or package.get("_about") or "",
        "dataset_title": title,
        "dataset_description": description,
        "dataset_url": package.get("url") or package.get("landingPage") or package.get("_about") or "",
        "resource_id": resource.get("id") or resource.get("identifier") or resource.get("_about") or "",
        "resource_name": resource_name,
        "resource_format": text_value(resource.get("format")) or resource.get("mediaType") or "",
        "resource_url": resource.get("url") or resource.get("downloadURL") or resource.get("accessURL") or "",
        "modified_at": package.get("metadata_modified") or package.get("modified") or package.get("lastModified") or "",
        "iseu_topics": topics,
        "relevance_score": relevance_score,
        "raw_file": relative(path),
    }


def detect_json_shape(payload: dict[str, Any]) -> tuple[int | None, int | None, str]:
    data = payload.get("data", payload)
    records = None
    observations = None
    fields: list[str] = []

    if isinstance(data, list):
        records = len(data)
        if data and isinstance(data[0], dict):
            fields = sorted(data[0].keys())
        observations = sum(len(item.get("Data", [])) for item in data if isinstance(item, dict) and isinstance(item.get("Data"), list))
    elif isinstance(data, dict):
        if isinstance(data.get("result"), list):
            records = len(data["result"])
            fields = sorted(data["result"][0].keys()) if data["result"] and isinstance(data["result"][0], dict) else []
        elif isinstance(data.get("result"), dict):
            result = data["result"]
            result_rows = result.get("results") or result.get("items") or []
            records = len(result_rows) if isinstance(result_rows, list) else None
            fields = sorted(result_rows[0].keys()) if result_rows and isinstance(result_rows[0], dict) else sorted(result.keys())
        else:
            fields = sorted(data.keys())

    return records, observations, ", ".join(fields[:20])


def detect_csv_shape(path: Path) -> tuple[int | None, str]:
    for encoding in ("utf-8", "utf-8-sig", "latin1"):
        try:
            rows = 0
            columns: list[str] = []
            for chunk in pd.read_csv(path, sep=None, engine="python", chunksize=50_000, encoding=encoding, on_bad_lines="skip"):
                rows += len(chunk)
                if not columns:
                    columns = [str(column) for column in chunk.columns]
            return rows, ", ".join(columns[:20])
        except Exception:
            continue
    try:
        with path.open("r", encoding="utf-8", errors="replace") as file:
            header = file.readline().strip()
            rows = max(sum(1 for _ in file), 0)
        return rows, header[:500]
    except OSError:
        return None, ""


def build_sql_ready_indicators(observations_df: pd.DataFrame) -> pd.DataFrame:
    if observations_df.empty:
        return pd.DataFrame(columns=SQL_INDICATOR_COLUMNS)
    df = observations_df.copy()
    for column in SQL_INDICATOR_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df = df[SQL_INDICATOR_COLUMNS]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])
    df = df.drop_duplicates()
    return df


def build_resource_profile(catalog_df: pd.DataFrame) -> pd.DataFrame:
    if catalog_df.empty:
        return pd.DataFrame(
            columns=["scope", "source", "iseu_topics", "resource_format", "resources", "datasets", "with_url"]
        )
    df = catalog_df.copy()
    df["with_url"] = df["resource_url"].fillna("").astype(str).str.len() > 0
    return (
        df.groupby(["scope", "source", "iseu_topics", "resource_format"], dropna=False)
        .agg(resources=("resource_url", "count"), datasets=("dataset_id", "nunique"), with_url=("with_url", "sum"))
        .reset_index()
        .sort_values(["resources", "datasets"], ascending=False)
    )


def build_column_profile(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for dataset, df in frames.items():
        for column in df.columns:
            if not len(df):
                nulls = 0
                empty = 0
                missing = 0
            else:
                null_mask = df[column].isna()
                empty_mask = (~null_mask) & (df[column].astype(str).str.strip() == "")
                missing_mask = null_mask | empty_mask
                nulls = int(null_mask.sum())
                empty = int(empty_mask.sum())
                missing = int(missing_mask.sum())
            rows.append(
                {
                    "dataset": dataset,
                    "column": column,
                    "rows": int(len(df)),
                    "nulls": nulls,
                    "empty_strings": empty,
                    "missing_pct": round(missing / len(df) * 100, 2) if len(df) else 0,
                    "unique_values": int(df[column].nunique(dropna=True)) if len(df) else 0,
                    "dtype": str(df[column].dtype) if len(df) else "",
                }
            )
    return pd.DataFrame(rows)


def build_summary(
    inventory_df: pd.DataFrame,
    catalog_df: pd.DataFrame,
    observations_df: pd.DataFrame,
    sql_ready_df: pd.DataFrame,
    resource_profile_df: pd.DataFrame,
) -> dict[str, Any]:
    silver_summary = load_silver_summary()
    by_source = []
    if not inventory_df.empty:
        by_source = (
            inventory_df.groupby(["scope", "source"], dropna=False)
            .agg(files=("file", "count"), bytes=("bytes", "sum"))
            .reset_index()
            .to_dict(orient="records")
        )

    catalog_by_source = []
    if not catalog_df.empty:
        catalog_by_source = (
            catalog_df.groupby(["scope", "source"], dropna=False)
            .agg(resources=("resource_url", "count"), datasets=("dataset_id", "nunique"))
            .reset_index()
            .to_dict(orient="records")
        )

    observations_by_source = []
    if not observations_df.empty:
        observations_by_source = (
            observations_df.groupby("source", dropna=False)
            .agg(rows=("value", "count"), datasets=("dataset", "nunique"), geos=("geo", "nunique"))
            .reset_index()
            .to_dict(orient="records")
        )

    topics = []
    if not catalog_df.empty and "iseu_topics" in catalog_df.columns:
        topic_rows = []
        for value in catalog_df["iseu_topics"].fillna(""):
            for topic in str(value).split("|"):
                topic = topic.strip()
                if topic:
                    topic_rows.append(topic)
        topics = pd.Series(topic_rows).value_counts().rename_axis("topic").reset_index(name="resources").to_dict(orient="records") if topic_rows else []

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "bronze_dir": relative(BRONZE_DIR),
        "output_dir": relative(OUTPUT_DIR),
        "archivos_bronze": int(len(inventory_df)),
        "bytes_bronze": int(inventory_df["bytes"].sum()) if not inventory_df.empty else 0,
        "recursos_catalogados": int(len(catalog_df)),
        "datasets_catalogados": int(catalog_df["dataset_id"].nunique()) if not catalog_df.empty else 0,
        "observaciones_unificadas": int(len(observations_df)),
        "indicadores_sql_ready": int(len(sql_ready_df)),
        "filas_csv_descargadas": int(
            inventory_df.loc[
                (inventory_df["scope"] == "downloaded_resources") & (inventory_df["extension"] == ".csv"),
                "records_detected",
            ].fillna(0).sum()
        ) if not inventory_df.empty else 0,
        "recursos_relevantes_iseu": int((catalog_df.get("relevance_score", pd.Series(dtype=int)) > 0).sum()) if not catalog_df.empty else 0,
        "by_source": by_source,
        "catalog_by_source": catalog_by_source,
        "observations_by_source": observations_by_source,
        "topics": topics,
        "silver": silver_summary,
        "outputs": {
            "inventory": relative(OUTPUT_DIR / "inventario_bronze.csv"),
            "catalog": relative(OUTPUT_DIR / "catalogo_recursos_bronze.csv"),
            "observations": relative(OUTPUT_DIR / "observaciones_bronze_unificadas.csv"),
            "sql_ready": relative(OUTPUT_DIR / "indicadores_bronze_limpios.csv"),
            "resource_profile": relative(OUTPUT_DIR / "perfil_recursos_iseu.csv"),
            "column_profile": relative(OUTPUT_DIR / "perfil_columnas_eda.csv"),
            "silver_report": relative(SILVER_REPORT) if SILVER_REPORT.exists() else "",
        },
    }


def load_silver_summary() -> dict[str, Any]:
    if not SILVER_REPORT.exists():
        return {}
    try:
        payload = json.loads(SILVER_REPORT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    rows_by_table = payload.get("rows_by_table", {})
    detail_rows = sum(
        int(rows)
        for table, rows in rows_by_table.items()
        if table != "indicadores_silver_barcelona.csv"
    )
    return {
        "generated_at": payload.get("generated_at", ""),
        "silver_dir": payload.get("silver_dir", ""),
        "sqlite_staging": payload.get("sqlite_staging", ""),
        "resources_processed": int(payload.get("resources_processed", 0)),
        "detail_rows": int(detail_rows),
        "indicator_rows": int(rows_by_table.get("indicadores_silver_barcelona.csv", 0)),
        "rows_by_table": rows_by_table,
    }


def build_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# EDA Bronze APIs intento 3",
        "",
        f"Generado en: {summary['generated_at']}",
        "",
        "## Resumen",
        "",
        f"- Archivos Bronze inventariados: {summary['archivos_bronze']}",
        f"- Tamano total Bronze: {summary['bytes_bronze']:,} bytes",
        f"- Recursos catalogados: {summary['recursos_catalogados']}",
        f"- Datasets catalogados: {summary['datasets_catalogados']}",
        f"- Observaciones numericas unificadas: {summary['observaciones_unificadas']}",
        f"- Indicadores listos para SQL: {summary['indicadores_sql_ready']}",
        f"- Filas CSV descargadas para staging raw: {summary['filas_csv_descargadas']}",
        f"- Recursos con tema ISEU detectado: {summary['recursos_relevantes_iseu']}",
        "",
        "## Limpieza Silver",
        "",
    ]
    silver = summary.get("silver") or {}
    if silver:
        lines.extend(
            [
                f"- Recursos procesados en Silver: {silver['resources_processed']}",
                f"- Filas limpias de detalle: {silver['detail_rows']}",
                f"- Indicadores derivados Silver: {silver['indicator_rows']}",
                f"- Directorio Silver: `{silver['silver_dir']}`",
                f"- SQLite staging: `{silver['sqlite_staging']}`",
                "",
            ]
        )
        for table, rows in silver.get("rows_by_table", {}).items():
            lines.append(f"- {table}: {rows} filas")
        lines.append("")
    else:
        lines.extend(["- Limpieza Silver no ejecutada todavia.", ""])
    lines.extend([
        "## Archivos por fuente",
        "",
    ])
    for item in summary["by_source"]:
        lines.append(f"- {item['scope']}/{item['source']}: {item['files']} archivos, {item['bytes']:,} bytes")
    lines.extend(["", "## Recursos catalogados por fuente", ""])
    for item in summary["catalog_by_source"]:
        lines.append(f"- {item['scope']}/{item['source']}: {item['resources']} recursos, {item['datasets']} datasets")
    lines.extend(["", "## Observaciones unificadas", ""])
    if summary["observations_by_source"]:
        for item in summary["observations_by_source"]:
            lines.append(f"- {item['source']}: {item['rows']} filas, {item['datasets']} datasets, {item['geos']} territorios")
    else:
        lines.append("- No se detectaron observaciones numericas estructuradas.")
    lines.extend(["", "## Temas ISEU detectados", ""])
    if summary["topics"]:
        for item in summary["topics"]:
            lines.append(f"- {item['topic']}: {item['resources']} recursos")
    else:
        lines.append("- No se detectaron temas ISEU en catalogos.")
    lines.extend(
        [
            "",
            "## Salidas",
            "",
            f"- Inventario: `{summary['outputs']['inventory']}`",
            f"- Catalogo de recursos: `{summary['outputs']['catalog']}`",
            f"- Observaciones unificadas: `{summary['outputs']['observations']}`",
            f"- Indicadores SQL-ready: `{summary['outputs']['sql_ready']}`",
            f"- Perfil de recursos ISEU: `{summary['outputs']['resource_profile']}`",
            f"- Perfil de columnas: `{summary['outputs']['column_profile']}`",
            f"- Reporte Silver: `{summary['outputs']['silver_report']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def detect_topics(text: str) -> tuple[str, int]:
    normalized = normalize_text(text)
    matches: list[str] = []
    score = 0
    for topic, keywords in ISEU_TOPICS.items():
        topic_hits = sum(1 for keyword in keywords if normalize_text(keyword) in normalized)
        if topic_hits:
            matches.append(topic)
            score += topic_hits
    return "|".join(matches), score


def infer_scope_source(path: Path) -> tuple[str, str]:
    parts = path.relative_to(BRONZE_DIR).parts
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "unknown", "unknown"


def metadata_name(metadata: list[dict[str, Any]], variable: str) -> str:
    for item in metadata:
        if item.get("T3_Variable") == variable:
            return str(item.get("Nombre") or "")
    return ""


def text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        if "es" in value:
            return text_value(value["es"])
        if "_value" in value:
            return text_value(value["_value"])
        if "value" in value:
            return text_value(value["value"])
        if "title" in value:
            return text_value(value["title"])
        return " | ".join(text_value(item) for item in value.values() if text_value(item))
    if isinstance(value, list):
        return " | ".join(text_value(item) for item in value if text_value(item))
    return str(value)


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value[:1000]


def normalize_text(value: str) -> str:
    value = value.lower()
    replacements = str.maketrans("áéíóúüñ", "aeiouun")
    return value.translate(replacements)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as file:
            payload = json.load(file)
        return payload if isinstance(payload, dict) else {"data": payload}
    except (OSError, json.JSONDecodeError):
        return None


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8")


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()