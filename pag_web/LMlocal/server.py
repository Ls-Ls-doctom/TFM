from __future__ import annotations

import csv
import json
import mimetypes
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai"
GROQ_MODEL = "llama-3.3-70b-versatile"


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
LOCAL_DIR = Path(__file__).resolve().parent
CONFIG_PATH = LOCAL_DIR / "config.json"
SYSTEM_PROMPT_PATH = LOCAL_DIR / "system_prompt.txt"
PROCESOS_DIR = ROOT / "Procesos"

sys.path.insert(0, str(PROCESOS_DIR))

from analysis_engine import analyze_question, should_analyze
from sql_data import DB_PATH, fetch_catalog_summary, fetch_relevant_indicators, normalize
from gemini_data import answer_with_gemini


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()


def read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw_body = handler.rfile.read(length)
    return json.loads(raw_body.decode("utf-8"))


def build_user_content(payload: dict) -> str:
    question = str(payload.get("message", "")).strip()
    context = payload.get("context", {})
    history = compact_history(payload.get("history", []))
    page_context = {
        "tema_activo": context.get("activeTopic"),
        "fuentes_disponibles": context.get("availableSources", []),
    }
    if should_use_data_context(question):
        data_section = "\n\nDatos locales disponibles para investigar:\n" + build_data_context(question)
    else:
        data_section = "\n\nModo conversacion simple: no uses ni menciones SQLite, datos locales, fuentes ni trazabilidad."

    return (
        ("/no_think\n" if not GROQ_API_KEY else "")
        + "Responde solo con la respuesta final en espanol, sin mostrar razonamiento interno ni pasos de pensamiento.\n"
        "Si el usuario pregunta por el historial, contesta usando el historial reciente, no pidas mas informacion.\n\n"
        "Historial reciente de la conversacion, en orden cronologico:\n"
        f"{format_history_for_prompt(history)}\n\n"
        "Contexto de la pagina:\n"
        f"{json.dumps(page_context, ensure_ascii=False, separators=(',', ':'))}\n\n"
        "Pregunta actual del usuario:\n"
        f"{question}\n\n"
        "Usa el historial para entender referencias como 'puedes analizarlo', 'eso', 'lo anterior', 'que te pregunte primero' o 'mi pregunta anterior'.\n\n"
        f"{data_section}"
    )


