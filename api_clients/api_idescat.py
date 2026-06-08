"""
Cliente API: Idescat (Institut d'Estadística de Catalunya)
API EMEX: https://api.idescat.cat/emex/v1/dades.json

Cubre: PIB/VAB, demografía, esperanza de vida, turismo, vivienda.
Usa la API EMEX que permite consultar por municipio (Barcelona = 080193).
"""
from utils import fetch_json, save_json, save_csv, timestamp

BASE = "https://api.idescat.cat/emex/v1/dades.json"
_EMEX_CACHE = None


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _load_emex_barcelona() -> dict | None:
    """Carga la ficha completa de Barcelona y la mantiene en memoria."""
    global _EMEX_CACHE
    if _EMEX_CACHE is not None:
        return _EMEX_CACHE

    url = f"{BASE}?id={BCN_ID}"
    print("  GET EMEX ficha Barcelona")
    data = fetch_json(url)
    if not data or "fitxes" not in data:
        return None
    _EMEX_CACHE = data
    return data


def _find_indicator(data: dict, indicator_id: str) -> dict | None:
    """Busca un indicador por id dentro de la respuesta completa EMEX."""
    fitxes = data.get("fitxes", {})
    stack = list(_as_list(fitxes.get("gg", {}).get("g")))

    while stack:
        group = stack.pop()
        if not isinstance(group, dict):
            continue

        stack.extend(_as_list(group.get("gg", {}).get("g")))
        tables = _as_list(group.get("tt", {}).get("t"))
        for table in tables:
            rows = _as_list(table.get("ff", {}).get("f"))
            for row in rows:
                if isinstance(row, dict) and row.get("id") == indicator_id:
                    merged = dict(row)
                    for key in ("r", "s", "updated"):
                        if key not in merged and table.get(key):
                            merged[key] = table.get(key)
                    if "t" not in merged:
                        merged["t"] = {
                            "id": table.get("id", ""),
                            "content": table.get("c", ""),
                        }
                    return merged
    return None


def _discover_all_emex_indicators(data: dict) -> list[dict]:
    """Lista todos los indicadores con valor disponibles en la ficha EMEX."""
    indicators = []
    fitxes = data.get("fitxes", {})
    stack = list(_as_list(fitxes.get("gg", {}).get("g")))

    while stack:
        group = stack.pop()
        if not isinstance(group, dict):
            continue

        stack.extend(_as_list(group.get("gg", {}).get("g")))
        tables = _as_list(group.get("tt", {}).get("t"))
        for table in tables:
            table_name = table.get("c", "")
            rows = _as_list(table.get("ff", {}).get("f"))
            for row in rows:
                if not isinstance(row, dict) or not row.get("id") or not row.get("v"):
                    continue
                indicators.append({
                    "id": row.get("id"),
                    "variable": table_name or row.get("c", ""),
                    "descripcion": row.get("c", "") or table_name or row.get("id"),
                })
    return indicators
BCN_ID = "080193"  # Código INE de Barcelona municipio


def get_emex(indicator_id: str) -> dict | None:
    """
    Consulta un indicador EMEX para Barcelona.
    Devuelve valores para: municipio, comarca, Catalunya.
    """
    print(f"  GET EMEX {indicator_id}")
    data = _load_emex_barcelona()
    if not data or "fitxes" not in data:
        return None

    fitxes = data["fitxes"]
    # Parse columns (Barcelona, Barcelonès, Catalunya)
    cols_raw = fitxes.get("cols", {}).get("col", [])
    if not isinstance(cols_raw, list):
        cols_raw = [cols_raw]
    cols = [c.get("content", "") for c in cols_raw]

    # Idescat currently returns an empty body for id+i in this endpoint.
    # We fetch the municipal sheet once and extract the indicator locally.
    ind_raw = _find_indicator(data, indicator_id)
    if not ind_raw:
        return None

    name = ind_raw.get("c", "")
    values_str = ind_raw.get("v", "")
    ref = ind_raw.get("r", "")
    source = ind_raw.get("s", "")
    updated = ind_raw.get("updated", "")

    # Parse comma-separated values
    values = values_str.split(",") if values_str else []

    return {
        "indicador_id": indicator_id,
        "nombre": name,
        "valores_raw": values_str,
        "barcelona": values[0] if len(values) > 0 else None,
        "comarca": values[1] if len(values) > 1 else None,
        "catalunya": values[2] if len(values) > 2 else None,
        "columnas": cols,
        "referencia": ref,
        "fuente_idescat": source,
        "actualizado": updated,
        "extraido_en": timestamp(),
    }


