from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import boto3


AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")
DATABASE = os.getenv("ATHENA_DATABASE", "iseu")
WORKGROUP = os.getenv("ATHENA_WORKGROUP", "iseu")
DATA_BUCKET = os.getenv("DATA_BUCKET", "")
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "*")
MAX_QUERY_SECONDS = int(os.getenv("MAX_QUERY_SECONDS", "22"))

athena = boto3.client("athena", region_name=AWS_REGION)
glue = boto3.client("glue", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)

# Logical alias → S3 path fragment used to detect the Glue table
_TABLE_LOCATIONS = {
    "indicators":  "gold/athena/indicators",
    "indicadores": "gold/athena/indicadores",
    "observations": "gold/athena/semantic_obs",
}


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    method = event.get("httpMethod", "GET").upper()
    path = (event.get("resource") or event.get("path") or "/").rstrip("/") or "/"

    if method == "OPTIONS":
        return response(204, None)

    try:
        if path.endswith("/health") and method == "GET":
            return response(200, {
                "ok": True,
                "service": "iseu-athena-api",
                "database": DATABASE,
                "workgroup": WORKGROUP,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
        if path.endswith("/dashboard") and method == "GET":
            return response(200, build_dashboard())
        if path.endswith("/catalog") and method == "GET":
            return response(200, build_catalog())
        if path.endswith("/indicators") and method == "POST":
            return response(200, find_indicators(parse_body(event)))
        if path.endswith("/sql") and method == "POST":
            return response(200, execute_model_sql(parse_body(event)))
        return response(404, {"error": "Ruta no encontrada."})
    except ValueError as error:
        return response(400, {"error": str(error)})
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"level": "ERROR", "path": path, "error": str(error)}, ensure_ascii=False))
        return response(500, {"error": "No se pudo consultar Athena.", "detail": str(error)[:500]})


def response(status: int, payload: Any) -> dict[str, Any]:
    headers = {
        "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
        "Access-Control-Allow-Headers": "Content-Type,X-Api-Key",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Cache-Control": "no-store",
        "Content-Type": "application/json; charset=utf-8",
    }
    return {
        "statusCode": status,
        "headers": headers,
        "body": "" if payload is None else json.dumps(payload, ensure_ascii=False, default=json_default),
    }


def parse_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64
        body = base64.b64decode(body).decode("utf-8")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as error:
        raise ValueError("El cuerpo debe ser JSON válido.") from error
    if not isinstance(parsed, dict):
        raise ValueError("El cuerpo debe ser un objeto JSON.")
    return parsed


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


@lru_cache(maxsize=1)
def table_names() -> dict[str, str | None]:
    """Detect Glue table names by their S3 location.
    Fixed aliases: indicators, indicadores, observations.
    Dynamic aliases: silver_* for any table at silver/athena/ prefix."""
    paginator = glue.get_paginator("get_tables")
    found: dict[str, str | None] = {alias: None for alias in _TABLE_LOCATIONS}
    available = []
    for page in paginator.paginate(DatabaseName=DATABASE):
        for table in page.get("TableList", []):
            name = table["Name"]
            available.append(name)
            location = table.get("StorageDescriptor", {}).get("Location", "").lower()
            for alias, fragment in _TABLE_LOCATIONS.items():
                if fragment in location and found[alias] is None:
                    found[alias] = name
            # Detect Silver raw tables exported by the pipeline
            if "silver/athena/" in location and found.get(f"silver_{name}") is None:
                found[f"silver_{name}"] = name

    if not found["indicators"]:
        raise RuntimeError(f"No se encontró la tabla Gold de indicadores. Tablas disponibles: {available}")
    return found


def quoted_table(name: str) -> str:
    return f'"{DATABASE}"."{name.replace(chr(34), chr(34) * 2)}"'


