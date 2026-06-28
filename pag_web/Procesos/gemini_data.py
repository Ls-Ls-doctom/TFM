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
Tabla lógica: indicators
Motor SQL: Amazon Athena (dialecto Trino)
Columnas:
- city varchar: Barcelona, Bilbao, Madrid, Malaga, Sevilla, Valencia, Zaragoza
- district double: actualmente nulo; no usar salvo petición explícita
- variable varchar
- value double
- date timestamp; escribir siempre como "date"
- source varchar
- quality_score bigint
- category varchar
- unit varchar
- year bigint
- month bigint

Variables disponibles:
- population_total (demography, persons)
- income, income_median, income_per_household, income_per_person (economy, eur)
- contracts_registered (employment, contracts)
- job_seekers, unemployed_registered (employment, persons)
- mobility_resources_records (mobility, records)
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

Decide si la pregunta necesita consultar los datos ISEU. Si no necesita datos,
devuelve needs_data=false y sql vacío. Si necesita datos, genera UNA consulta
SELECT de Athena sobre la tabla exacta indicators.

Reglas obligatorias:
- Solo SELECT; nunca CTE, JOIN, DDL, DML, comentarios ni punto y coma.
- Usa únicamente las columnas y variables indicadas.
- Cita la tabla como indicators, sin base de datos ni esquema.
- Usa comillas dobles para "date".
- Para comparaciones, conserva city, variable, value, unit, source y "date" en la salida.
- Athena no admite QUALIFY: no lo uses nunca.
- Para una sola ciudad, el dato más reciente se obtiene con ORDER BY "date" DESC LIMIT 1.
- Para el dato más reciente de varias ciudades puedes usar una subconsulta con
  row_number() OVER (PARTITION BY city, variable ORDER BY "date" DESC) AS rn y
  filtrar rn = 1 en la consulta exterior.
- Añade LIMIT, máximo 100.
- Si el indicador solicitado no existe, consulta solo el indicador disponible
  más cercano cuando sea metodológicamente razonable y explícalo en reason.
""".strip()
    return gemini_json(
        system_instruction=(
            "Eres el planificador SQL de ISEU. Produce SQL correcto para Amazon Athena y "
            "respeta estrictamente el esquema y las restricciones de seguridad."
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
    evidence = {
        "sql": query_result.get("sql") if query_result else None,
        "rows": query_result.get("rows", [])[:100] if query_result else [],
        "row_count": query_result.get("rowCount", 0) if query_result else 0,
        "plan_reason": plan.get("reason", ""),
    }
    prompt = f"""
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
    return gemini_text(
        system_instruction=(
            "Eres el asistente ISEU. Respondes con claridad, trazabilidad y prudencia "
            "metodológica. Nunca inventas indicadores ausentes."
        ),
        prompt=prompt,
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
