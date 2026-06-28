from __future__ import annotations

import json
import os
import sqlite3
import unicodedata
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASETS_DIR = PROJECT_ROOT / "pag_web" / "Procesos" / "Datasets"
DB_PATH = DATASETS_DIR / "iseu_datos.sqlite"
SEMANTIC_DICTIONARY_PATH = PROJECT_ROOT / "pag_web" / "Procesos" / "semantic_dictionary.json"
DATA_API_URL = os.environ.get("ISEU_DATA_API_URL", "").rstrip("/")
DATA_API_KEY = os.environ.get("ISEU_DATA_API_KEY", "")


_KNOWN_CITIES = ("barcelona", "madrid", "valencia", "sevilla", "bilbao", "malaga", "zaragoza")

TOPIC_TERMS = {
    "empleo": ["tasa de paro", "tasa de empleo", "salario", "laboral", "empresas", "paro registrado", "contratos registrados"],
    "trabajo": ["tasa de paro", "tasa de empleo", "salario", "laboral", "paro registrado", "contratos registrados"],
    "mudanza": ["paro registrado", "contratos registrados", "precio vivienda", "precio alquiler", "ipc"],
    "mudarme": ["paro registrado", "contratos registrados", "precio vivienda", "precio alquiler", "ipc"],
    "conviene": ["paro registrado", "contratos registrados", "precio vivienda", "precio alquiler", "ipc"],
    "madrid": ["madrid"],
    "barcelona": ["barcelona"],
    "valencia": ["valencia"],
    "sevilla": ["sevilla"],
    "bilbao": ["bilbao"],
    "malaga": ["malaga"],
    "zaragoza": ["zaragoza"],
    "paro": ["tasa de paro", "paro", "paro registrado"],
    "desempleo": ["tasa de paro", "paro", "paro registrado"],
    "ipc": ["ipc", "inflacion", "alimentos"],
    "inflacion": ["ipc", "inflacion", "alimentos"],
    "coste": ["ipc", "precio electricidad", "precio vivienda", "precio alquiler", "ibi"],
    "vida": ["ipc", "precio electricidad", "precio vivienda", "precio alquiler"],
    "energia": ["precio electricidad", "demanda electrica", "consumo electrico"],
    "electricidad": ["precio electricidad", "demanda electrica"],
    "luz": ["precio electricidad"],
    "vivienda": ["precio vivienda", "precio alquiler"],
    "alquiler": ["precio alquiler"],
    "poblacion": ["poblacion", "habitantes"],
    "habitantes": ["poblacion"],
    "turismo": ["turismo", "hotel"],
    "hoteles": ["turismo", "hotel", "ocupacion hotelera"],
    "salud": ["salud", "equipamientos", "bienestar"],
    "sanidad": ["salud", "equipamientos", "bienestar"],
    "aire": ["calidad del aire"],
    "movilidad": ["movilidad", "transporte"],
    "transporte": ["movilidad", "transporte"],
    "verde": ["zonas verdes"],
    "zonas": ["zonas verdes"],
    "empresa": ["empresas", "licencias", "densidad empresarial"],
    "negocio": ["empresas", "licencias"],
}


def database_ready() -> bool:
    return bool(DATA_API_URL) or DB_PATH.exists()


