"""
Cliente API: INE (Instituto Nacional de EstadÃ­stica)
API: https://servicios.ine.es/wstempus/js/ES

Cubre: IPC, salarios, EPA (paro/empleo), empresas, comercio, turismo, etc.
DocumentaciÃ³n: https://www.ine.es/dyngs/DataLab/manual.html?cid=1259945948443
"""
from utils import fetch_json, save_json, save_csv, timestamp
from config import INE_NULT

BASE = "https://servicios.ine.es/wstempus/js/ES"


def get_serie(serie_id: str, nult: int = INE_NULT) -> list[dict]:
    """Fetch Ãºltimos N datos de una serie temporal del INE."""
    url = f"{BASE}/DATOS_SERIE/{serie_id}?nult={nult}"
    print(f"  GET {url}")
    try:
        data = fetch_json(url)
    except Exception as exc:
        print(f"  âš  Error parseando respuesta para {serie_id}: {exc}")
        return []
    if not data:
        print(f"  âš  Sin datos para serie {serie_id}")
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
        print(f"  âš  Formato inesperado para serie {serie_id}")
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


def get_tabla_filtrada(tabla_id: str, filtros: list[str], nult: int = INE_NULT) -> list[dict]:
    """Fetch rows from an INE table and keep rows whose name contains all filters."""
    url = f"{BASE}/DATOS_TABLA/{tabla_id}?tip=AM&nult={nult}"
    print(f"  GET {url}")
    data = fetch_json(url)
    if not isinstance(data, list):
        print(f"  ⚠ Formato inesperado para tabla {tabla_id}")
        return []

    rows = []
    filtros_norm = [f.lower() for f in filtros]
    for item in data:
        nombre = item.get("Nombre", "")
        if not all(f in nombre.lower() for f in filtros_norm):
            continue
        for entry in item.get("Data", []):
            if not isinstance(entry, dict):
                continue
            rows.append({
                "serie_id": f"TABLA_{tabla_id}",
                "fecha": entry.get("Fecha", ""),
                "valor": entry.get("Valor", None),
                "nombre": nombre,
                "unidad": "",
                "extraido_en": timestamp(),
            })
    return rows


# =====================================================
# Mapeo de series INE relevantes para Barcelona / CataluÃ±a / EspaÃ±a
# =====================================================
# Las series se identifican por su cÃ³digo COD en INEbase.
# Cuando no existe dato municipal de Barcelona, se usa CataluÃ±a o provincia.

SERIES = {
    # --- IPC ---
    "ipc_general_barcelona": {
        "serie": "IPC251852",  # IPC general, provincia Barcelona
        "variable": "Ãndice general IPC",
        "descripcion": "IPC general mensual, provincia de Barcelona",
    },
    "ipc_alimentos_barcelona": {
        "serie": "IPC251856",  # IPC alimentos
        "variable": "InflaciÃ³n alimentaria",
        "descripcion": "IPC alimentos y bebidas no alcohÃ³licas, Barcelona",
    },

    # --- Salarios ---
    "salario_medio_cataluna": {
        "serie": "EAES33856",  # Encuesta estructura salarial - CataluÃ±a
        "variable": "Salario medio bruto",
        "descripcion": "Salario medio bruto anual, CataluÃ±a",
    },

    # --- EPA (Encuesta PoblaciÃ³n Activa) ---
    "tasa_paro_cataluna": {
        "serie": "EPA453154",  # Tasa de paro CataluÃ±a
        "variable": "Tasa de paro",
        "descripcion": "Tasa de paro EPA, CataluÃ±a, trimestral",
    },
    "tasa_empleo_cataluna": {
        "serie": "EPA659685",  # Tasa de empleo CataluÃ±a
        "variable": "Tasa de empleo",
        "descripcion": "Tasa de empleo EPA, CataluÃ±a, trimestral",
    },

    # --- Comercio ---
    "ventas_retail_cataluna": {
        "serie": "ICM4425",  # Indice comercio minorista Cataluna, base actual
        "variable": "Ventas retail",
        "descripcion": "Ãndice de comercio al por menor, CataluÃ±a",
    },

    # --- Turismo ---
    "ocupacion_hotelera_barcelona": {
        "tabla": "59841",
        "filtros": ["Barcelona", "Total, Total"],
        "variable": "OcupaciÃ³n hotelera",
        "descripcion": "Grado de ocupaciÃ³n hotelera, Barcelona provincia",
    },

    # --- Empresas ---
    "creacion_empresas_barcelona": {
        "serie": "SM24955",  # Sociedades mercantiles constituidas, Barcelona
        "variable": "CreaciÃ³n de empresas",
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
        if "tabla" in cfg:
            rows = get_tabla_filtrada(cfg["tabla"], cfg.get("filtros", []))
        else:
            rows = get_serie(cfg["serie"])
        if rows:
            # AÃ±adir metadatos del catÃ¡logo
            for r in rows:
                r["variable_iseu"] = cfg["variable"]
                r["clave_config"] = key
            all_rows.extend(rows)
            resultados[key] = {"estado": "OK", "filas": len(rows)}
            print(f"  âœ“ {len(rows)} registros")
        else:
            resultados[key] = {"estado": "ERROR", "filas": 0}
            print(f"  âœ— Sin datos")

    # Guardar datos
    if all_rows:
        save_csv(all_rows, "ine_raw.csv", "ine")
        save_json(all_rows, "ine_raw.json", "ine")

    # Guardar log
    save_json({
        "fuente": "INE",
        "timestamp": timestamp(),
        "nult": INE_NULT,
        "series_configuradas": len(SERIES),
        "resultados": resultados,
    }, "ine_log.json", "ine")

    ok = sum(1 for v in resultados.values() if v["estado"] == "OK")
    print(f"\nResumen INE: {ok}/{len(SERIES)} series extraÃ­das correctamente")
    return resultados


if __name__ == "__main__":
    scrape_ine()

