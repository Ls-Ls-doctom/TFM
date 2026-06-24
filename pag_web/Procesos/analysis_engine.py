from __future__ import annotations

from typing import Any

import pandas as pd

from sql_data import fetch_series

DB_LABEL = "pag_web\\Procesos\\Datasets\\iseu_datos.sqlite"


ANALYSIS_TRIGGERS = [
    "analiza",
    "analisis",
    "auge",
    "baja",
    "basas",
    "calcula",
    "compara",
    "datos",
    "dataset",
    "evolucion",
    "evolución",
    "justifica",
    "por que",
    "por qué",
    "razon",
    "razón",
    "segun",
    "según",
    "sube",
    "tendencia",
    "variacion",
    "variación",
]


def should_analyze(question: str) -> bool:
    normalized = normalize(question)
    return any(trigger in normalized for trigger in ANALYSIS_TRIGGERS)


def analyze_question(question: str) -> dict[str, Any] | None:
    if not should_analyze(question):
        return None

    normalized = normalize(question)
    analyses: list[dict[str, Any]] = []

    if has_any(normalized, ["paro", "desempleo", "empleo", "trabajo", "laboral"]):
        analyses.append(analyze_ine_series("tasa_paro_cataluna", "empleo"))
        analyses.append(analyze_ine_series("tasa_empleo_cataluna", "empleo"))

    if has_any(normalized, ["ipc", "inflacion", "inflación", "coste", "vida", "precio"]):
        analyses.append(analyze_ine_series("ipc_general_espana", "coste de vida"))
        analyses.append(analyze_ine_series("ipc_alimentos_espana", "coste de vida"))

    if has_any(normalized, ["energia", "energía", "electricidad", "luz", "demanda", "consumo"]):
        analyses.append(analyze_ree_prices())
        analyses.append(analyze_ree_demand())

    if has_any(normalized, ["poblacion", "población", "habitantes", "demografia", "demografía"]):
        analyses.append(analyze_idescat_row("poblacion", "poblacion"))

    analyses = [analysis for analysis in analyses if analysis.get("estado") != "sin_datos"]
    if not analyses:
        return {
            "activado": True,
            "motivo": "La pregunta pide datos o justificacion, pero no se encontro un analizador especifico.",
            "analisis": [],
        }

    return {
        "activado": True,
        "motivo": "Analisis bajo demanda activado por la pregunta del usuario.",
        "analisis": analyses,
    }


def analyze_ine_series(clave_config: str, tema: str) -> dict[str, Any]:
    rows = fetch_series(dataset=clave_config)
    filtered = pd.DataFrame(rows)
    if filtered.empty:
        return missing(tema, clave_config)

    filtered["fecha_parseada"] = pd.to_datetime(filtered["period"], errors="coerce")
    filtered["valor_num"] = pd.to_numeric(filtered["value"], errors="coerce")
    filtered = filtered.dropna(subset=["fecha_parseada", "valor_num"]).sort_values("fecha_parseada")
    if filtered.empty:
        return missing(tema, clave_config)

    latest = filtered.iloc[-1]
    previous = filtered.iloc[-2] if len(filtered) > 1 else latest
    first = filtered.iloc[0]
    diff_previous = float(latest["valor_num"] - previous["valor_num"])
    diff_first = float(latest["valor_num"] - first["valor_num"])
    quality = assess_ine_quality(clave_config, safe_value(latest.get("metric")))

    return {
        "estado": "ok",
        "tema": tema,
        "variable": clave_config,
        "fuente": "INE",
        "archivo": DB_LABEL,
        "nombre_serie": safe_value(latest.get("metric")),
        "calidad": quality["calidad"],
        "advertencias": quality["advertencias"],
        "periodos_analizados": int(len(filtered)),
        "primer_periodo": date_text(first["fecha_parseada"]),
        "primer_valor": round_float(first["valor_num"]),
        "periodo_anterior": date_text(previous["fecha_parseada"]),
        "valor_anterior": round_float(previous["valor_num"]),
        "ultimo_periodo": date_text(latest["fecha_parseada"]),
        "ultimo_valor": round_float(latest["valor_num"]),
        "variacion_vs_anterior": round_float(diff_previous),
        "variacion_desde_inicio": round_float(diff_first),
        "tendencia_reciente": classify_trend(diff_previous),
        "tendencia_serie": classify_trend(diff_first),
        "limite": "Puede ser proxy territorial si la serie no es municipal de Barcelona.",
    }


