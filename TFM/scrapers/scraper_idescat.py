"""
Scraper: Idescat (Institut d'Estadística de Catalunya)
API EMEX: https://api.idescat.cat/emex/v1/dades.json

Cubre: PIB/VAB, demografía, esperanza de vida, turismo, vivienda.
Usa la API EMEX que permite consultar por municipio (Barcelona = 080193).
"""
from utils import fetch_json, save_json, save_csv, timestamp

BASE = "https://api.idescat.cat/emex/v1/dades.json"
BCN_ID = "080193"  # Código INE de Barcelona municipio


def get_emex(indicator_id: str) -> dict | None:
    """
    Consulta un indicador EMEX para Barcelona.
    Devuelve valores para: municipio, comarca, Catalunya.
    """
    url = f"{BASE}?id={BCN_ID}&i={indicator_id}"
    print(f"  GET EMEX {indicator_id}")
    data = fetch_json(url)
    if not data or "fitxes" not in data:
        return None

    fitxes = data["fitxes"]
    # Parse columns (Barcelona, Barcelonès, Catalunya)
    cols_raw = fitxes.get("cols", {}).get("col", [])
    if not isinstance(cols_raw, list):
        cols_raw = [cols_raw]
    cols = [c.get("content", "") for c in cols_raw]

    # Parse indicator
    ind_raw = fitxes.get("indicadors", {}).get("i", {})
    if isinstance(ind_raw, list):
        ind_raw = ind_raw[0]

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

    if all_rows:
        save_csv(all_rows, "idescat_raw.csv", "idescat")
        save_json(all_rows, "idescat_raw.json", "idescat")

    save_json({
        "fuente": "Idescat EMEX",
        "municipio": "Barcelona (080193)",
        "timestamp": timestamp(),
        "indicadores_configurados": len(INDICADORES),
        "resultados": resultados,
    }, "idescat_log.json", "idescat")

    ok = sum(1 for v in resultados.values() if v.get("estado") == "OK")
    print(f"\nResumen Idescat: {ok}/{len(INDICADORES)} indicadores extraídos")
    return resultados


if __name__ == "__main__":
    scrape_idescat()
