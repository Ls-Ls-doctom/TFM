from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

from sql_data import remote_request


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

SCHEMA_DESCRIPTION = """
Tienes acceso a tres tablas en Amazon Athena (dialecto Trino). Elige la más
apropiada según la pregunta:

━━━ TABLA: indicators (Gold — ciudad, 4 358 filas) ━━━
Usa esta para COMPARAR CIUDADES o pedir resúmenes a nivel ciudad.
Columnas: city varchar, district varchar, variable varchar, value double,
"date" varchar, source varchar, quality_score bigint, category varchar,
unit varchar, year bigint, month bigint
Ciudades: Barcelona, Bilbao, Madrid, Malaga, Sevilla, Valencia, Zaragoza
Variables (nombre en BD → significado en español):
  population_total      → población total
  income                → renta disponible media
  income_median         → renta mediana
  income_per_household  → renta por hogar
  income_per_person     → renta por persona / cápita
  gini_inequality       → desigualdad Gini
  inequality_p80p20     → desigualdad P80/P20
  contracts_registered  → contratos registrados
  job_seekers           → demandantes de empleo
  unemployed_registered → paro registrado
  traffic_accidents     → accidentes de tráfico
  mobility_resources_records → registros de movilidad / bicicletas
district tiene valores como "Eixample", "Gràcia" para Barcelona (puede ser vacío).

━━━ TABLA: indicadores (Silver — barrio/sección censal, 93 944 filas) ━━━
Usa esta para DETALLE SUB-CIUDAD (barrio, sección censal, zona) o cuando
indicators no tenga la variable pedida.
Columnas: source varchar, dataset varchar, variable varchar, metric varchar,
geo varchar (nombre de barrio, sección censal o ciudad), period varchar
(ej. "2023-01-01"), value double, unit varchar, quality varchar, notes varchar
Variables disponibles (nombre en español tal cual en la BD):
  Población total · Renta · Renta bruta · Renta bruta media por hogar ·
  Renta bruta media por persona · Renta disponible · Renta media ·
  Renta media por unidad de consumo · Renta mediana · Renta mediana por
  unidad de consumo · Renta neta media por hogar · Renta neta media por
  persona · Renta por hogar · Renta por persona · Desigualdad Gini ·
  Desigualdad P80/P20 · Contratos registrados · Demandantes de empleo ·
  Paro registrado · Accidentes de trafico · Registros de movilidad ·
  Usuarios bicicleta publica

━━━ TABLA: observations (contexto enriquecido, 105 774 filas) ━━━
Usa esta cuando necesites jerarquía ciudad→distrito→barrio o notas contextuales.
Columnas: city varchar, district varchar, neighborhood varchar, geo varchar,
period varchar, variable varchar, metric varchar, value double, unit varchar,
category varchar, granularity varchar (city|district|neighborhood), notes varchar,
source varchar, quality varchar

Regla de elección:
- Comparar ciudades → indicators  (variables en inglés, usa los nombres exactos)
- Detalle de barrio o zona → indicadores  (variables en español, usa los nombres exactos)
- Jerarquía o notas contextuales → observations
""".strip()

SQL_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "needs_data": {"type": "boolean"},
        "sql": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["needs_data", "sql", "reason"],
}


