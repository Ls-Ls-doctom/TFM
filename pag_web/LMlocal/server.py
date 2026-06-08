from __future__ import annotations

import csv
import json
import mimetypes
import socket
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
LOCAL_DIR = Path(__file__).resolve().parent
CONFIG_PATH = LOCAL_DIR / "config.json"
SYSTEM_PROMPT_PATH = LOCAL_DIR / "system_prompt.txt"
PROCESOS_DIR = ROOT / "Procesos"

sys.path.insert(0, str(PROCESOS_DIR))

from analysis_engine import analyze_question, should_analyze
from sql_data import DB_PATH, fetch_catalog_summary, fetch_relevant_indicators, normalize


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
        "/no_think\n"
        "Responde solo con la respuesta final en espanol, sin mostrar razonamiento interno ni pasos de pensamiento.\n"
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

    return {
        "instruccion": "Usa estos indicadores consultados desde SQLite como evidencia. Cita fuente, variable, territorio, periodo, unidad y calidad cuando sea posible. No inventes datos que no aparezcan aqui.",
        "pregunta": question,
        "database": "Base de datos",
        "database_ready": sql_payload["ready"],
        "terminos_busqueda": sql_payload["terms"],
        "indicadores": compact_indicator_rows(sql_payload["rows"]),
        "catalogo": compact_catalog_summary(sql_payload["summary"]),
        "log": log,
    }


def compact_indicator_rows(rows: list[dict]) -> list[dict]:
    keys = ("source", "dataset", "variable", "metric", "geo", "period", "value", "unit", "quality", "score")
    return [{key: row.get(key) for key in keys if key in row} for row in rows[:8]]


