from __future__ import annotations

import sqlite3
import unicodedata
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASETS_DIR = PROJECT_ROOT / "pag_web" / "Procesos" / "Datasets"
DB_PATH = DATASETS_DIR / "iseu_datos.sqlite"


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
    return DB_PATH.exists()


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
    return sorted(set(normalize(term) for term in terms))


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
    if not database_ready():
        return {
            "database": relative(DB_PATH),
            "ready": False,
            "terms": [],
            "rows": [],
            "summary": fetch_catalog_summary(),
        }

    normalized_question = normalize(question)
    terms = question_terms(question)
    requested_cities = [
        city
        for city in ("barcelona", "madrid", "valencia", "sevilla", "bilbao", "malaga", "zaragoza")
        if city in normalized_question
    ]
    detail_geo_intent = any(term in normalized_question for term in ("barrio", "barrios", "distrito", "distritos", "seccion", "secciones"))
    work_intent = any(term in normalized_question for term in ("trabajo", "empleo", "paro", "desempleo", "laboral"))
    cost_intent = any(term in normalized_question for term in ("coste", "vida", "vivienda", "alquiler", "precio", "mudanza", "mudarme"))
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
        score = sum(4 for term in terms if term and term in haystack)

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

        if "barcelona" in haystack:
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
        deduped = []
        seen = set()
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

    return {
        "database": relative(DB_PATH),
        "ready": True,
        "terms": terms[:20],
        "rows": scored[:limit],
        "summary": fetch_catalog_summary(),
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