# =====================================================
# Indicadores EMEX para Barcelona
# =====================================================
INDICADORES = {
    # --- Demografía ---
    "poblacion": {
        "id": "f171",
        "variable": "Población",
        "descripcion": "Población total de Barcelona",
    },
    "crecimiento_poblacion": {
        "id": "f53",
        "variable": "Crecimiento población",
        "descripcion": "Crecimiento total de la población (‰)",
    },

    # --- Economía (VAB como proxy PIB municipal) ---
    "vab_servicios": {
        "id": "f197",
        "variable": "PIB regional",
        "descripcion": "VAB servicios (M€) – proxy actividad económica",
    },
    "vab_industria": {
        "id": "f195",
        "variable": "Dinamismo económico",
        "descripcion": "VAB industria (M€)",
    },
    "vab_construccion": {
        "id": "f196",
        "variable": "Dinamismo económico",
        "descripcion": "VAB construcción (M€)",
    },
    "vab_comercio": {
        "id": "f209",
        "variable": "Ventas retail",
        "descripcion": "VAB comercio (M€)",
    },
    "vab_hostaleria": {
        "id": "f210",
        "variable": "Turismo (nº visitantes)",
        "descripcion": "VAB hostelería (M€)",
    },

    # --- Turismo ---
    "hoteles": {
        "id": "f215",
        "variable": "Ocupación hotelera",
        "descripcion": "Número de hoteles en Barcelona",
    },
    "plazas_hotel": {
        "id": "f216",
        "variable": "Ocupación hotelera",
        "descripcion": "Plazas hoteleras en Barcelona",
    },

    # --- Vivienda ---
    "viviendas_principales": {
        "id": "f193",
        "variable": "Ratio vivienda / ingresos",
        "descripcion": "Viviendas familiares principales",
    },

    # --- Fiscal ---
    "ibi_cuota": {
        "id": "f200",
        "variable": "Presión fiscal",
        "descripcion": "IBI cuota íntegra (€) – indicador presión fiscal",
    },
    "ibi_recibos": {
        "id": "f198",
        "variable": "Presión fiscal",
        "descripcion": "IBI recibos – número de contribuyentes",
    },

    # --- Actividades/equipamientos ---
    "espacios_deportivos": {
        "id": "f300",
        "variable": "Accesibilidad y bienestar",
        "descripcion": "Espacios deportivos",
    },
}

INDICADORES.update(
    {
        # --- Expansion ISEU: territorio y demografia ---
        "superficie": {
            "id": "f271",
            "variable": "Superficie municipal",
            "descripcion": "Superficie municipal",
        },
        "densidad_poblacion": {
            "id": "f262",
            "variable": "Densidad poblacion",
            "descripcion": "Densidad de poblacion",
        },
        "poblacion_hombres": {
            "id": "f318",
            "variable": "Poblacion por sexo",
            "descripcion": "Poblacion masculina",
        },
        "poblacion_mujeres": {
            "id": "f320",
            "variable": "Poblacion por sexo",
            "descripcion": "Poblacion femenina",
        },
        "poblacion_0_14": {
            "id": "f167",
            "variable": "Poblacion por edad",
            "descripcion": "Poblacion de 0 a 14 anos",
        },
        "poblacion_15_64": {
            "id": "f27",
            "variable": "Poblacion por edad",
            "descripcion": "Poblacion de 15 a 64 anos",
        },
        "poblacion_65_84": {
            "id": "f28",
            "variable": "Poblacion por edad",
            "descripcion": "Poblacion de 65 a 84 anos",
        },
        "poblacion_85_mas": {
            "id": "f29",
            "variable": "Poblacion por edad",
            "descripcion": "Poblacion de 85 anos y mas",
        },
        "nacimientos": {
            "id": "f187",
            "variable": "Nacimientos",
            "descripcion": "Nacimientos totales",
        },
        "defunciones": {
            "id": "f188",
            "variable": "Defunciones",
            "descripcion": "Defunciones totales",
        },
        "crecimiento_natural": {
            "id": "f54",
            "variable": "Crecimiento poblacion",
            "descripcion": "Crecimiento natural",
        },
        "crecimiento_migratorio": {
            "id": "f55",
            "variable": "Crecimiento poblacion",
            "descripcion": "Crecimiento migratorio",
        },
        "inmigraciones_externas": {
            "id": "f372",
            "variable": "Migraciones externas",
            "descripcion": "Inmigraciones externas",
        },
        "emigraciones_externas": {
            "id": "f373",
            "variable": "Migraciones externas",
            "descripcion": "Emigraciones externas",
        },
        "hogares_total": {
            "id": "f107",
            "variable": "Hogares",
            "descripcion": "Hogares totales",
        },
        "hogares_unipersonales": {
            "id": "f98",
            "variable": "Hogares",
            "descripcion": "Hogares de una persona",
        },
        # --- Expansion ISEU: empleo y actividad ---
        "poblacion_ocupada": {
            "id": "f221",
            "variable": "Poblacion ocupada",
            "descripcion": "Poblacion ocupada",
        },
        "poblacion_desocupada": {
            "id": "f222",
            "variable": "Poblacion desocupada",
            "descripcion": "Poblacion desocupada",
        },
        "poblacion_activa": {
            "id": "f223",
            "variable": "Poblacion activa",
            "descripcion": "Poblacion activa",
        },
        "afiliados_residencia": {
            "id": "f377",
            "variable": "Afiliacion Seguridad Social",
            "descripcion": "Afiliados a la Seguridad Social segun residencia",
        },
        "afiliaciones_total": {
            "id": "f363",
            "variable": "Afiliacion Seguridad Social",
            "descripcion": "Afiliaciones a la Seguridad Social",
        },
        "afiliaciones_servicios": {
            "id": "f280",
            "variable": "Afiliacion por sector",
            "descripcion": "Afiliaciones regimen general sector servicios",
        },
        "afiliaciones_industria": {
            "id": "f278",
            "variable": "Afiliacion por sector",
            "descripcion": "Afiliaciones regimen general sector industria",
        },
        "afiliaciones_construccion": {
            "id": "f279",
            "variable": "Afiliacion por sector",
            "descripcion": "Afiliaciones regimen general sector construccion",
        },
        # --- Expansion ISEU: bienestar ---
        "nivel_educacion_superior": {
            "id": "f389",
            "variable": "Nivel educativo",
            "descripcion": "Poblacion con educacion superior",
        },
        "nivel_educacion_primaria": {
            "id": "f386",
            "variable": "Nivel educativo",
            "descripcion": "Poblacion con educacion primaria o inferior",
        },
    }
)