def compact_catalog_summary(summary: dict) -> dict:
    sources = summary.get("sources", [])
    variables = summary.get("variables", [])
    return {
        "database": "Base de datos",
        "ready": summary.get("ready"),
        "source_count": len(sources),
        "variable_count": len(variables),
        "sources": sources,
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
        "model": "ISEU Assistant",
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
            "detailRows": int(sqlite_report.get("detail_rows_loaded") or 0),
        },
        "sources": sources,
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
    numeric_rows = []

    for row in rows:
        value = row.get("value")
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            numeric_value = None

        geo = str(row.get("geo") or "").strip()
        variable = str(row.get("variable") or row.get("dataset") or "Indicador").strip()
        period = str(row.get("period") or "").strip()
        unit = str(row.get("unit") or "").strip()
        source = str(row.get("source") or "").strip()
        label = f"{variable} · {geo}" if geo else variable
        display_value = format_metric_value(value, unit)
        status = f"{period} · {row.get('quality', 'calidad n/d')}".strip(" ·")

        table.append([label, display_value, source, status])
        if numeric_value is not None:
            numeric_rows.append((label, numeric_value))

    max_abs = max((abs(value) for _, value in numeric_rows), default=0)
    chart = []
    for label, value in numeric_rows[:8]:
        percent = 0 if max_abs == 0 else round((abs(value) / max_abs) * 100)
        chart.append([label[:46], max(4, min(100, percent)), format_metric_value(value, "")])

    sources = sorted({str(row.get("source")) for row in rows if row.get("source")})
    return {
        "label": "Datos SQL",
        "title": "Indicadores recuperados",
        "summary": f"Vista generada para: {question}",
        "source": " / ".join(sources) if sources else "Base de datos activa",
        "confidence": infer_visual_confidence(rows),
        "table": table[:10],
        "chart": chart,
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
    return f"{text} {unit}".strip()


def infer_visual_confidence(rows: list[dict]) -> str:
    qualities = [str(row.get("quality") or "").lower() for row in rows]
    if qualities and all(quality == "alta" for quality in qualities):
        return "Alta"
    if any(quality == "alta" for quality in qualities):
        return "Media-alta"
    return "Media"


def build_lm_studio_request(payload: dict, stream: bool = False) -> urllib.request.Request:
    config = load_config()
    base_url = config["lmStudioBaseUrl"].rstrip("/")
    url = f"{base_url}/v1/chat/completions"
    body = {
        "model": config["model"],
        "temperature": config.get("temperature", 0.3),
        "max_tokens": config.get("maxTokens", 700),
        "stream": stream,
        "messages": [
            {"role": "system", "content": load_system_prompt()},
            {"role": "user", "content": build_user_content(payload)},
        ],
    }

    return urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
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
    request = build_lm_studio_request(payload, stream=False)

    timeout = int(load_config().get("requestTimeoutSeconds", 90))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response_body = json.loads(response.read().decode("utf-8"))

    choices = response_body.get("choices", [])
    if choices:
        message = choices[0].get("message", {})
        content = message.get("content", "").strip()
        if content:
            return ensure_user_facing_answer(payload, content)

    raise RuntimeError("El asistente no devolvio una respuesta final util.")


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
    return build_local_fallback_answer(payload)


def build_local_fallback_answer(payload: dict) -> str:
    question = str(payload.get("message", "")).strip()
    if not should_use_data_context(question):
        return "Hola. Soy ISEU Assistant. Puedo ayudarte a revisar el dashboard, explicar fuentes y responder preguntas sobre los indicadores urbanos cargados."

    data = build_data_payload(question)
    rows = data.get("indicadores", [])[:4]
    if not rows:
        return "No he encontrado indicadores suficientes para responder esa pregunta con datos. Prueba a preguntar por empleo, vivienda, coste de vida, energia, poblacion o fuentes disponibles."

    lines = [
        "He recuperado indicadores relacionados con tu pregunta. Estos son los mas relevantes:"
    ]
    for row in rows:
        value = format_metric_value(row.get("value"), str(row.get("unit") or ""))
        lines.append(
            f"- {row.get('source', 'Fuente n/d')}: {row.get('variable', 'Variable n/d')} en {row.get('geo', 'territorio n/d')} ({row.get('period', 'periodo n/d')}): {value}."
        )
    lines.append("Usa la vista de tablas o graficos para revisar la trazabilidad completa.")
    return "\n".join(lines)


def call_lm_studio_final(payload: dict) -> str:
    config = load_config()
    base_url = config["lmStudioBaseUrl"].rstrip("/")
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
        final_input = f"Pregunta: {question}\nDatos recuperados desde SQLite:\n{facts}\nRespuesta final:"
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
        headers={"Content-Type": "application/json"},
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

        try:
            payload = read_json_body(self)
            if payload.get("stream"):
                self.stream_chat(payload)
                return

            trace = build_trace(payload)
            question = str(payload.get("message", ""))
            memory_answer = answer_memory_question(question, compact_history(payload.get("history", [])))
            answer = memory_answer or call_lm_studio(payload)
            self.send_json({"answer": answer, "provider": "lmstudio", "trace": trace})
        except socket.timeout:
            self.send_json(
                {
                    "error": "El asistente ha tardado demasiado en responder.",
                    "detail": "Prueba de nuevo en unos segundos o revisa que el servicio de respuesta este activo.",
                },
                status=504,
            )
        except TimeoutError:
            self.send_json(
                {
                    "error": "El asistente ha tardado demasiado en responder.",
                    "detail": "Prueba de nuevo en unos segundos o revisa que el servicio de respuesta este activo.",
                },
                status=504,
            )
        except urllib.error.URLError as error:
            detail = str(error)
            if isinstance(error, urllib.error.HTTPError):
                try:
                    detail = error.read().decode("utf-8", errors="replace")
                except OSError:
                    detail = str(error)
            self.send_json(
                {
                    "error": "No se pudo conectar con el asistente.",
                    "detail": detail,
                },
                status=502,
            )
        except Exception as error:
            self.send_json({"error": "Error generando la respuesta local.", "detail": str(error)}, status=500)

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
            started_answer = False
            memory_answer = answer_memory_question(question, compact_history(payload.get("history", [])))
            if memory_answer:
                self.write_sse("status", {"label": "Redactando", "detail": "Mostrando la respuesta final."})
                for chunk in chunk_answer(memory_answer):
                    self.write_sse("delta", {"text": chunk})
                    time.sleep(0.018)
                started_answer = True
            else:
                answer = call_lm_studio(payload)
                self.write_sse("status", {"label": "Redactando", "detail": "Mostrando la respuesta final."})
                for chunk in chunk_answer(answer):
                    self.write_sse("delta", {"text": chunk})
                    time.sleep(0.018)
                started_answer = True

            if not started_answer:
                answer = call_lm_studio(payload)
                self.write_sse("status", {"label": "Redactando", "detail": "Mostrando la respuesta final."})
                for chunk in chunk_answer(answer):
                    self.write_sse("delta", {"text": chunk})
                    time.sleep(0.018)
            self.write_sse("done", {"ok": True, "finishReason": finish_reason})
        except socket.timeout:
            self.write_sse("error", {"error": "El asistente ha tardado demasiado en responder."})
        except TimeoutError:
            self.write_sse("error", {"error": "El asistente ha tardado demasiado en responder."})
        except urllib.error.URLError as error:
            detail = str(error)
            if isinstance(error, urllib.error.HTTPError):
                try:
                    detail = error.read().decode("utf-8", errors="replace")
                except OSError:
                    detail = str(error)
            self.write_sse("error", {"error": "No se pudo conectar con el asistente.", "detail": detail})
        except Exception as error:
            self.write_sse("error", {"error": "Error generando la respuesta local.", "detail": str(error)})

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