def analyze_ree_prices() -> dict[str, Any]:
    df = pd.DataFrame(fetch_series(dataset="ree_precios"))
    if df.empty:
        return missing("energia", "precio electricidad")

    df["fecha_parseada"] = pd.to_datetime(df["period"], errors="coerce")
    df["valor_num"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["fecha_parseada", "valor_num"]).sort_values("fecha_parseada")
    if df.empty:
        return missing("energia", "precio electricidad")

    daily = df.groupby(df["fecha_parseada"].dt.date)["valor_num"].mean().reset_index()
    first = daily.iloc[0]
    latest = daily.iloc[-1]
    diff = float(latest["valor_num"] - first["valor_num"])

    return {
        "estado": "ok",
        "tema": "energia",
        "variable": "precio electricidad",
        "fuente": "REE",
        "archivo": DB_LABEL,
        "periodos_analizados": int(len(daily)),
        "primer_periodo": str(first["fecha_parseada"]),
        "primer_valor_medio_eur_mwh": round_float(first["valor_num"]),
        "ultimo_periodo": str(latest["fecha_parseada"]),
        "ultimo_valor_medio_eur_mwh": round_float(latest["valor_num"]),
        "variacion_desde_inicio": round_float(diff),
        "tendencia_serie": classify_trend(diff),
        "limite": "Serie horaria agregada a media diaria para reducir ruido.",
    }


def analyze_ree_demand() -> dict[str, Any]:
    df = pd.DataFrame(fetch_series(dataset="ree_demanda"))
    if df.empty:
        return missing("energia", "demanda electrica")

    df["fecha_parseada"] = pd.to_datetime(df["period"], errors="coerce")
    df["valor_num"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["fecha_parseada", "valor_num"]).sort_values("fecha_parseada")
    if df.empty:
        return missing("energia", "demanda electrica")

    latest = df.iloc[-1]
    previous = df.iloc[-2] if len(df) > 1 else latest
    diff = float(latest["valor_num"] - previous["valor_num"])

    return {
        "estado": "ok",
        "tema": "energia",
        "variable": "demanda electrica",
        "fuente": "REE",
        "archivo": DB_LABEL,
        "periodos_analizados": int(len(df)),
        "periodo_anterior": date_text(previous["fecha_parseada"]),
        "valor_anterior_mwh": round_float(previous["valor_num"]),
        "ultimo_periodo": date_text(latest["fecha_parseada"]),
        "ultimo_valor_mwh": round_float(latest["valor_num"]),
        "variacion_vs_anterior": round_float(diff),
        "tendencia_reciente": classify_trend(diff),
    }


def analyze_idescat_row(clave_config: str, tema: str) -> dict[str, Any]:
    filtered = pd.DataFrame(fetch_series(dataset=clave_config, limit=20))
    if filtered.empty:
        return missing(tema, clave_config)

    row = filtered.iloc[0]
    return {
        "estado": "ok",
        "tema": tema,
        "variable": clave_config,
        "fuente": "Idescat",
        "archivo": DB_LABEL,
        "nombre": safe_value(row.get("metric")),
        "barcelona": safe_value(row.get("value")),
        "comarca": "",
        "catalunya": "",
        "referencia": safe_value(row.get("period")),
        "actualizado": safe_value(row.get("extracted_at")),
        "limite": "Dato descriptivo: no calcula tendencia si solo hay una fila agregada.",
    }


def normalize(text: str) -> str:
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
    }
    normalized = text.lower()
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return normalized


def has_any(text: str, keywords: list[str]) -> bool:
    normalized_keywords = [normalize(keyword) for keyword in keywords]
    return any(keyword in text for keyword in normalized_keywords)


def classify_trend(diff: float, epsilon: float = 0.01) -> str:
    if diff > epsilon:
        return "sube"
    if diff < -epsilon:
        return "baja"
    return "estable"


def round_float(value: Any) -> float:
    return round(float(value), 3)


def date_text(value: Any) -> str:
    return pd.Timestamp(value).date().isoformat()


def missing(tema: str, variable: str) -> dict[str, Any]:
    return {
        "estado": "sin_datos",
        "tema": tema,
        "variable": variable,
        "archivo": DB_LABEL,
    }


def safe_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def assess_ine_quality(clave_config: str, series_name: str) -> dict[str, Any]:
    normalized_name = normalize(series_name)
    warnings = []

    if clave_config == "tasa_paro_cataluna":
        if "inactivos" in normalized_name:
            warnings.append(
                "La clave local se llama tasa_paro_cataluna, pero el nombre INE de la serie indica 'Inactivos', no tasa de paro."
            )
        if "personas" in normalized_name and "tasa" not in normalized_name:
            warnings.append("La unidad aparente son personas, no porcentaje de tasa.")

    if clave_config == "tasa_empleo_cataluna":
        if "tasa" not in normalized_name and "empleo" not in normalized_name and "ocupados" not in normalized_name:
            warnings.append("La clave local sugiere empleo, pero el nombre INE no confirma claramente que sea tasa de empleo.")

    return {
        "calidad": "baja" if warnings else "media",
        "advertencias": warnings,
    }