def remote_request(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not DATA_API_URL:
        raise RuntimeError("ISEU_DATA_API_URL no está configurada.")
    headers = {"Accept": "application/json"}
    if DATA_API_KEY:
        headers["x-api-key"] = DATA_API_KEY
    if payload is not None:
        data: bytes | None = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    else:
        data, method = None, "GET"
    request = urllib.request.Request(f"{DATA_API_URL}/{path.lstrip('/')}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=28) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:1600]
        raise RuntimeError(f"La API de datos respondió {error.code}: {detail}") from error


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def question_terms(question: str) -> list[str]:
    normalized = normalize(question)
    terms: list[str] = []
    for token, mapped_terms in TOPIC_TERMS.items():
        if token in normalized:
            terms.extend(mapped_terms)

    words = [
        word
        for word in normalized.replace("?", " ").replace(",", " ").replace(".", " ").split()
        if len(word) >= 4
    ]
    terms.extend(words)
    semantic = semantic_query(question)
    terms.extend(semantic["terms"])
    return sorted(set(normalize(term) for term in terms))


@lru_cache(maxsize=1)
def load_semantic_dictionary() -> dict[str, Any]:
    if not SEMANTIC_DICTIONARY_PATH.exists():
        return {"aliases": [], "cities": {}}
    with SEMANTIC_DICTIONARY_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def semantic_query(question: str) -> dict[str, Any]:
    dictionary = load_semantic_dictionary()
    normalized = normalize(question)
    matched_aliases = []
    terms: list[str] = []
    variables: list[str] = []
    categories: list[str] = []
    sources: list[str] = []
    tables: list[str] = []
    intents: list[str] = []

    for entry in dictionary.get("aliases", []):
        aliases = [normalize(str(alias)) for alias in entry.get("aliases", [])]
        if not any(alias and alias in normalized for alias in aliases):
            continue
        matched_aliases.append(entry)
        intents.append(str(entry.get("intent", "")))
        variables.extend(str(value) for value in entry.get("variables", []))
        categories.extend(str(value) for value in entry.get("categories", []))
        sources.extend(str(value) for value in entry.get("sources", []))
        tables.extend(str(value) for value in entry.get("tables", []))
        terms.extend(aliases)
        terms.extend(str(value) for value in entry.get("variables", []))
        terms.extend(str(value) for value in entry.get("categories", []))
        terms.extend(str(value) for value in entry.get("sources", []))

    cities = []
    for city, aliases in dictionary.get("cities", {}).items():
        normalized_aliases = [normalize(str(alias)) for alias in aliases]
        if any(alias and alias in normalized for alias in normalized_aliases):
            cities.append(city)
            terms.append(city)

    return {
        "matched": bool(matched_aliases),
        "intents": sorted(set(filter(None, intents))),
        "terms": sorted(set(normalize(term) for term in terms if term)),
        "variables": sorted(set(variables)),
        "categories": sorted(set(categories)),
        "sources": sorted(set(sources)),
        "tables": sorted(set(tables)),
        "cities": sorted(set(cities)),
        "detail_geo": any(normalize(str(term)) in normalized for term in dictionary.get("geo_detail_terms", [])),
        "comparison": any(normalize(str(term)) in normalized for term in dictionary.get("comparison_terms", [])),
        "time": any(normalize(str(term)) in normalized for term in dictionary.get("time_terms", [])),
    }


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def fetch_catalog_summary() -> dict[str, Any]:
    if DATA_API_URL:
        result = remote_request("catalog")
        result["tables"] = [
            {
                "table_name": table,
                "layer": "athena",
                "rows_loaded": None,
                "columns_loaded": None,
                "description": "Tabla catalogada en Glue Data Catalog.",
            }
            for table in result.get("tables", [])
            if table
        ]
        return result
    if not database_ready():
        return {
            "database": relative(DB_PATH),
            "ready": False,
            "sources": [],
            "variables": [],
        }

    with connect() as conn:
        sources = conn.execute(
            """
            SELECT source, COUNT(*) AS rows, COUNT(DISTINCT variable) AS variables
            FROM indicadores
            GROUP BY source
            ORDER BY rows DESC
            """
        ).fetchall()
        variables = conn.execute(
            """
            SELECT variable, source, COUNT(*) AS rows, MAX(period) AS latest_period
            FROM indicadores
            GROUP BY variable, source
            ORDER BY variable, source
            """
        ).fetchall()
        if table_exists(conn, "sql_table_catalog"):
            tables = conn.execute(
                """
                SELECT table_name, layer, rows_loaded, columns_loaded, description
                FROM sql_table_catalog
                ORDER BY layer, table_name
                """
            ).fetchall()
        else:
            tables = []

    return {
        "database": relative(DB_PATH),
        "ready": True,
        "sources": [dict(row) for row in sources],
        "variables": [dict(row) for row in variables],
        "tables": [dict(row) for row in tables],
        "semantic_dictionary": compact_semantic_dictionary(),
    }


def fetch_series(dataset: str | None = None, variable: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    if not database_ready():
        return []

    clauses = []
    params: list[Any] = []
    if dataset:
        clauses.append("dataset = ?")
        params.append(dataset)
    if variable:
        clauses.append("normalize_like(variable) LIKE ?")
        params.append(f"%{normalize(variable)}%")

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with connect() as conn:
        conn.create_function("normalize_like", 1, lambda value: normalize(str(value or "")))
        rows = conn.execute(
            f"""
            SELECT source, dataset, variable, metric, geo, period, value, unit, quality, notes, raw_file, extracted_at
            FROM indicadores
            {where}
            ORDER BY period
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_relevant_indicators(question: str, limit: int = 18) -> dict[str, Any]:
    if DATA_API_URL:
        normalized_question = normalize(question)
        semantic = semantic_query(question)
        terms = question_terms(question)
        cities = semantic["cities"] or [city for city in _KNOWN_CITIES if city in normalized_question]
        result = remote_request(
            "indicators",
            {
                "terms": terms[:12],
                "cities": cities,
                # Los alias semánticos son nombres legibles; Gold usa claves
                # normalizadas como contracts_registered. Los términos y la
                # categoría resuelven ese mapeo sin exigir igualdad literal.
                "variables": [],
                "categories": semantic["categories"][:8],
                "sources": semantic["sources"][:8],
                "limit": limit,
            },
        )
        result["semantic"] = semantic
        result["summary"] = {
            "database": result.get("database", "iseu"),
            "ready": result.get("ready", False),
            "sources": [],
            "variables": [],
            "tables": [],
        }
        return result
    if not database_ready():
        return {
            "database": relative(DB_PATH),
            "ready": False,
            "terms": [],
            "rows": [],
            "summary": fetch_catalog_summary(),
        }

    normalized_question = normalize(question)
    semantic = semantic_query(question)
    terms = question_terms(question)
    requested_cities = semantic["cities"] or [
        city
        for city in ("barcelona", "madrid", "valencia", "sevilla", "bilbao", "malaga", "zaragoza")
        if city in normalized_question
    ]
    detail_geo_intent = semantic["detail_geo"] or any(term in normalized_question for term in ("barrio", "barrios", "distrito", "distritos", "seccion", "secciones"))
    work_intent = any(intent.startswith("employment") for intent in semantic["intents"]) or any(term in normalized_question for term in ("trabajo", "empleo", "paro", "desempleo", "laboral"))
    cost_intent = "income" in semantic["intents"] or any(term in normalized_question for term in ("coste", "vida", "vivienda", "alquiler", "precio", "mudanza", "mudarme"))
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT source, dataset, variable, metric, geo, period, value, unit, quality, notes, raw_file, extracted_at
            FROM indicadores
            ORDER BY period DESC, id DESC
            """
        ).fetchall()

    scored = []
    for row in rows:
        item = dict(row)
        haystack = normalize(
            " ".join(
                str(item.get(key) or "")
                for key in ("source", "dataset", "variable", "metric", "geo", "notes")
            )
        )
        variable_text = normalize(
            " ".join(str(item.get(key) or "") for key in ("source", "dataset", "variable", "metric", "notes"))
        )
        geo_text = normalize(str(item.get("geo") or ""))
        variable_name = normalize(str(item.get("variable") or ""))
        dataset_name = normalize(str(item.get("dataset") or ""))
        source_name = normalize(str(item.get("source") or ""))
        score = sum(4 for term in terms if term and term in haystack)

        for variable in semantic["variables"]:
            normalized_variable = normalize(variable)
            if normalized_variable and normalized_variable == variable_name:
                score += 18
            elif normalized_variable and normalized_variable in variable_text:
                score += 10

        for category in semantic["categories"]:
            normalized_category = normalize(category)
            if normalized_category and normalized_category in dataset_name:
                score += 7
            if normalized_category and normalized_category in variable_text:
                score += 4

        for source in semantic["sources"]:
            normalized_source = normalize(source)
            if normalized_source and normalized_source == source_name:
                score += 6

        for city in requested_cities:
            exact_city = geo_text == city or geo_text.startswith(f"{city},")
            detailed_city = city in geo_text and not exact_city
            if detail_geo_intent and detailed_city:
                score += 12
            elif exact_city:
                score += 3 if detail_geo_intent else 12
            elif city in geo_text:
                score += 2

        if detail_geo_intent:
            notes_text = normalize(str(item.get("notes") or ""))
            if any(token in notes_text for token in ("neighborhood", "district", "census_section")):
                score += 6
            if "," in str(item.get("geo") or ""):
                score += 4

        if work_intent and any(term in variable_text for term in ("paro registrado", "contratos registrados", "tasa de paro", "tasa de empleo", "salario")):
            score += 8
        if cost_intent and any(term in variable_text for term in ("precio vivienda", "precio alquiler", "ipc", "precio electricidad")):
            score += 5

        if not requested_cities and "barcelona" in haystack:
            score += 1
        if item.get("quality") == "alta":
            score += 1
        if score > 0:
            item["score"] = score
            scored.append(item)

    if not scored:
        seen = set()
        fallback = []
        for row in rows:
            item = dict(row)
            key = (item.get("source"), item.get("variable"))
            if key in seen:
                continue
            seen.add(key)
            item["score"] = 0
            fallback.append(item)
            if len(fallback) >= limit:
                break
        scored = fallback
    else:
        scored.sort(
            key=lambda item: (
                item["score"],
                str(item.get("period") or ""),
                str(item.get("variable") or ""),
            ),
            reverse=True,
        )
        deduped = balanced_dedup(scored, requested_cities, limit) if requested_cities else []
        seen = set()
        for item in deduped:
            key = (
                item.get("source"),
                item.get("variable"),
                item.get("geo"),
                item.get("period"),
                item.get("value"),
                item.get("unit"),
            )
            seen.add(key)
        for item in scored:
            key = (
                item.get("source"),
                item.get("variable"),
                item.get("geo"),
                item.get("period"),
                item.get("value"),
                item.get("unit"),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
            if len(deduped) >= limit:
                break
        scored = deduped

    if "available_data" in semantic["intents"] and not semantic["variables"]:
        scored = []

    return {
        "database": relative(DB_PATH),
        "ready": True,
        "terms": terms[:20],
        "semantic": semantic,
        "rows": scored[:limit],
        "summary": fetch_catalog_summary(),
    }


def balanced_dedup(scored: list[dict[str, Any]], requested_cities: list[str], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen = set()
    for city in requested_cities:
        for item in scored:
            geo_text = normalize(str(item.get("geo") or ""))
            if city not in geo_text:
                continue
            key = (
                item.get("source"),
                item.get("variable"),
                item.get("geo"),
                item.get("period"),
                item.get("value"),
                item.get("unit"),
            )
            if key in seen:
                continue
            seen.add(key)
            selected.append(item)
            break
        if len(selected) >= limit:
            return selected
    return selected


def compact_semantic_dictionary() -> dict[str, Any]:
    dictionary = load_semantic_dictionary()
    aliases = dictionary.get("aliases", [])
    return {
        "version": dictionary.get("version"),
        "alias_count": len(aliases),
        "cities": sorted((dictionary.get("cities") or {}).keys()),
        "intents": [entry.get("intent") for entry in aliases],
    }


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type IN ('table', 'view') AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None