def run_query(sql: str) -> list[dict[str, Any]]:
    execution = athena.start_query_execution(QueryString=sql, WorkGroup=WORKGROUP)
    query_id = execution["QueryExecutionId"]
    deadline = time.monotonic() + MAX_QUERY_SECONDS
    while time.monotonic() < deadline:
        detail = athena.get_query_execution(QueryExecutionId=query_id)["QueryExecution"]
        state = detail["Status"]["State"]
        if state == "SUCCEEDED":
            return read_results(query_id)
        if state in {"FAILED", "CANCELLED"}:
            reason = detail["Status"].get("StateChangeReason", state)
            raise RuntimeError(f"Athena {state.lower()}: {reason}")
        time.sleep(0.25)
    athena.stop_query_execution(QueryExecutionId=query_id)
    raise TimeoutError(f"Athena superó {MAX_QUERY_SECONDS} segundos.")


def read_results(query_id: str) -> list[dict[str, Any]]:
    paginator = athena.get_paginator("get_query_results")
    columns: list[str] = []
    records: list[dict[str, Any]] = []
    first_row = True
    for page in paginator.paginate(QueryExecutionId=query_id, PaginationConfig={"PageSize": 1000}):
        if not columns:
            columns = [item["Name"] for item in page["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]]
        for row in page["ResultSet"].get("Rows", []):
            values = [item.get("VarCharValue") for item in row.get("Data", [])]
            values.extend([None] * (len(columns) - len(values)))
            if first_row and values == columns:
                first_row = False
                continue
            first_row = False
            records.append({column: coerce_value(column, value) for column, value in zip(columns, values)})
    return records


def coerce_value(column: str, value: str | None) -> Any:
    if value is None:
        return None
    integer_columns = {
        "rows", "variables", "sources", "source_count", "city_count",
        "indicator_rows", "source_count_total", "variable_count",
        "detail_rows", "obs_rows", "gold_rows", "silver_rows",
    }
    float_columns = {"value", "quality_score"}
    if column in integer_columns:
        try:
            return int(value)
        except ValueError:
            return 0
    if column in float_columns:
        try:
            return float(value)
        except ValueError:
            return value
    return value


def run_named_queries(queries: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    results: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(queries))) as executor:
        futures = {executor.submit(run_query, sql): name for name, sql in queries.items()}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


def build_dashboard() -> dict[str, Any]:
    tables = table_names()
    indicators = quoted_table(str(tables["indicators"]))
    # Use Silver indicadores as main source (matches local server behaviour)
    indicadores = quoted_table(str(tables["indicadores"])) if tables.get("indicadores") else indicators
    geo_case = """
        CASE
          WHEN lower(city) = 'barcelona' THEN 'Barcelona'
          WHEN lower(city) = 'madrid' THEN 'Madrid'
          WHEN lower(city) = 'valencia' THEN 'Valencia'
          WHEN lower(city) = 'sevilla' THEN 'Sevilla'
          WHEN lower(city) = 'bilbao' THEN 'Bilbao'
          WHEN lower(city) IN ('malaga', 'málaga') THEN 'Malaga'
          WHEN lower(city) = 'zaragoza' THEN 'Zaragoza'
          ELSE city
        END
    """
    silver_city_case = """
        CASE
          WHEN lower(geo) LIKE '%barcelona%' THEN 'Barcelona'
          WHEN lower(geo) LIKE '%madrid%' THEN 'Madrid'
          WHEN lower(geo) LIKE '%valencia%' THEN 'Valencia'
          WHEN lower(geo) LIKE '%sevilla%' THEN 'Sevilla'
          WHEN lower(geo) LIKE '%bilbao%' THEN 'Bilbao'
          WHEN lower(geo) LIKE '%malaga%' OR lower(geo) LIKE '%málaga%' THEN 'Malaga'
          WHEN lower(geo) LIKE '%zaragoza%' THEN 'Zaragoza'
          ELSE NULL
        END
    """
    queries = {
        "metrics": f"""
            SELECT count(*) indicator_rows,
                   count(DISTINCT source) source_count_total,
                   count(DISTINCT variable) variable_count
            FROM {indicadores}
        """,
        "sources": f"""
            SELECT source, count(*) rows, count(DISTINCT variable) variables
            FROM {indicadores} GROUP BY source ORDER BY rows DESC
        """,
        "variables": f"""
            SELECT variable, source, count(*) rows, max(period) latest_period
            FROM {indicadores} GROUP BY variable, source ORDER BY variable, source LIMIT 80
        """,
        "latest": f"""
            SELECT source, variable, metric, geo, period, value, unit,
                   CASE lower(coalesce(quality,'')) WHEN 'alta' THEN 'Alta' WHEN 'media' THEN 'Media' ELSE 'Baja' END quality
            FROM {indicadores} ORDER BY period DESC LIMIT 12
        """,
        "quality": f"""
            SELECT CASE lower(coalesce(quality,'')) WHEN 'alta' THEN 'Alta' WHEN 'media' THEN 'Media' ELSE 'Baja' END quality,
                   count(*) rows
            FROM {indicadores} GROUP BY 1 ORDER BY rows DESC
        """,
        "top_variables": f"""
            SELECT variable, count(*) rows FROM {indicadores}
            GROUP BY variable ORDER BY rows DESC LIMIT 10
        """,
        "periods": f"""
            SELECT substr(period, 1, 4) period_group, count(*) rows
            FROM {indicadores} WHERE period IS NOT NULL AND trim(period) <> ''
            GROUP BY 1 ORDER BY period_group DESC LIMIT 8
        """,
        "source_variables": f"""
            SELECT source, count(DISTINCT variable) variables
            FROM {indicadores} GROUP BY source ORDER BY variables DESC, source
        """,
        "cities": f"""
            SELECT {geo_case} city, count(*) rows,
                   count(DISTINCT variable) variables, count(DISTINCT source) source_count,
                   max(CAST(date AS varchar)) latest_period,
                   array_join(array_agg(DISTINCT source), ', ') source_list
            FROM {indicators} WHERE city IS NOT NULL AND trim(city) <> ''
            GROUP BY 1 ORDER BY rows DESC, city
        """,
        "catalog": f"""
            SELECT variable, min(coalesce(dataset, 'Sin categoría')) description,
                   array_join(array_agg(DISTINCT source), ', ') source_names,
                   min(period) first_period, max(period) latest_period,
                   min(unit) unit, count(*) rows,
                   count(DISTINCT {silver_city_case}) city_count
            FROM {indicadores} GROUP BY variable ORDER BY variable
        """,
        "analytics_series": f"""
            SELECT {geo_case} city, variable, CAST(date AS varchar) period,
                   value, unit, source
            FROM {indicators}
            WHERE (district IS NULL OR trim(CAST(district AS varchar)) = '')
              AND variable IN (
                'unemployed_registered', 'contracts_registered', 'job_seekers',
                'income', 'income_median', 'income_per_person',
                'gini_inequality', 'inequality_p80p20',
                'traffic_accidents', 'mobility_resources_records'
              )
            ORDER BY period, city, variable
        """,
        "accident_heatmap": f"""
            SELECT {silver_city_case} city, substr(period, 1, 7) period,
                   sum(value) value
            FROM {indicadores}
            WHERE variable = 'Accidentes de trafico'
              AND unit = 'accidents'
              AND period IS NOT NULL AND length(period) >= 7
            GROUP BY 1, 2
            HAVING {silver_city_case} IS NOT NULL
            ORDER BY period, city
        """,
        "cpi_series": f"""
            SELECT {silver_city_case} city, substr(period, 1, 4) year,
                   avg(value) value
            FROM {indicadores}
            WHERE variable = 'Cpi general index'
              AND period IS NOT NULL AND length(period) >= 4
            GROUP BY 1, 2
            HAVING {silver_city_case} IS NOT NULL
            ORDER BY year, city
        """,
        "rent_series": f"""
            SELECT {silver_city_case} city, substr(period, 1, 4) year,
                   avg(value) value
            FROM {indicadores}
            WHERE variable = 'Alquiler medio mensual'
              AND period IS NOT NULL AND length(period) >= 4
            GROUP BY 1, 2
            HAVING {silver_city_case} IS NOT NULL
            ORDER BY year, city
        """,
        "tourism_series": f"""
            SELECT {silver_city_case} city, substr(period, 1, 4) year,
                   avg(value) value
            FROM {indicadores}
            WHERE variable = 'Pernoctaciones turisticas'
              AND period IS NOT NULL AND length(period) >= 4
            GROUP BY 1, 2
            HAVING {silver_city_case} IS NOT NULL
            ORDER BY year, city
        """,
    }

    # detailRows = Gold indicators + semantic_obs + any silver_* tables in Athena
    # (mirrors local server which counts everything except the main indicadores table)
    queries["gold_count"] = f"SELECT count(*) gold_rows FROM {indicators}"
    if tables.get("observations"):
        queries["obs_count"] = f"SELECT count(*) obs_rows FROM {quoted_table(str(tables['observations']))}"
    for alias, tname in tables.items():
        if alias.startswith("silver_"):
            safe = re.sub(r"[^a-z0-9_]", "_", alias)
            queries[f"cnt_{safe}"] = f"SELECT count(*) silver_rows FROM {quoted_table(str(tname))}"

    result = run_named_queries(queries)
    metrics = (result.get("metrics") or [{}])[0]
    detail_count = (
        ((result.get("gold_count") or [{}])[0].get("gold_rows") or 0)
        + ((result.get("obs_count") or [{}])[0].get("obs_rows") or 0)
        + sum(
            (result.get(f"cnt_{re.sub(r'[^a-z0-9_]', '_', alias)}") or [{}])[0].get("silver_rows") or 0
            for alias in tables if alias.startswith("silver_")
        )
    )
    cities = result.get("cities", [])
    catalog = [
        {
            **{key: value for key, value in row.items() if key != "source_names"},
            "sources": row.get("source_names"),
        }
        for row in result.get("catalog", [])
    ]
    updated_at = gold_last_modified()
    city_updates = [
        {
            "city": row.get("city"),
            "received_at": updated_at,
            "latest_period": row.get("latest_period"),
            "rows": row.get("rows"),
            "source_count": row.get("source_count"),
            "sources": row.get("source_list"),
        }
        for row in cities
    ]
    return {
        "ready": True,
        "storageLabel": "Athena sobre S3 Gold",
        "updatedAt": updated_at,
        "kpis": {
            "indicatorRows": metrics.get("indicator_rows", 0),
            "sourceCount": metrics.get("source_count_total", 0),
            "variableCount": metrics.get("variable_count", 0),
            "detailRows": detail_count or metrics.get("indicator_rows", 0),
        },
        "sources": result.get("sources", []),
        "cities": [
            {
                **{key: value for key, value in row.items() if key not in {"latest_period", "source_list", "source_count"}},
                "sources": row.get("source_count"),
            }
            for row in cities
        ],
        "cityUpdates": city_updates,
        "indicatorCatalog": catalog,
        "variables": result.get("variables", []),
        "latestRows": result.get("latest", []),
        "charts": {
            "quality": result.get("quality", []),
            "topVariables": result.get("top_variables", []),
            "periods": result.get("periods", []),
            "sourceVariables": result.get("source_variables", []),
        },
        "analytics": {
            "series": result.get("analytics_series", []),
            "accidentHeatmap": result.get("accident_heatmap", []),
            "cpiSeries": result.get("cpi_series", []),
            "rentSeries": result.get("rent_series", []),
            "tourismSeries": result.get("tourism_series", []),
        },
        "pipeline": {"apis": {}, "dataLoad": {"backend": "athena"}},
    }


def build_catalog() -> dict[str, Any]:
    tables = table_names()
    indicadores = quoted_table(str(tables.get("indicadores") or tables["indicators"]))
    queries = {
        "sources": f"SELECT source, count(*) rows, count(DISTINCT variable) variables FROM {indicadores} GROUP BY source ORDER BY rows DESC",
        "variables": f"SELECT variable, source, count(*) rows, max(period) latest_period FROM {indicadores} GROUP BY variable, source ORDER BY variable, source",
    }
    result = run_named_queries(queries)
    available_tables = {alias: name for alias, name in tables.items() if name}
    return {
        "database": DATABASE,
        "ready": True,
        "sources": result.get("sources", []),
        "variables": result.get("variables", []),
        "tables": available_tables,
    }


def find_indicators(payload: dict[str, Any]) -> dict[str, Any]:
    tables = table_names()
    # Use indicadores (Silver-level detail) when detail=True and available
    use_detail = bool(payload.get("detail")) and tables.get("indicadores")
    if use_detail:
        table = quoted_table(str(tables["indicadores"]))
        sql = _build_indicadores_query(table, payload)
    else:
        table = quoted_table(str(tables["indicators"]))
        sql = _build_indicators_query(table, payload)
    rows = run_query(sql)
    return {
        "database": DATABASE,
        "ready": True,
        "table": "indicadores" if use_detail else "indicators",
        "rows": rows,
        "summary": {"rowCount": len(rows), "backend": "athena"},
    }


def _build_indicators_query(table: str, payload: dict[str, Any]) -> str:
    terms = clean_list(payload.get("terms"), 12, 80)
    cities = clean_list(payload.get("cities"), 7, 40)
    variables = clean_list(payload.get("variables"), 12, 80)
    categories = clean_list(payload.get("categories"), 8, 60)
    sources = clean_list(payload.get("sources"), 8, 60)
    limit = min(max(int(payload.get("limit", 18)), 1), 200)
    clauses = []
    if cities:
        clauses.append("lower(city) IN (" + ",".join(sql_string(i.lower()) for i in cities) + ")")
    if variables:
        clauses.append("lower(variable) IN (" + ",".join(sql_string(i.lower()) for i in variables) + ")")
    if categories:
        clauses.append("lower(category) IN (" + ",".join(sql_string(i.lower()) for i in categories) + ")")
    if sources:
        clauses.append("lower(source) IN (" + ",".join(sql_string(i.lower()) for i in sources) + ")")
    if terms:
        searchable = "concat_ws(' ', lower(variable), lower(category), lower(source), lower(city), lower(coalesce(CAST(district AS varchar), '')))"
        clauses.append("(" + " OR ".join(f"{searchable} LIKE {sql_string('%' + i.lower() + '%')}" for i in terms) + ")")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return f"""
        SELECT source, category dataset, variable, variable metric,
               concat(city, CASE WHEN district IS NULL OR trim(CAST(district AS varchar)) = '' THEN '' ELSE concat(' - ', CAST(district AS varchar)) END) geo,
               CAST(date AS varchar) period, value, unit,
               CASE WHEN quality_score >= 8 THEN 'alta' WHEN quality_score >= 5 THEN 'media' ELSE 'baja' END quality,
               quality_score, category, city, district
        FROM {table}{where}
        ORDER BY date DESC LIMIT {limit}
    """


def _build_indicadores_query(table: str, payload: dict[str, Any]) -> str:
    terms = clean_list(payload.get("terms"), 12, 80)
    cities = clean_list(payload.get("cities"), 7, 40)
    variables = clean_list(payload.get("variables"), 12, 80)
    sources = clean_list(payload.get("sources"), 8, 60)
    limit = min(max(int(payload.get("limit", 50)), 1), 500)
    clauses = []
    if cities:
        # indicadores uses 'geo' not 'city'
        city_pattern = " OR ".join(
            f"lower(geo) LIKE {sql_string('%' + c.lower() + '%')}" for c in cities
        )
        clauses.append(f"({city_pattern})")
    if variables:
        clauses.append("lower(variable) IN (" + ",".join(sql_string(i.lower()) for i in variables) + ")")
    if sources:
        clauses.append("lower(source) IN (" + ",".join(sql_string(i.lower()) for i in sources) + ")")
    if terms:
        searchable = "concat_ws(' ', lower(coalesce(variable,'')), lower(coalesce(source,'')), lower(coalesce(geo,'')), lower(coalesce(metric,'')))"
        clauses.append("(" + " OR ".join(f"{searchable} LIKE {sql_string('%' + i.lower() + '%')}" for i in terms) + ")")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return f"""
        SELECT source, dataset, variable, metric, geo, period, value, unit, quality, notes
        FROM {table}{where}
        ORDER BY period DESC LIMIT {limit}
    """


def execute_model_sql(payload: dict[str, Any]) -> dict[str, Any]:
    sql = validate_model_sql(str(payload.get("sql") or ""))
    rows = run_query(sql)
    return {
        "database": DATABASE,
        "ready": True,
        "sql": sql,
        "rows": rows,
        "rowCount": len(rows),
    }


# Logical table names the model may reference → alias key in table_names()
_ALLOWED_SQL_ALIASES: dict[str, str] = {
    "indicators":   "indicators",
    "indicadores":  "indicadores",
    "observations": "observations",
}


def validate_model_sql(raw_sql: str) -> str:
    sql = raw_sql.strip()
    if sql.startswith("```"):
        sql = re.sub(r"^```(?:sql)?\s*|\s*```$", "", sql, flags=re.IGNORECASE).strip()
    if not sql or len(sql) > 5000:
        raise ValueError("La consulta SQL está vacía o supera el tamaño permitido.")
    if ";" in sql or "--" in sql or "/*" in sql or "*/" in sql:
        raise ValueError("La consulta contiene separadores o comentarios no permitidos.")
    if not re.match(r"^\s*select\b", sql, flags=re.IGNORECASE):
        raise ValueError("Solo se permiten consultas SELECT.")
    forbidden = (
        "insert", "update", "delete", "drop", "alter", "create", "replace",
        "truncate", "unload", "call", "merge", "grant", "revoke", "msck",
        "repair", "show", "describe", "explain",
    )
    lowered = sql.lower()
    if any(re.search(rf"\b{word}\b", lowered) for word in forbidden):
        raise ValueError("La consulta contiene una operación no permitida.")

    referenced = re.findall(r"\b(?:from|join)\s+([a-zA-Z0-9_.\"-]+)", sql, flags=re.IGNORECASE)
    if not referenced:
        raise ValueError("La consulta no referencia ninguna tabla.")
    unknown = [t.strip('"').lower() for t in referenced if t.strip('"').lower() not in _ALLOWED_SQL_ALIASES]
    if unknown:
        allowed = ", ".join(_ALLOWED_SQL_ALIASES)
        raise ValueError(f"Tablas no permitidas: {unknown}. Permitidas: {allowed}.")

    # Replace logical aliases with real Glue table names
    tables = table_names()
    for alias, key in _ALLOWED_SQL_ALIASES.items():
        real = tables.get(key)
        if real:
            actual = quoted_table(real)
            sql = re.sub(
                rf'\b(from|join)\s+"?{re.escape(alias)}"?\b',
                lambda m, t=actual: f"{m.group(1)} {t}",
                sql,
                flags=re.IGNORECASE,
            )

    limit_match = re.search(r"\blimit\s+(\d+)\s*$", sql, flags=re.IGNORECASE)
    if limit_match:
        if int(limit_match.group(1)) > 500:
            sql = sql[:limit_match.start(1)] + "500" + sql[limit_match.end(1):]
    else:
        sql = sql.rstrip() + " LIMIT 100"
    return sql


def clean_list(value: Any, max_items: int, max_length: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Los filtros deben enviarse como listas.")
    result = []
    for item in value[:max_items]:
        text = str(item).strip()[:max_length]
        if text:
            result.append(text)
    return list(dict.fromkeys(result))


def sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def gold_last_modified() -> str:
    if not DATA_BUCKET:
        return ""
    try:
        detail = s3.head_object(Bucket=DATA_BUCKET, Key="gold/athena/indicators/data.parquet")
        return detail["LastModified"].astimezone(timezone.utc).isoformat(timespec="seconds")
    except Exception:  # noqa: BLE001
        return ""