def compact_history(history: list) -> list[dict[str, str]]:
    compacted = []
    if not isinstance(history, list):
        return compacted
    for item in history[-8:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        compacted.append({"role": role, "content": content[:900]})
    return compacted


def format_history_for_prompt(history: list[dict[str, str]]) -> str:
    if not history:
        return "Sin historial previo."
    labels = {"user": "Usuario", "assistant": "Asistente"}
    return "\n".join(
        f"{index + 1}. {labels.get(item['role'], item['role'])}: {item['content']}"
        for index, item in enumerate(history)
    )


def answer_memory_question(question: str, history: list[dict[str, str]]) -> str | None:
    normalized = normalize(question)
    personal_answer = answer_personal_memory_question(normalized, history)
    if personal_answer:
        return personal_answer

    if not any(token in normalized for token in ("pregunte", "pregunta anterior", "primero", "memoria", "recuerdas")):
        return None

    user_turns = [item["content"] for item in history if item.get("role") == "user"]
    if not user_turns:
        return "Todavia no tengo mensajes anteriores en esta conversacion."

    if "primero" in normalized or "pregunte primero" in normalized:
        return f"Lo primero que me preguntaste fue: \"{user_turns[0]}\"."
    if "anterior" in normalized or "ultimo" in normalized or "ultima" in normalized:
        previous = user_turns[-2] if len(user_turns) >= 2 else user_turns[-1]
        return f"Tu pregunta anterior fue: \"{previous}\"."
    return f"Si, tengo el historial reciente de esta conversacion. Lo primero que me preguntaste fue: \"{user_turns[0]}\"."


def answer_personal_memory_question(normalized_question: str, history: list[dict[str, str]]) -> str | None:
    personal_markers = (
        "como me llamo",
        "cual es mi nombre",
        "donde vivo",
        "donde vivo yo",
        "mi apellido",
        "apellido paterno",
        "apellido materno",
    )
    if not any(marker in normalized_question for marker in personal_markers):
        return None

    facts = extract_user_personal_facts(history)

    if "como me llamo" in normalized_question or "cual es mi nombre" in normalized_question:
        if facts.get("nombre"):
            return f"Te llamas {facts['nombre']}."
        return "No me has dicho tu nombre en esta conversacion."

    if "donde vivo" in normalized_question:
        if facts.get("residencia"):
            return f"Vives en {facts['residencia']}."
        return "No me has dicho donde vives en esta conversacion."

    if "apellido materno" in normalized_question:
        if facts.get("apellido_materno"):
            return f"Tu apellido materno es {facts['apellido_materno']}."
        return "No me has dicho tu apellido materno en esta conversacion."

    if "apellido paterno" in normalized_question:
        if facts.get("apellido_paterno"):
            return f"Tu apellido paterno es {facts['apellido_paterno']}."
        if facts.get("apellido"):
            return f"Solo me has dicho un apellido: {facts['apellido']}. No puedo confirmar si es paterno o materno."
        return "No me has dicho tu apellido paterno en esta conversacion."

    if "mi apellido" in normalized_question:
        if facts.get("apellido"):
            return f"Tu apellido es {facts['apellido']}."
        return "No me has dicho tu apellido en esta conversacion."

    return None


def extract_user_personal_facts(history: list[dict[str, str]]) -> dict[str, str]:
    facts: dict[str, str] = {}
    for item in history:
        if item.get("role") != "user":
            continue
        text = item.get("content", "")
        normalized = normalize(text)

        name = match_personal_value(text, normalized, (r"\bme llamo\s+(.+)", r"\bmi nombre es\s+(.+)"))
        if name and not is_question_like(normalized):
            facts["nombre"] = clean_personal_value(name)

        residence = match_personal_value(text, normalized, (r"\bvivo en\s+(.+)", r"\bmi ciudad es\s+(.+)"))
        if residence and not is_question_like(normalized):
            facts["residencia"] = clean_personal_value(residence)

        paternal = match_personal_value(text, normalized, (r"\bapellido paterno es\s+(.+)", r"\bmi apellido paterno es\s+(.+)"))
        if paternal:
            facts["apellido_paterno"] = clean_personal_value(paternal)

        maternal = match_personal_value(text, normalized, (r"\bapellido materno es\s+(.+)", r"\bmi apellido materno es\s+(.+)"))
        if maternal:
            facts["apellido_materno"] = clean_personal_value(maternal)

        generic_last = match_personal_value(text, normalized, (r"\bmi apellido es\s+(.+)", r"\bahora mi apellido es\s+(.+)"))
        if generic_last:
            value = clean_personal_value(generic_last)
            facts["apellido"] = value
            facts.setdefault("apellido_paterno", value)

        correction = match_personal_value(text, normalized, (r"\bno,\s*es\s+(.+)", r"\bno es\s+(.+)"))
        if correction:
            value = clean_personal_value(correction)
            if "materno" in normalized or "apellido materno" in normalized_question_context(history, item):
                facts["apellido_materno"] = value
            else:
                facts["apellido"] = value

    return facts


def normalized_question_context(history: list[dict[str, str]], current_item: dict[str, str]) -> str:
    try:
        index = history.index(current_item)
    except ValueError:
        return ""
    previous = history[max(0, index - 2):index]
    return " ".join(normalize(item.get("content", "")) for item in previous)


def match_personal_value(original_text: str, normalized_text: str, patterns: tuple[str, ...]) -> str | None:
    import re

    for pattern in patterns:
        match = re.search(pattern, normalized_text, flags=re.IGNORECASE)
        if not match:
            continue
        start, end = match.span(1)
        return original_text[start:end]
    return None


def clean_personal_value(value: str) -> str:
    value = value.strip(" .,:;¿?¡!\"'")
    value = value.split("?")[0].strip()
    value = value.split(",")[0].strip()
    return value[:1].upper() + value[1:] if value else value


def is_question_like(normalized_text: str) -> bool:
    return "?" in normalized_text or normalized_text.startswith(("como ", "cual ", "donde ", "quien "))


def should_use_data_context(question: str) -> bool:
    normalized = normalize(question)
    simple_patterns = [
        "hola",
        "buenas",
        "buenos dias",
        "buenas tardes",
        "buenas noches",
        "como estas",
        "quien te creo",
        "quien eres",
        "que eres",
        "gracias",
    ]
    data_markers = [
        "dato",
        "datos",
        "ciudad",
        "ciudades",
        "compar",
        "empleo",
        "trabajo",
        "paro",
        "vivienda",
        "coste",
        "precio",
        "fuente",
        "sql",
        "grafico",
        "tabla",
    ]
    if any(pattern in normalized for pattern in simple_patterns) and not any(marker in normalized for marker in data_markers):
        return False

    data_keywords = [
        "barcelona",
        "calidad",
        "ciudad",
        "ciudades",
        "comparar",
        "comparado",
        "contratos",
        "coste",
        "dato",
        "datos",
        "dataset",
        "desempleo",
        "economia",
        "economía",
        "empleo",
        "energia",
        "energía",
        "fuente",
        "habitantes",
        "ib i",
        "ibi",
        "idescat",
        "ine",
        "ipc",
        "laboral",
        "paro",
        "poblacion",
        "población",
        "ree",
        "sanidad",
        "scraper",
        "tasa",
        "variable",
        "vab",
        "vivienda",
    ]
    return should_analyze(question) or any(keyword in normalized for keyword in data_keywords)


def safe_read_text(path: Path, max_chars: int = 6000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except OSError as error:
        return f"No se pudo leer {path.name}: {error}"


def summarize_csv(path: Path, max_rows: int = 4) -> dict:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as file:
        reader = csv.DictReader(file)
        rows = []
        for index, row in enumerate(reader):
            if index >= max_rows:
                break
            rows.append(row)

    return {
        "archivo": str(path.relative_to(PROJECT_ROOT)),
        "columnas": reader.fieldnames or [],
        "muestra": rows,
    }


def summarize_json(path: Path) -> dict:
    text = safe_read_text(path, max_chars=2500)
    try:
        parsed = json.loads(text)
        return {
            "archivo": str(path.relative_to(PROJECT_ROOT)),
            "contenido": parsed,
        }
    except json.JSONDecodeError:
        return {
            "archivo": str(path.relative_to(PROJECT_ROOT)),
            "texto": text[:3000],
        }


def dataset_relevance_score(path: Path, question: str) -> int:
    normalized = question.lower()
    path_text = str(path).lower()

    topic_keywords = {
        "ine": ["ine", "ipc", "inflacion", "paro", "empleo", "tasa", "salario", "coste", "vida"],
        "idescat": ["idescat", "poblacion", "vab", "ibi", "hotel", "turismo", "barcelona", "industria", "comercio", "coste", "vida"],
        "ree": ["ree", "energia", "electricidad", "demanda", "precio", "luz", "coste", "vida"],
        "mitma": ["mitma", "vivienda", "venta", "m2"],
        "empleo": ["empleo", "paro", "afiliacion", "sepe", "seguridad social", "trabajo"],
        "informe_ejecucion": ["calidad", "fuente", "scraper", "estado", "dataset", "datos", "variables"],
    }

    score = 0
    if path.suffix.lower() == ".csv":
        score += 4
    if "raw" in path_text:
        score += 2
    if "log" in path_text:
        score -= 2

    for folder, keywords in topic_keywords.items():
        if folder in path_text:
            score += 8 * sum(1 for keyword in keywords if keyword in normalized)

    if any(word in normalized for word in ["dato", "dataset", "fuente", "variable", "calidad"]):
        score += 2

    if "informe_ejecucion" in path_text:
        score += 3

    return score


def get_candidate_datasets(question: str) -> list[Path]:
    if not DATA_DIR.exists():
        return []

    scored_paths = sorted(
        [
            (dataset_relevance_score(path, question), path)
            for path in DATA_DIR.rglob("*")
            if path.is_file() and path.suffix.lower() in {".csv", ".json"}
        ],
        key=lambda item: (-item[0], str(item[1])),
    )

    return [path for score, path in scored_paths if score > 0][:8]


def build_data_payload(question: str) -> dict:
    if not should_use_data_context(question):
        return {
            "instruccion": "No se consultan indicadores porque la pregunta no requiere datos locales.",
            "pregunta": question,
            "database": "Base de datos",
            "indicadores": [],
            "log": [],
        }

    sql_payload = fetch_relevant_indicators(question, limit=12)
    log = [
        {
            "archivo": "Indicadores consultados",
            "tipo": "sqlite",
            "score": item.get("score", 0),
            "estado": "consultado",
            "variable": item.get("variable", ""),
            "periodo": item.get("period", ""),
            "fuente": item.get("source", ""),
        }
        for item in sql_payload.get("rows", [])
    ]

    compact_rows = compact_indicator_rows(sql_payload["rows"])
    return {
        "instruccion": (
            "Usa estos indicadores como evidencia y ofrece una opinion concreta. "
            "Cita fuente, territorio, periodo, valor y unidad. Usa las metricas derivadas cuando existan, "
            "explica su significado y no contradigas sus valores. No inventes datos."
        ),
        "pregunta": question,
        "database": "Base de datos",
        "database_ready": sql_payload["ready"],
        "terminos_busqueda": sql_payload["terms"],
        "semantic_sql": compact_semantic_payload(sql_payload.get("semantic", {})),
        "indicadores": compact_rows,
        "metricas_derivadas": build_derived_metrics(compact_rows),
        "catalogo": compact_catalog_summary(sql_payload["summary"]),
        "log": log,
    }


def build_derived_metrics(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    latest_period = max((str(row.get("period") or "") for row in rows), default="")
    latest_rows = [row for row in rows if str(row.get("period") or "") == latest_period]
    city_metrics: dict[str, dict[str, float]] = defaultdict(dict)
    for row in latest_rows:
        city = str(row.get("geo") or "").strip()
        variable = normalize(str(row.get("variable") or ""))
        if not city:
            continue
        try:
            value = float(row.get("value"))
        except (TypeError, ValueError):
            continue
        if "contrat" in variable:
            city_metrics[city]["contracts"] = value
        if "demand" in variable or "paro" in variable:
            city_metrics[city]["job_seekers"] = value

    ratios = []
    for city, metrics in city_metrics.items():
        contracts = metrics.get("contracts")
        job_seekers = metrics.get("job_seekers")
        if contracts is None or not job_seekers:
            continue
        ratios.append({
            "territorio": city,
            "periodo": latest_period,
            "contratos": contracts,
            "demandantes": job_seekers,
            "contratos_por_demandante": round(contracts / job_seekers, 3),
        })
    if len(ratios) < 2:
        return []
    ordered_ratios = sorted(ratios, key=lambda item: item["contratos_por_demandante"], reverse=True)
    return [{
        "metrica": "contratos_por_demandante",
        "descripcion": "Proxy de dinamismo laboral: contratos registrados divididos por demandantes de empleo en el mismo periodo.",
        "criterio": "Un valor mayor indica mas volumen de contratacion por demandante; no equivale a probabilidad individual de conseguir empleo.",
        "fuente": "SEPE",
        "orden_descendente": [item["territorio"] for item in ordered_ratios],
        "territorio_lider_segun_metrica": ordered_ratios[0]["territorio"],
        "comparacion_calculada": (
            f"{ordered_ratios[0]['territorio']} ({ordered_ratios[0]['contratos_por_demandante']}) > "
            f"{ordered_ratios[1]['territorio']} ({ordered_ratios[1]['contratos_por_demandante']})"
        ),
        "valores": ordered_ratios,
    }]


def compact_indicator_rows(rows: list[dict]) -> list[dict]:
    keys = ("source", "dataset", "variable", "metric", "geo", "period", "value", "unit", "quality", "score")
    return [{key: row.get(key) for key in keys if key in row} for row in rows[:12]]


def compact_catalog_summary(summary: dict) -> dict:
    sources = summary.get("sources", [])
    variables = summary.get("variables", [])
    tables = summary.get("tables", [])
    return {
        "database": "Base de datos",
        "ready": summary.get("ready"),
        "source_count": len(sources),
        "variable_count": len(variables),
        "table_count": len(tables),
        "sources": sources,
        "tables": [
            {
                "table_name": table.get("table_name"),
                "layer": table.get("layer"),
                "rows_loaded": table.get("rows_loaded"),
                "columns_loaded": table.get("columns_loaded"),
            }
            for table in tables[:16]
        ],
    }


def compact_semantic_payload(semantic: dict) -> dict:
    return {
        "matched": semantic.get("matched", False),
        "intents": semantic.get("intents", [])[:6],
        "variables": semantic.get("variables", [])[:8],
        "categories": semantic.get("categories", [])[:6],
        "sources": semantic.get("sources", [])[:6],
        "cities": semantic.get("cities", [])[:8],
        "detail_geo": semantic.get("detail_geo", False),
        "comparison": semantic.get("comparison", False),
        "time": semantic.get("time", False),
    }


def build_data_context(question: str) -> str:
    return json.dumps(build_data_payload(question), ensure_ascii=False, separators=(",", ":"))


def build_analysis_payload(question: str) -> dict:
    analysis = analyze_question(question)
    if analysis is None:
        return {
            "activado": False,
            "motivo": "La pregunta no requiere procesamiento pandas.",
            "analisis": [],
        }
    return analysis


def build_analysis_context(question: str) -> str:
    return json.dumps(build_analysis_payload(question), ensure_ascii=False, separators=(",", ":"))


def build_trace(payload: dict) -> dict:
    question = str(payload.get("message", "")).strip()
    data_payload = build_data_payload(question)
    use_data = should_use_data_context(question)
    analysis_payload = build_analysis_payload(question) if use_data else {
        "activado": False,
        "analisis": [],
    }
    local_data = build_local_visual_data(question, data_payload)
    return {
        "provider": "assistant",
        "model": load_config().get("model", "Modelo configurado"),
        "maxTokens": load_config().get("maxTokens"),
        "question": question,
        "usesData": use_data,
        "analysis": {
            "enabled": analysis_payload["activado"],
            "items": len(analysis_payload["analisis"]),
        },
        "datasets": data_payload["log"],
        "localData": local_data,
    }


def build_dashboard_payload() -> dict:
    summary = fetch_catalog_summary()
    sqlite_report_path = ROOT / "Procesos" / "Datasets" / "sqlite_carga.json"
    execution_report_path = PROJECT_ROOT / "api_clients" / "data" / "informe_ejecucion.json"
    sqlite_report = load_optional_json(sqlite_report_path)
    execution_report = load_optional_json(execution_report_path)
    latest_rows = []
    quality_rows = []
    top_variable_rows = []
    period_rows = []
    source_variable_rows = []
    city_rows = []
    city_update_rows = []
    catalog_rows = []
    detail_rows = int(sqlite_report.get("detail_rows_loaded") or 0)

    if DB_PATH.exists():
        import sqlite3

        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            latest_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT source, variable, metric, geo, period, value, unit, quality
                    FROM indicadores
                    ORDER BY period DESC, id DESC
                    LIMIT 12
                    """
                ).fetchall()
            ]
            quality_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT COALESCE(NULLIF(TRIM(quality), ''), 'Sin clasificar') AS quality, COUNT(*) AS rows
                    FROM indicadores
                    GROUP BY COALESCE(NULLIF(TRIM(quality), ''), 'Sin clasificar')
                    ORDER BY rows DESC
                    """
                ).fetchall()
            ]
            top_variable_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT variable, COUNT(*) AS rows
                    FROM indicadores
                    GROUP BY variable
                    ORDER BY rows DESC
                    LIMIT 10
                    """
                ).fetchall()
            ]
            period_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT SUBSTR(COALESCE(period, ''), 1, 4) AS period_group, COUNT(*) AS rows
                    FROM indicadores
                    WHERE period IS NOT NULL AND TRIM(period) <> ''
                    GROUP BY SUBSTR(period, 1, 4)
                    HAVING period_group GLOB '[0-9][0-9][0-9][0-9]'
                    ORDER BY period_group DESC
                    LIMIT 8
                    """
                ).fetchall()
            ]
            source_variable_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT source, COUNT(DISTINCT variable) AS variables
                    FROM indicadores
                    GROUP BY source
                    ORDER BY variables DESC, source
                    """
                ).fetchall()
            ]
            city_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    WITH normalized AS (
                        SELECT
                            CASE
                                WHEN LOWER(geo) LIKE '%barcelona%' THEN 'Barcelona'
                                WHEN LOWER(geo) LIKE '%madrid%' THEN 'Madrid'
                                WHEN LOWER(geo) LIKE '%valencia%' THEN 'Valencia'
                                WHEN LOWER(geo) LIKE '%sevilla%' THEN 'Sevilla'
                                WHEN LOWER(geo) LIKE '%bilbao%' THEN 'Bilbao'
                                WHEN LOWER(geo) LIKE '%malaga%' OR LOWER(geo) LIKE '%málaga%' THEN 'Malaga'
                                WHEN LOWER(geo) LIKE '%zaragoza%' THEN 'Zaragoza'
                                ELSE NULL
                            END AS city,
                            variable,
                            source
                        FROM indicadores
                        WHERE geo IS NOT NULL AND TRIM(geo) <> ''
                    )
                    SELECT
                        city,
                        COUNT(*) AS rows,
                        COUNT(DISTINCT variable) AS variables,
                        COUNT(DISTINCT source) AS sources
                    FROM normalized
                    WHERE city IS NOT NULL
                    GROUP BY city
                    ORDER BY rows DESC, city
                    """
                ).fetchall()
            ]
            city_update_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    WITH normalized AS (
                        SELECT
                            CASE
                                WHEN LOWER(geo) LIKE '%barcelona%' THEN 'Barcelona'
                                WHEN LOWER(geo) LIKE '%madrid%' THEN 'Madrid'
                                WHEN LOWER(geo) LIKE '%valencia%' THEN 'Valencia'
                                WHEN LOWER(geo) LIKE '%sevilla%' THEN 'Sevilla'
                                WHEN LOWER(geo) LIKE '%bilbao%' THEN 'Bilbao'
                                WHEN LOWER(geo) LIKE '%malaga%' OR LOWER(geo) LIKE '%málaga%' THEN 'Malaga'
                                WHEN LOWER(geo) LIKE '%zaragoza%' THEN 'Zaragoza'
                                ELSE NULL
                            END AS city,
                            period,
                            extracted_at,
                            source
                        FROM indicadores
                        WHERE geo IS NOT NULL AND TRIM(geo) <> ''
                    )
                    SELECT
                        city,
                        MAX(extracted_at) AS received_at,
                        MAX(period) AS latest_period,
                        COUNT(*) AS rows,
                        COUNT(DISTINCT source) AS source_count,
                        GROUP_CONCAT(DISTINCT source) AS sources
                    FROM normalized
                    WHERE city IS NOT NULL
                    GROUP BY city
                    ORDER BY received_at DESC, city
                    """
                ).fetchall()
            ]
            catalog_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    WITH enriched AS (
                        SELECT
                            variable,
                            metric,
                            source,
                            period,
                            extracted_at,
                            CASE
                                WHEN LOWER(geo) LIKE '%barcelona%' THEN 'Barcelona'
                                WHEN LOWER(geo) LIKE '%madrid%' THEN 'Madrid'
                                WHEN LOWER(geo) LIKE '%valencia%' THEN 'Valencia'
                                WHEN LOWER(geo) LIKE '%sevilla%' THEN 'Sevilla'
                                WHEN LOWER(geo) LIKE '%bilbao%' THEN 'Bilbao'
                                WHEN LOWER(geo) LIKE '%malaga%' OR LOWER(geo) LIKE '%málaga%' THEN 'Malaga'
                                WHEN LOWER(geo) LIKE '%zaragoza%' THEN 'Zaragoza'
                                ELSE NULL
                            END AS city
                        FROM indicadores
                        WHERE variable IS NOT NULL AND TRIM(variable) <> ''
                    )
                    SELECT
                        variable,
                        MIN(NULLIF(TRIM(metric), '')) AS description,
                        GROUP_CONCAT(DISTINCT source) AS sources,
                        MIN(period) AS first_period,
                        MAX(period) AS latest_period,
                        MAX(extracted_at) AS received_at,
                        COUNT(*) AS rows,
                        COUNT(DISTINCT city) AS city_count
                    FROM enriched
                    GROUP BY variable
                    ORDER BY variable
                    """
                ).fetchall()
            ]
            detail_tables = [
                "semantic_observations",
                "indicators",
                "indicator_catalog",
                "sql_table_catalog",
            ]
            detail_tables.extend(
                row["name"]
                for row in conn.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table' AND name LIKE 'silver_%'
                    ORDER BY name
                    """
                ).fetchall()
            )
            counted_tables = []
            for table_name in dict.fromkeys(detail_tables):
                exists = conn.execute(
                    """
                    SELECT 1
                    FROM sqlite_master
                    WHERE type = 'table' AND name = ?
                    """,
                    (table_name,),
                ).fetchone()
                if not exists:
                    continue
                rows = conn.execute(f'SELECT COUNT(*) AS rows FROM "{table_name}"').fetchone()["rows"]
                counted_tables.append((table_name, int(rows or 0)))
            if counted_tables:
                detail_rows = sum(rows for _, rows in counted_tables)

    sources = summary.get("sources", [])
    variables = summary.get("variables", [])
    total_rows = sum(int(item.get("rows") or 0) for item in sources)
    return {
        "ready": summary.get("ready", False),
        "storageLabel": "Base de datos activa",
        "updatedAt": sqlite_report.get("loaded_at") or execution_report.get("timestamp") or "",
        "kpis": {
            "indicatorRows": total_rows,
            "sourceCount": len(sources),
            "variableCount": len(variables),
            "detailRows": detail_rows,
        },
        "sources": sources,
        "cities": city_rows,
        "cityUpdates": city_update_rows,
        "indicatorCatalog": catalog_rows,
        "variables": variables[:80],
        "latestRows": latest_rows,
        "charts": {
            "quality": quality_rows,
            "topVariables": top_variable_rows,
            "periods": period_rows,
            "sourceVariables": source_variable_rows,
        },
        "pipeline": {
            "apis": execution_report.get("resumen", {}),
            "dataLoad": sanitize_sqlite_report(sqlite_report),
        },
    }


def sanitize_sqlite_report(report: dict) -> dict:
    if not report:
        return {}
    clean = {
        "loaded_at": report.get("loaded_at"),
        "rows_loaded": report.get("rows_loaded"),
        "derived_indicator_rows_loaded": report.get("derived_indicator_rows_loaded"),
        "detail_rows_loaded": report.get("detail_rows_loaded"),
        "rows_by_source": report.get("rows_by_source", []),
    }
    clean["detail_tables"] = [
        {
            "table_name": item.get("table_name"),
            "rows_loaded": item.get("rows_loaded"),
            "columns_loaded": item.get("columns_loaded"),
        }
        for item in report.get("detail_tables", [])
        if isinstance(item, dict)
    ]
    return clean


def load_optional_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build_local_visual_data(question: str, data_payload: dict) -> dict:
    rows = data_payload.get("indicadores", [])
    table = []

    for row in rows:
        geo = str(row.get("geo") or "").strip()
        variable = str(row.get("variable") or row.get("dataset") or "Indicador").strip()
        period = str(row.get("period") or "").strip()
        unit = str(row.get("unit") or "").strip()
        source = str(row.get("source") or "").strip()
        quality = str(row.get("quality") or "n/d").strip()
        table.append([
            variable,
            geo or "Territorio n/d",
            period or "Periodo n/d",
            format_metric_value(row.get("value"), unit),
            source or "Fuente n/d",
            quality,
        ])

    sources = sorted({str(row.get("source")) for row in rows if row.get("source")})
    return {
        "label": "Datos SQL",
        "title": "Indicadores recuperados",
        "summary": f"Vista generada para: {question}",
        "source": " / ".join(sources) if sources else "Base de datos activa",
        "confidence": infer_visual_confidence(rows),
        "tableHeaders": ["Indicador", "Territorio", "Periodo", "Valor", "Fuente", "Calidad"],
        "table": table[:10],
        "chart": choose_visualization(question, rows),
    }


def choose_visualization(question: str, rows: list[dict]) -> dict:
    numeric_rows = []
    for row in rows:
        try:
            value = float(row.get("value"))
        except (TypeError, ValueError):
            continue
        numeric_rows.append({**row, "numeric_value": value})

    if not numeric_rows:
        return {"type": "empty", "title": "Sin valores numericos", "reason": "No hay valores numericos suficientes."}

    normalized_question = normalize(question)
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in numeric_rows:
        key = (str(row.get("variable") or "Indicador"), str(row.get("unit") or ""))
        grouped[key].append(row)

    time_candidates = []
    for (variable, unit), group in grouped.items():
        periods = {str(row.get("period") or "") for row in group if row.get("period")}
        geos = {str(row.get("geo") or "Total") for row in group}
        if len(periods) >= 2:
            preference = 10 if "contrat" in normalize(variable) else 0
            time_candidates.append((len(periods) * max(1, len(geos)) + preference, variable, unit, group))

    if time_candidates:
        _, variable, unit, group = max(time_candidates, key=lambda item: item[0])
        labels = sorted({str(row.get("period")) for row in group if row.get("period")})[-8:]
        series = []
        for geo in sorted({str(row.get("geo") or "Total") for row in group}):
            values_by_period = {
                str(row.get("period")): row["numeric_value"]
                for row in group
                if str(row.get("geo") or "Total") == geo
            }
            values = [values_by_period.get(period) for period in labels]
            if sum(value is not None for value in values) >= 2:
                series.append({"name": geo, "values": values})
        if series:
            return {
                "type": "line",
                "title": f"Evolucion de {variable}",
                "reason": "Se eligio una linea porque los datos forman una serie temporal comparable.",
                "labels": labels,
                "series": series[:4],
                "unit": unit,
            }

    latest_by_geo_variable = {}
    for row in sorted(numeric_rows, key=lambda item: str(item.get("period") or "")):
        key = (str(row.get("geo") or "Total"), str(row.get("variable") or "Indicador"))
        latest_by_geo_variable[key] = row
    geos = sorted({key[0] for key in latest_by_geo_variable})
    variables = sorted({key[1] for key in latest_by_geo_variable})

    if len(geos) >= 2 and len(variables) >= 3:
        radar_variables = variables[:6]
        series = []
        for geo in geos[:4]:
            normalized_values = []
            raw_values = []
            for variable in radar_variables:
                values = [
                    latest_by_geo_variable[(candidate_geo, variable)]["numeric_value"]
                    for candidate_geo in geos
                    if (candidate_geo, variable) in latest_by_geo_variable
                ]
                row = latest_by_geo_variable.get((geo, variable))
                raw_value = row["numeric_value"] if row else None
                raw_values.append(raw_value)
                if raw_value is None or not values:
                    normalized_values.append(0)
                elif max(values) == min(values):
                    normalized_values.append(100)
                else:
                    normalized_values.append(round((raw_value - min(values)) / (max(values) - min(values)) * 100, 1))
            series.append({"name": geo, "values": normalized_values, "rawValues": raw_values})
        return {
            "type": "radar",
            "title": "Perfil comparado de ciudades",
            "reason": "Se eligio un radar para comparar varias dimensiones entre territorios.",
            "labels": radar_variables,
            "series": series,
            "unit": "indice normalizado 0-100",
        }

    selected_rows = numeric_rows[:8]
    values = [row["numeric_value"] for row in selected_rows]
    labels = [
        " - ".join(filter(None, (str(row.get("variable") or "Indicador"), str(row.get("geo") or ""))))
        for row in selected_rows
    ]
    if any(token in normalized_question for token in ("reparto", "distribucion", "proporcion", "porcentaje")) and all(value >= 0 for value in values):
        return {
            "type": "doughnut",
            "title": "Distribucion de valores",
            "reason": "Se eligio un grafico de anillo porque la pregunta pide una distribucion proporcional.",
            "labels": labels,
            "values": values,
            "unit": str(selected_rows[0].get("unit") or ""),
        }

    return {
        "type": "bar",
        "title": "Comparacion de indicadores",
        "reason": "Se eligieron barras porque permiten comparar categorias independientes.",
        "labels": labels,
        "values": values,
        "displayValues": [format_metric_value(row["numeric_value"], str(row.get("unit") or "")) for row in selected_rows],
        "unit": str(selected_rows[0].get("unit") or ""),
    }


def format_metric_value(value, unit: str) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value or "")
    if abs(number) >= 1000:
        text = f"{number:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        text = f"{number:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    translated_units = {
        "persons": "personas",
        "person": "personas",
        "contracts": "contratos",
        "contract": "contratos",
        "percent": "%",
        "percentage": "%",
    }
    display_unit = translated_units.get(unit.lower().strip(), unit)
    return f"{text} {display_unit}".strip()


def infer_visual_confidence(rows: list[dict]) -> str:
    qualities = [str(row.get("quality") or "").lower() for row in rows]
    if qualities and all(quality == "alta" for quality in qualities):
        return "Alta"
    if any(quality == "alta" for quality in qualities):
        return "Media-alta"
    return "Media"


def build_lm_studio_request(payload: dict, stream: bool = False) -> urllib.request.Request:
    config = load_config()
    if GROQ_API_KEY:
        base_url = GROQ_BASE_URL
        model = GROQ_MODEL
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_API_KEY}"}
        messages = [
            {"role": "system", "content": load_system_prompt()},
            {"role": "user", "content": build_user_content(payload)},
        ]
    else:
        base_url = config["lmStudioBaseUrl"].rstrip("/")
        model = config["model"]
        headers = {"Content-Type": "application/json"}
        messages = [
            {"role": "system", "content": load_system_prompt()},
            {"role": "user", "content": build_user_content(payload)},
            {"role": "assistant", "content": "Respuesta final:"},
        ]
    url = f"{base_url}/v1/chat/completions"
    body = {
        "model": model,
        "temperature": config.get("temperature", 0.3),
        "max_tokens": config.get("maxTokens", 700),
        "stream": stream,
        "messages": messages,
    }
    return urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )


def build_lm_studio_chat_request(payload: dict) -> urllib.request.Request:
    config = load_config()
    base_url = config["lmStudioBaseUrl"].rstrip("/")
    url = f"{base_url}/api/v1/chat"
    body = {
        "model": config["model"],
        "system_prompt": load_system_prompt(),
        "input": build_user_content(payload),
    }

    return urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )


def build_lm_studio_chat_stream_request(payload: dict) -> urllib.request.Request:
    config = load_config()
    base_url = config["lmStudioBaseUrl"].rstrip("/")
    url = f"{base_url}/api/v1/chat"
    body = {
        "model": config["model"],
        "system_prompt": load_system_prompt(),
        "input": build_user_content(payload),
        "stream": True,
    }

    return urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )


def call_lm_studio(payload: dict) -> str:
    answer, _trace = answer_with_gemini(payload)
    return answer


def review_data_answer_with_model(payload: dict, draft_answer: str) -> str:
    config = load_config()
    base_url = config["lmStudioBaseUrl"].rstrip("/")
    url = f"{base_url}/v1/chat/completions"
    question = str(payload.get("message", "")).strip()
    data = build_data_payload(question)
    evidence = {
        "indicadores": data.get("indicadores", [])[:10],
        "metricas_derivadas": data.get("metricas_derivadas", []),
    }
    review_prompt = (
        f"Pregunta del usuario:\n{question}\n\n"
        f"Evidencia disponible:\n{json.dumps(evidence, ensure_ascii=False)}\n\n"
        f"Borrador que debes revisar:\n{draft_answer}\n\n"
        "Devuelve exactamente tres frases en espanol: (1) una recomendacion concreta del territorio indicado en "
        "territorio_lider_segun_metrica; (2) la comparacion del proxy usando solo comparacion_calculada y explicando "
        "que un valor mayor indica mas contratos por demandante; (3) la limitacion metodologica. No compares ni "
        "califiques por separado los recuentos brutos de contratos o demandantes. No menciones coste de vida, "
        "vivienda, salarios ni variables ausentes. No expliques la revision."
    )
    body = {
        "model": config["model"],
        "temperature": 0.1,
        "max_tokens": min(int(config.get("maxTokens", 700)), 520),
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres el revisor factual final de ISEU. Tu salida se muestra directamente al usuario. "
                    "Usa solo la evidencia proporcionada. Obedece territorio_lider_segun_metrica y "
                    "comparacion_calculada sin reinterpretarlos. Debes mantener una recomendacion clara."
                ),
            },
            {"role": "user", "content": review_prompt},
        ],
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = int(config.get("requestTimeoutSeconds", 90))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response_body = json.loads(response.read().decode("utf-8"))
    choices = response_body.get("choices", [])
    if not choices:
        raise RuntimeError("El modelo revisor no devolvio una respuesta.")
    reviewed = extract_final_answer(choices[0].get("message", {}).get("content", "")).strip()
    if not reviewed:
        raise RuntimeError("El modelo revisor devolvio una respuesta vacia.")
    return reviewed


def iter_lm_studio_chat_message_stream(payload: dict):
    config = load_config()
    request = build_lm_studio_chat_stream_request(payload)
    timeout = int(config.get("requestTimeoutSeconds", 90))
    event_name = "message"

    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
                continue

            if not line.startswith("data:"):
                continue

            data = line.removeprefix("data:").strip()
            try:
                payload_data = json.loads(data)
            except json.JSONDecodeError:
                continue

            event_type = payload_data.get("type") or event_name
            if event_type == "message.delta":
                content = payload_data.get("content")
                if content:
                    yield {"type": "delta", "text": content}
            elif event_type in {"message.end", "chat.end"}:
                yield {"type": "finish", "finishReason": "stop"}
                return

    yield {"type": "finish", "finishReason": "stop"}


def ensure_user_facing_answer(payload: dict, answer: str) -> str:
    answer = extract_final_answer(answer).strip()
    suspicious = [
        "Thinking Process",
        "Thinking:",
        "<think>",
        "Analyze the Request",
        "Draft",
        "Final Review",
        "Final Polish",
        "This is",
        "It covers",
        "sentence",
    ]
    if answer and not any(marker.lower() in answer.lower() for marker in suspicious):
        return answer.strip()
    repaired = extract_final_answer(call_lm_studio_final(payload)).strip()
    if repaired and not any(marker.lower() in repaired.lower() for marker in suspicious):
        return repaired
    raise RuntimeError("El modelo no devolvio una respuesta final util.")


def build_local_fallback_answer(payload: dict) -> str:
    question = str(payload.get("message", "")).strip()
    normalized_question = normalize(question)
    if not should_use_data_context(question):
        return "Hola. Soy ISEU Assistant. Puedo ayudarte a revisar el dashboard, explicar fuentes y responder preguntas sobre los indicadores urbanos cargados."

    data = build_data_payload(question)
    rows = data.get("indicadores", [])[:4]
    if not rows:
        catalog = data.get("catalogo", {})
        tables = catalog.get("tables", [])
        if tables and any(token in normalize(question) for token in ("tabla", "tablas", "fuente", "fuentes", "sql", "datos disponibles")):
            lines = ["La base SQLite tiene estas tablas principales disponibles:"]
            for table in tables[:8]:
                lines.append(
                    f"- {table.get('table_name')}: capa {table.get('layer')}, {table.get('rows_loaded')} filas."
                )
            return "\n".join(lines)
        return "No he encontrado indicadores suficientes para responder esa pregunta con datos. Prueba a preguntar por empleo, vivienda, coste de vida, energia, poblacion o fuentes disponibles."

    comparison_answer = build_comparison_recommendation(question, rows)
    if comparison_answer:
        return comparison_answer

    is_move_or_job_query = any(
        token in normalized_question
        for token in ("mudar", "mudanza", "oferta laboral", "informatica", "informática", "oportunidad", "oportunidades", "coste de vida")
    )
    if is_move_or_job_query:
        lines = [
            "Para evaluar esa mudanza puedo darte una lectura orientativa con los indicadores disponibles, pero hay una cautela importante: no tengo un desglose directo de contratos por sector informatico.",
            "Como aproximacion, uso los indicadores laborales generales recuperados y separo lo que es dato directo de lo que requiere interpretacion:",
        ]
    else:
        lines = [
            "He recuperado indicadores relacionados con tu pregunta. Estos son los mas relevantes:"
        ]
    for row in rows:
        value = format_metric_value(row.get("value"), str(row.get("unit") or ""))
        lines.append(
            f"- {row.get('source', 'Fuente n/d')}: {row.get('variable', 'Variable n/d')} en {row.get('geo', 'territorio n/d')} ({row.get('period', 'periodo n/d')}): {value}."
        )
    if is_move_or_job_query:
        lines.append("Con estos datos puedo comparar el contexto laboral general entre ciudades, pero no afirmar oportunidades especificas en informatica sin una fuente sectorial adicional.")
    else:
        lines.append("Usa la vista de tablas o graficos para revisar la trazabilidad completa.")
    return "\n".join(lines)


def build_comparison_recommendation(question: str, rows: list[dict]) -> str | None:
    normalized_question = normalize(question)
    if not any(token in normalized_question for token in ("compar", "mejor", "entre", "o ", "vivir", "mudar")):
        return None

    cities = sorted({str(row.get("geo") or "").strip() for row in rows if row.get("geo")})
    if len(cities) < 2:
        return None

    latest_period = max((str(row.get("period") or "") for row in rows), default="")
    latest_rows = [row for row in rows if str(row.get("period") or "") == latest_period]
    city_metrics: dict[str, dict[str, float]] = defaultdict(dict)
    for row in latest_rows:
        city = str(row.get("geo") or "").strip()
        variable = normalize(str(row.get("variable") or ""))
        try:
            value = float(row.get("value"))
        except (TypeError, ValueError):
            continue
        if "contrat" in variable:
            city_metrics[city]["contracts"] = value
        if "demand" in variable or "paro" in variable:
            city_metrics[city]["job_seekers"] = value

    ratios = {
        city: metrics["contracts"] / metrics["job_seekers"]
        for city, metrics in city_metrics.items()
        if metrics.get("contracts") is not None and metrics.get("job_seekers", 0) > 0
    }
    if len(ratios) >= 2:
        winner = max(ratios, key=ratios.get)
        ordered = sorted(ratios, key=ratios.get, reverse=True)
        facts = []
        ratio_facts = []
        for city in ordered[:3]:
            metrics = city_metrics[city]
            facts.append(
                f"{city}: {format_metric_value(metrics['contracts'], 'contratos')} y "
                f"{format_metric_value(metrics['job_seekers'], 'demandantes')}"
            )
            ratio_facts.append(f"{city} {ratios[city]:.2f}".replace(".", ","))
        return (
            f"Mi recomendacion es {winner} si tu prioridad principal es encontrar trabajo.\n\n"
            f"En {latest_period}, SEPE registra " + "; ".join(facts) + ".\n\n"
            "Como proxy de dinamismo laboral, la relacion contratos por demandante es "
            + " frente a ".join(ratio_facts)
            + f", por lo que {winner} muestra una actividad de contratacion claramente mayor en los datos disponibles.\n\n"
            "Esta es una recomendacion laboral, no una conclusion completa sobre calidad de vida: los recuentos no estan ajustados por poblacion y faltan vivienda, salarios y sector profesional."
        )

    contracts = {
        city: metrics["contracts"]
        for city, metrics in city_metrics.items()
        if metrics.get("contracts") is not None
    }
    if len(contracts) >= 2:
        winner = max(contracts, key=contracts.get)
        facts = "; ".join(f"{city}: {format_metric_value(value, 'contratos')}" for city, value in contracts.items())
        return (
            f"Con los datos laborales disponibles, me inclino por {winner}.\n\n"
            f"En {latest_period}, SEPE registra {facts}.\n\n"
            "La recomendacion es orientativa porque compara volumen de contratacion sin ajustar por poblacion, salarios ni coste de vivienda."
        )
    return None


def build_direct_recommendation(payload: dict) -> str | None:
    question = str(payload.get("message", "")).strip()
    if not should_use_data_context(question):
        return None
    data = build_data_payload(question)
    return build_comparison_recommendation(question, data.get("indicadores", []))


def call_lm_studio_final(payload: dict) -> str:
    config = load_config()
    if GROQ_API_KEY:
        base_url = GROQ_BASE_URL
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_API_KEY}"}
    else:
        base_url = config["lmStudioBaseUrl"].rstrip("/")
        headers = {"Content-Type": "application/json"}
    url = f"{base_url}/v1/chat/completions"
    question = str(payload.get("message", "")).strip()
    use_data = should_use_data_context(question)
    if use_data:
        data = build_data_payload(question)
        rows = data.get("indicadores", [])[:6]
        facts = "; ".join(
            f"{row.get('source')} {row.get('variable')} {row.get('geo')} {row.get('period')}: {row.get('value')} {row.get('unit')}"
            for row in rows
        )
        final_input = (
            f"Pregunta: {question}\n"
            f"Datos recuperados desde SQLite:\n{facts}\n"
            "Instruccion de respuesta: si faltan datos directos para una parte de la pregunta, "
            "explicalo de forma profesional y ofrece la mejor aproximacion con los indicadores disponibles. "
            "No digas simplemente que no hay datos; separa dato directo, aproximacion disponible y cautela.\n"
            "Respuesta final:"
        )
    else:
        final_input = f"Pregunta: {question}\nRespuesta conversacional breve, sin mencionar datos ni SQLite:"
    body = {
        "model": config["model"],
        "temperature": config.get("temperature", 0.3),
        "max_tokens": min(int(config.get("maxTokens", 700)), 450),
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Responde en espanol al usuario final. No muestres razonamiento. "
                    "Si recibes datos, usa exactamente esos datos y cita sus fuentes. "
                    "Si el usuario pide variables no disponibles, dilo con claridad y propone indicadores relacionados como aproximacion. "
                    "Para mudanzas o comparaciones entre ciudades, estructura la respuesta en lectura general, empleo, coste/renta si existe y limites. "
                    "Si no recibes datos, responde de forma natural sin mencionar bases de datos, fuentes ni trazabilidad. "
                    "Maximo 5 frases."
                ),
            },
            {"role": "user", "content": final_input},
        ],
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    timeout = int(config.get("requestTimeoutSeconds", 90))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response_body = json.loads(response.read().decode("utf-8"))

    choices = response_body.get("choices", [])
    if not choices:
        return ""
    return extract_final_answer(choices[0].get("message", {}).get("content", ""))


def extract_final_answer(text: str) -> str:
    if not text:
        return ""

    clean_text = text.strip()
    for stop_marker in (
        "\n\nInstrucción:",
        "\n\nInstruction:",
        "\n\nNo inventar datos",
        "\nNo inventar datos",
        "\n</think>",
        "</think>",
    ):
        marker_index = clean_text.find(stop_marker)
        if marker_index > 0 and "Thinking Process:" not in clean_text[:marker_index]:
            clean_text = clean_text[:marker_index].strip()
            break
    text = clean_text

    markers = [
        "Revised Draft:",
        "Final Polish:",
        "Text:",
        "*Draft 5:*",
        "*Draft 4:*",
        "Final Output Generation:",
        "Final Answer:",
        "Respuesta final:",
        "Respuesta:",
    ]
    for marker in markers:
        if marker in text:
            candidate = text.split(marker, 1)[1].strip()
            paragraphs = [part.strip(" -*\t") for part in candidate.split("\n\n") if part.strip()]
            for paragraph in paragraphs:
                lower = paragraph.lower()
                if lower.startswith(("wait", "sentence count", "count sentences", "check", "review", "re-reading")):
                    continue
                if len(paragraph) > 80 and any(char in paragraph for char in ".:;"):
                    return paragraph.strip().strip('"')
            lines = [line.strip(" -*\t") for line in candidate.splitlines() if line.strip()]
            useful = [
                line
                for line in lines
                if not line.lower().startswith(("check", "review", "counting", "total", "wait"))
            ]
            if useful:
                return "\n".join(useful[:6]).strip().strip('"')

    if "Thinking Process:" in text:
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        useful = [part for part in paragraphs if not part.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7."))]
        if useful:
            return useful[-1].strip()

    return text.strip()


FINAL_STREAM_MARKERS = [
    "Respuesta final:",
    "Final Answer:",
    "Final Output Generation:",
    "Revised Draft:",
    "Text:",
    "*Draft 5:*",
    "*Draft 4:*",
]

FINAL_STOP_MARKERS = [
    "\n\nWait",
    "\n\n    Wait",
    "\n\nSentence count",
    "\n\nCount sentences",
    "\n\nChecking Constraints",
    "\n\nFinal check",
    "\n\nReview",
]


def find_final_marker(buffer: str) -> tuple[int, str] | None:
    positions = [(buffer.find(marker), marker) for marker in FINAL_STREAM_MARKERS if marker in buffer]
    positions = [(pos, marker) for pos, marker in positions if pos >= 0]
    if not positions:
        return None
    return min(positions, key=lambda item: item[0])


def trim_stream_candidate(text: str) -> tuple[str, bool]:
    for marker in FINAL_STOP_MARKERS:
        index = text.find(marker)
        if index >= 0:
            return text[:index].strip(), True
    return text, False


def iter_clean_lm_studio_stream(payload: dict):
    buffer = ""
    started = False
    marker_text = ""
    sent_length = 0
    completed = False

    for event in iter_lm_studio_stream(payload):
        if event["type"] == "finish":
            break

        delta = event.get("text", "")
        if not delta:
            continue
        buffer += delta

        if not started:
            marker = find_final_marker(buffer)
            if marker is None:
                continue
            marker_position, marker_text = marker
            buffer = buffer[marker_position + len(marker_text):]
            started = True

        candidate, completed = trim_stream_candidate(buffer)
        if len(candidate) > sent_length:
            chunk = candidate[sent_length:]
            sent_length = len(candidate)
            yield {"type": "delta", "text": chunk}

        if completed:
            break

    if sent_length == 0:
        fallback = extract_final_answer(buffer)
        for chunk in chunk_answer(fallback):
            yield {"type": "delta", "text": chunk}

    yield {"type": "finish", "finishReason": "stop"}


def iter_lm_studio_stream(payload: dict):
    config = load_config()
    request = build_lm_studio_request(payload, stream=True)
    timeout = int(config.get("requestTimeoutSeconds", 90))

    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue

            data = line.removeprefix("data:").strip()
            if data == "[DONE]":
                break

            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue

            choices = event.get("choices", [])
            if not choices:
                continue

            finish_reason = choices[0].get("finish_reason")
            if finish_reason:
                yield {"type": "finish", "finishReason": finish_reason}
                continue

            delta = choices[0].get("delta", {})
            content = delta.get("content")
            if content:
                yield {"type": "delta", "text": content}


class LocalHandler(BaseHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self.send_json({"ok": True, "provider": "lmstudio", "config": load_config()})
            return

        if self.path == "/api/dashboard":
            self.send_json(build_dashboard_payload())
            return

        requested_path = self.path.split("?", 1)[0]
        if requested_path in ("", "/"):
            requested_path = "/dashboard.html"

        file_path = (ROOT / requested_path.lstrip("/")).resolve()
        if not str(file_path).startswith(str(ROOT)) or not file_path.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self.send_error(404)
            return

        payload = {}
        try:
            payload = read_json_body(self)
            if payload.get("stream"):
                self.stream_chat(payload)
                return

            trace = build_trace(payload)
            answer = call_lm_studio(payload)
            self.send_json({"answer": answer, "provider": "model", "trace": trace})
        except socket.timeout:
            self.send_json({"error": "El modelo no respondio dentro del tiempo limite."}, status=504)
        except TimeoutError:
            self.send_json({"error": "El modelo no respondio dentro del tiempo limite."}, status=504)
        except urllib.error.URLError as error:
            self.send_json({"error": "No se pudo conectar con el modelo.", "detail": str(error)}, status=502)
        except Exception as error:
            self.send_json({"error": "El modelo fallo al generar la respuesta.", "detail": str(error)}, status=500)

    def stream_chat(self, payload: dict) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        try:
            question = str(payload.get("message", ""))
            use_data = should_use_data_context(question)
            self.write_sse("status", {"label": "Pensando", "detail": "Interpretando la pregunta."})
            if use_data:
                self.write_sse("status", {"label": "Recuperando datos", "detail": "Consultando indicadores relevantes."})
            trace = build_trace(payload)
            self.write_sse("meta", trace)
            detail = "Preparando contexto de respuesta." if use_data else "Preparando respuesta."
            self.write_sse("status", {"label": "Generando respuesta", "detail": detail})
            finish_reason = "stop"
            answer = call_lm_studio(payload)
            self.write_sse("status", {"label": "Redactando", "detail": "Mostrando la respuesta del modelo."})
            for chunk in chunk_answer(answer):
                self.write_sse("delta", {"text": chunk})
                time.sleep(0.018)
            self.write_sse("done", {"ok": True, "finishReason": finish_reason})
        except socket.timeout:
            self.write_sse("error", {"error": "El modelo no respondio dentro del tiempo limite."})
        except TimeoutError:
            self.write_sse("error", {"error": "El modelo no respondio dentro del tiempo limite."})
        except urllib.error.URLError as error:
            self.write_sse("error", {"error": "No se pudo conectar con el modelo.", "detail": str(error)})
        except Exception as error:
            self.write_sse("error", {"error": "El modelo fallo al generar la respuesta.", "detail": str(error)})

    def write_sse(self, event: str, payload: dict) -> None:
        message = f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        self.wfile.write(message.encode("utf-8"))
        self.wfile.flush()

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        sys.stdout.write("%s - %s\n" % (self.address_string(), format % args))


def chunk_answer(text: str, chunk_size: int = 18):
    text = text.strip()
    for start in range(0, len(text), chunk_size):
        yield text[start: start + chunk_size]


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5500
    server = ThreadingHTTPServer(("127.0.0.1", port), LocalHandler)
    print(f"ISEU local server: http://127.0.0.1:{port}")
    print("API chat: /api/chat")
    server.serve_forever()


if __name__ == "__main__":
    main()