def scrape_idescat():
    """Ejecuta la extracción de datos de Idescat EMEX para Barcelona."""
    print(f"\n{'='*60}")
    print(f"SCRAPER IDESCAT (EMEX Barcelona) - {timestamp()}")
    print(f"{'='*60}")

    all_rows = []
    resultados = {}

    for key, cfg in INDICADORES.items():
        print(f"\n[{key}] {cfg['descripcion']}")
        result = get_emex(cfg["id"])
        if result and result["nombre"] and "no trobat" not in result["nombre"]:
            result["variable_iseu"] = cfg["variable"]
            result["clave_config"] = key
            all_rows.append(result)
            resultados[key] = {
                "estado": "OK",
                "nombre": result["nombre"],
                "barcelona": result["barcelona"],
                "referencia": result["referencia"],
            }
            print(f"  ✓ {result['nombre']} = {result['barcelona']} ({result['referencia']})")
        else:
            resultados[key] = {"estado": "ERROR"}
            print(f"  ✗ Sin datos")

    data = _load_emex_barcelona()
    configured_ids = {cfg["id"] for cfg in INDICADORES.values()}
    if data:
        auto_indicators = [
            item for item in _discover_all_emex_indicators(data)
            if item["id"] not in configured_ids
        ]
        for item in auto_indicators:
            key = f"emex_auto_{item['id']}"
            print(f"\n[{key}] {item['descripcion']}")
            result = get_emex(item["id"])
            if result and result["nombre"] and "no trobat" not in result["nombre"]:
                result["variable_iseu"] = item["variable"]
                result["clave_config"] = key
                all_rows.append(result)
                resultados[key] = {
                    "estado": "OK",
                    "nombre": result["nombre"],
                    "barcelona": result["barcelona"],
                    "referencia": result["referencia"],
                }
                print(f"  OK {result['nombre']} = {result['barcelona']} ({result['referencia']})")
            else:
                resultados[key] = {"estado": "ERROR"}
                print("  Sin datos")

    if all_rows:
        save_csv(all_rows, "idescat_raw.csv", "idescat")
        save_json(all_rows, "idescat_raw.json", "idescat")

    save_json({
        "fuente": "Idescat EMEX",
        "municipio": "Barcelona (080193)",
        "timestamp": timestamp(),
        "indicadores_configurados": len(INDICADORES),
        "indicadores_totales_intentados": len(resultados),
        "resultados": resultados,
    }, "idescat_log.json", "idescat")

    ok = sum(1 for v in resultados.values() if v.get("estado") == "OK")
    print(f"\nResumen Idescat: {ok}/{len(resultados)} indicadores extraídos")
    return resultados


if __name__ == "__main__":
    scrape_idescat()
