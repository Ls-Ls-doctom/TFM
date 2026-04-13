"""
Scraper: INE (Instituto Nacional de Estadística)
API: https://servicios.ine.es/wstempus/js/ES

Cubre: IPC, salarios, EPA (paro/empleo), empresas, comercio, turismo, etc.
Documentación: https://www.ine.es/dyngs/DataLab/manual.html?cid=1259945948443
"""
from utils import fetch_json, save_json, save_csv, timestamp

BASE = "https://servicios.ine.es/wstempus/js/ES"


def get_serie(serie_id: str, nult: int = 24) -> list[dict]:
    """Fetch últimos N datos de una serie temporal del INE."""
    url = f"{BASE}/DATOS_SERIE/{serie_id}?nult={nult}"
    print(f"  GET {url}")
    try:
        data = fetch_json(url)
    except Exception as exc:
        print(f"  ⚠ Error parseando respuesta para {serie_id}: {exc}")
        return []
    if not data:
        print(f"  ⚠ Sin datos para serie {serie_id}")
        return []
    # La API puede devolver un dict con "Data" o directamente una lista
    if isinstance(data, dict) and "Data" in data:
        entries = data["Data"]
        nombre = data.get("Nombre", "")
        unidad = data.get("Unidad", {})
        if isinstance(unidad, dict):
            unidad = unidad.get("Nombre", "")
    elif isinstance(data, list):
        entries = data
        nombre = ""
        unidad = ""
    else:
        print(f"  ⚠ Formato inesperado para serie {serie_id}")
        return []

    rows = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rows.append({
            "serie_id": serie_id,
            "fecha": entry.get("Fecha", entry.get("fecha", "")),
            "valor": entry.get("Valor", entry.get("valor", None)),
            "nombre": nombre,
            "unidad": unidad,
            "extraido_en": timestamp(),
        })
    return rows


# =====================================================
# Mapeo de series INE relevantes para Barcelona / Cataluña / España
# =====================================================
# Las series se identifican por su código COD en INEbase.
# Cuando no existe dato municipal de Barcelona, se usa Cataluña o provincia.

SERIES = {
    # --- IPC ---
    "ipc_general_barcelona": {
        "serie": "IPC251852",  # IPC general, provincia Barcelona
        "variable": "Índice general IPC",
        "descripcion": "IPC general mensual, provincia de Barcelona",
    },
    "ipc_alimentos_barcelona": {
        "serie": "IPC251856",  # IPC alimentos
        "variable": "Inflación alimentaria",
        "descripcion": "IPC alimentos y bebidas no alcohólicas, Barcelona",
    },

    # --- Salarios ---
    "salario_medio_cataluna": {
        "serie": "EES20190",  # Encuesta estructura salarial - Cataluña
        "variable": "Salario medio bruto",
        "descripcion": "Salario medio bruto anual, Cataluña",
    },

    # --- EPA (Encuesta Población Activa) ---
    "tasa_paro_cataluna": {
        "serie": "EPA137904",  # Tasa de paro Cataluña
        "variable": "Tasa de paro",
        "descripcion": "Tasa de paro EPA, Cataluña, trimestral",
    },
    "tasa_empleo_cataluna": {
        "serie": "EPA137916",  # Tasa de empleo Cataluña
        "variable": "Tasa de empleo",
        "descripcion": "Tasa de empleo EPA, Cataluña, trimestral",
    },

    # --- Comercio ---
    "ventas_retail_cataluna": {
        "serie": "ICM38708",  # Índice comercio minorista Cataluña
        "variable": "Ventas retail",
        "descripcion": "Índice de comercio al por menor, Cataluña",
    },

    # --- Turismo ---
    "ocupacion_hotelera_barcelona": {
        "serie": "EOH11620",  # Grado ocupación Barcelona
        "variable": "Ocupación hotelera",
        "descripcion": "Grado de ocupación hotelera, Barcelona provincia",
    },

    # --- Empresas ---
    "creacion_empresas_barcelona": {
        "serie": "DIRCE3680",  # Empresas creadas Barcelona
        "variable": "Creación de empresas",
        "descripcion": "Empresas creadas, provincia de Barcelona",
    },
}


def scrape_ine():
    """Ejecuta todas las extracciones INE configuradas."""
    print(f"\n{'='*60}")
    print(f"SCRAPER INE - {timestamp()}")
    print(f"{'='*60}")

    all_rows = []
    resultados = {}

    for key, cfg in SERIES.items():
        print(f"\n[{key}] {cfg['descripcion']}")
        rows = get_serie(cfg["serie"])
        if rows:
            # Añadir metadatos del catálogo
            for r in rows:
                r["variable_iseu"] = cfg["variable"]
                r["clave_config"] = key
            all_rows.extend(rows)
            resultados[key] = {"estado": "OK", "filas": len(rows)}
            print(f"  ✓ {len(rows)} registros")
        else:
            resultados[key] = {"estado": "ERROR", "filas": 0}
            print(f"  ✗ Sin datos")

    # Guardar datos
    if all_rows:
        save_csv(all_rows, "ine_raw.csv", "ine")
        save_json(all_rows, "ine_raw.json", "ine")

    # Guardar log
    save_json({
        "fuente": "INE",
        "timestamp": timestamp(),
        "series_configuradas": len(SERIES),
        "resultados": resultados,
    }, "ine_log.json", "ine")

    ok = sum(1 for v in resultados.values() if v["estado"] == "OK")
    print(f"\nResumen INE: {ok}/{len(SERIES)} series extraídas correctamente")
    return resultados


if __name__ == "__main__":
    scrape_ine()