def answer_with_gemini(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if not GEMINI_API_KEY:
        raise RuntimeError("Falta configurar GEMINI_API_KEY en Vercel.")

    question = str(payload.get("message") or "").strip()
    if not question:
        raise ValueError("La pregunta está vacía.")
    history = compact_history(payload.get("history", []))
    plan = generate_sql_plan(question, history)
    query_result: dict[str, Any] | None = None

    if plan.get("needs_data"):
        sql = str(plan.get("sql") or "").strip()
        if not sql:
            raise RuntimeError("Gemini indicó que necesitaba datos, pero no generó SQL.")
        query_result = remote_request("sql", {"sql": sql})

    answer = generate_final_answer(question, history, plan, query_result)
    trace = {
        "provider": "google",
        "model": GEMINI_MODEL,
        "usesData": bool(plan.get("needs_data")),
        "sql": query_result.get("sql") if query_result else None,
        "rows": query_result.get("rowCount", 0) if query_result else 0,
        "queryRows": (query_result.get("rows", [])[:50] if query_result else []),
        "reason": plan.get("reason", ""),
    }
    return answer, trace


def generate_sql_plan(question: str, history: list[dict[str, str]]) -> dict[str, Any]:
    prompt = f"""
Pregunta actual: {question}

Fecha actual del sistema: {date.today().isoformat()}

Historial reciente:
{format_history(history)}

{SCHEMA_DESCRIPTION}

Decide si la pregunta necesita consultar los datos ISEU.

SIEMPRE needs_data=true si la pregunta:
- Pide valores numéricos (renta, paro, contratos, población, desigualdad, movilidad…)
- Compara ciudades, distritos, barrios o periodos
- Pide rankings, evolución temporal, promedios o totales
- Menciona cualquier variable del esquema aunque sea de forma aproximada
- Pregunta por fuentes disponibles, qué datos hay o qué tablas existen

needs_data=false SOLO para saludos, preguntas sobre la identidad del asistente
o preguntas completamente ajenas a datos urbanos.

Si necesita datos, genera UNA consulta SELECT de Athena usando la tabla más
adecuada del esquema anterior.

Reglas obligatorias:
- Solo SELECT; nunca CTE, JOIN, DDL, DML, comentarios ni punto y coma.
- Usa únicamente las columnas de la tabla elegida.
- Nombra la tabla como indicators, indicadores u observations (sin base de datos).
- Usa comillas dobles para la columna "date" en la tabla indicators.
  En indicadores y observations la columna temporal se llama period (sin comillas).
- Para comparaciones entre ciudades usa indicators; conserva city, variable, value, unit, source, "date".
- Para detalle de barrio usa indicadores; conserva geo, variable, metric, value, unit, period.
- Para notas y jerarquía usa observations; conserva city, district, neighborhood, variable, value, period, notes.
- Athena no admite QUALIFY: no lo uses nunca.
- Para el dato más reciente de varias ciudades en indicators, usa subconsulta con
  row_number() OVER (PARTITION BY city, variable ORDER BY "date" DESC) AS rn.
- Añade LIMIT, máximo 100.
- Si el indicador solicitado no existe en ninguna tabla, consulta el más cercano
  disponible y explícalo en reason.
""".strip()
    return gemini_json(
        system_instruction=(
            "Eres el planificador SQL de ISEU+, asistente del Índice de Salud Económica Urbana. "
            "Produce SQL correcto para Amazon Athena y respeta estrictamente el esquema y las "
            "restricciones de seguridad. Si la pregunta es conversacional o no necesita datos, "
            "devuelve needs_data=false."
        ),
        prompt=prompt,
        schema=SQL_RESPONSE_SCHEMA,
        temperature=0.1,
        max_tokens=700,
    )


def generate_final_answer(
    question: str,
    history: list[dict[str, str]],
    plan: dict[str, Any],
    query_result: dict[str, Any] | None,
) -> str:
    return gemini_text(
        system_instruction=_ANSWER_SYSTEM,
        prompt=_build_answer_prompt(question, history, plan, query_result),
        temperature=0.25,
        max_tokens=900,
    )


def gemini_json(
    system_instruction: str,
    prompt: str,
    schema: dict[str, Any],
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    text = gemini_request(
        system_instruction,
        prompt,
        {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
            "responseJsonSchema": schema,
        },
    )
    try:
        result = json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeError("Gemini no devolvió un plan JSON válido.") from error
    if not isinstance(result, dict):
        raise RuntimeError("Gemini devolvió un plan con formato inesperado.")
    return result


def gemini_text(
    system_instruction: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
) -> str:
    return gemini_request(
        system_instruction,
        prompt,
        {"temperature": temperature, "maxOutputTokens": max_tokens},
    ).strip()


def gemini_request(system_instruction: str, prompt: str, generation_config: dict[str, Any]) -> str:
    body = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }
    encoded_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
    models = list(dict.fromkeys(filter(None, (GEMINI_MODEL, GEMINI_FALLBACK_MODEL))))
    result = None
    last_error: Exception | None = None
    for model_name in models:
        model = urllib.parse.quote(model_name, safe="-._")
        url = f"{GEMINI_BASE_URL}/{model}:generateContent"
        for attempt in range(3):
            request = urllib.request.Request(
                url,
                data=encoded_body,
                headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=40) as response:
                    result = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace")[:1000]
                last_error = RuntimeError(f"Gemini API respondió {error.code}: {detail}")
                if error.code not in {429, 500, 502, 503, 504}:
                    raise last_error from error
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
            except (urllib.error.URLError, TimeoutError) as error:
                last_error = error
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        if result is not None:
            break
    if result is None:
        raise RuntimeError(f"Gemini no estuvo disponible tras los reintentos: {last_error}")
    candidates = result.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini no devolvió candidatos.")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(str(part.get("text") or "") for part in parts).strip()
    if not text:
        raise RuntimeError("Gemini no devolvió texto utilizable.")
    return text


def gemini_stream_text(system_instruction: str, prompt: str, temperature: float, max_tokens: int):
    """Yields text chunks from Gemini streaming API (streamGenerateContent?alt=sse)."""
    model = urllib.parse.quote(GEMINI_MODEL, safe="-._")
    url = f"{GEMINI_BASE_URL}/{model}:streamGenerateContent?alt=sse"
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line.startswith("data:"):
                    continue
                json_str = line[5:].strip()
                try:
                    chunk = json.loads(json_str)
                    for cand in chunk.get("candidates", []):
                        for part in cand.get("content", {}).get("parts", []):
                            text = part.get("text", "")
                            if text:
                                yield text
                except (json.JSONDecodeError, KeyError):
                    continue
    except Exception:
        # On streaming failure, fall back to non-streaming
        yield gemini_text(system_instruction, prompt, temperature, max_tokens)


def _build_answer_prompt(
    question: str,
    history: list[dict[str, str]],
    plan: dict[str, Any],
    query_result: dict[str, Any] | None,
) -> str:
    evidence = {
        "sql": query_result.get("sql") if query_result else None,
        "rows": query_result.get("rows", [])[:100] if query_result else [],
        "row_count": query_result.get("rowCount", 0) if query_result else 0,
        "plan_reason": plan.get("reason", ""),
    }
    return f"""
Pregunta actual: {question}

Historial reciente:
{format_history(history)}

Evidencia recuperada:
{json.dumps(evidence, ensure_ascii=False, separators=(',', ':'))}

Redacta la respuesta final en español. Si hay filas, usa exclusivamente esos
datos para las afirmaciones cuantitativas, menciona territorio, periodo, valor,
unidad y fuente, y distingue claramente cualquier proxy o limitación. Si la
consulta no devuelve filas, dilo con claridad. Si no era necesaria una consulta,
responde de forma conversacional sin inventar que consultaste datos. No muestres
razonamiento interno. No incluyas bloques de código SQL salvo que el usuario los
pida expresamente. No describas una fecha pasada como futura. No afirmes que un
dato es proyección, estimación o previsión salvo que la evidencia lo indique de
forma explícita.
""".strip()


_ANSWER_SYSTEM = (
    "Eres ISEU+, el asistente del Índice de Salud Económica Urbana, un proyecto de "
    "investigación académica sobre ciudades españolas. Tu función es responder sobre "
    "indicadores urbanos de Barcelona, Bilbao, Madrid, Málaga, Sevilla, Valencia y Zaragoza.\n\n"
    "Fuentes de datos disponibles:\n"
    "- INE (Instituto Nacional de Estadística): población total y renta (bruta, disponible, "
    "mediana, por hogar/persona, desigualdad Gini y P80/P20) a nivel de sección censal.\n"
    "- SEPE (Servicio Público de Empleo Estatal): paro registrado, contratos registrados "
    "y demandantes de empleo por ciudad.\n"
    "- Municipal Open Data (Open Data BCN): accidentes de tráfico, registros de movilidad "
    "y usuarios de bicicleta pública.\n"
    "Cobertura temporal: principalmente 2015-2023, según fuente y variable.\n"
    "Total: ~93 944 registros de indicadores en 22 variables.\n\n"
    "Cuando te pregunten quién te creó, responde que eres ISEU+, desarrollado como TFM "
    "de análisis de datos urbanos. No menciones Google, Gemini ni ningún proveedor de IA.\n"
    "Responde siempre en español. Cita fuente, territorio y periodo cuando uses datos. "
    "Nunca inventes indicadores que no existan en la base de datos."
)


def answer_with_gemini_stream(payload: dict[str, Any]):
    """Generator of (event_name, event_data) tuples for SSE streaming response."""
    if not GEMINI_API_KEY:
        raise RuntimeError("Falta configurar GEMINI_API_KEY en Vercel.")
    question = str(payload.get("message") or "").strip()
    if not question:
        raise ValueError("La pregunta está vacía.")
    history = compact_history(payload.get("history", []))

    yield "status", {"label": "Pensando", "detail": "Analizando la consulta."}
    plan = generate_sql_plan(question, history)
    query_result: dict[str, Any] | None = None

    if plan.get("needs_data"):
        sql = str(plan.get("sql") or "").strip()
        if sql:
            yield "status", {"label": "Recuperando datos", "detail": "Consultando Athena."}
            query_result = remote_request("sql", {"sql": sql})

    yield "status", {"label": "Generando respuesta", "detail": "Escribiendo..."}
    prompt = _build_answer_prompt(question, history, plan, query_result)
    for chunk in gemini_stream_text(_ANSWER_SYSTEM, prompt, 0.25, 900):
        yield "delta", {"text": chunk}

    trace = {
        "provider": "google",
        "model": GEMINI_MODEL,
        "usesData": bool(plan.get("needs_data")),
        "sql": query_result.get("sql") if query_result else None,
        "rows": query_result.get("rowCount", 0) if query_result else 0,
        "queryRows": (query_result.get("rows", [])[:50] if query_result else []),
        "reason": plan.get("reason", ""),
    }
    yield "meta", trace
    yield "done", {"finishReason": "stop"}


def compact_history(history: Any) -> list[dict[str, str]]:
    if not isinstance(history, list):
        return []
    result = []
    for item in history[-8:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            result.append({"role": role, "content": content[:1200]})
    return result


def format_history(history: list[dict[str, str]]) -> str:
    if not history:
        return "Sin historial previo."
    labels = {"user": "Usuario", "assistant": "Asistente"}
    return "\n".join(f"{labels[item['role']]}: {item['content']}" for item in history)
