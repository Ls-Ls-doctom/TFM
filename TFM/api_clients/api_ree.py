"""
Cliente API: REE (Red Eléctrica de España)
API: https://apidatos.ree.es

Cubre: precio electricidad (PVPC/mercado), demanda eléctrica.
Documentación: https://www.ree.es/es/apidatos
"""
from utils import fetch_json, save_json, save_csv, timestamp

BASE = "https://apidatos.ree.es/es/datos"


def get_precios_electricidad(start_date: str, end_date: str) -> list[dict]:
    """
    Obtiene precios del mercado eléctrico (PVPC).
    Formato fechas: YYYY-MM-DDThh:mm
    NOTA: La API REE requiere time_trunc=hour para precios y fechas no futuras.
    """
    url = (
        f"{BASE}/mercados/precios-mercados-tiempo-real"
        f"?start_date={start_date}&end_date={end_date}"
        f"&time_trunc=hour"
    )
    print(f"  GET precios electricidad {start_date} -> {end_date}")
    data = fetch_json(url)
    if not data or "included" not in data:
        return []

    rows = []
    for serie in data["included"]:
        for val in serie.get("attributes", {}).get("values", []):
            rows.append({
                "fecha": val.get("datetime", ""),
                "valor_eur_mwh": val.get("value", None),
                "concepto": serie.get("attributes", {}).get("title", "PVPC"),
                "tipo": serie.get("type", ""),
                "variable_iseu": "Precio electricidad",
                "extraido_en": timestamp(),
            })
    return rows


def get_demanda(start_date: str, end_date: str) -> list[dict]:
    """
    Obtiene evolución de demanda eléctrica nacional.
    Para Cataluña no hay desglose directo; se usa demanda nacional como proxy.
    """
    url = (
        f"{BASE}/demanda/evolucion"
        f"?start_date={start_date}&end_date={end_date}"
        f"&time_trunc=month"
    )
    print(f"  GET demanda eléctrica {start_date} -> {end_date}")
    data = fetch_json(url)
    if not data or "included" not in data:
        return []

    rows = []
    for serie in data["included"]:
        for val in serie.get("attributes", {}).get("values", []):
            rows.append({
                "fecha": val.get("datetime", ""),
                "valor_mwh": val.get("value", None),
                "concepto": serie.get("attributes", {}).get("title", ""),
                "variable_iseu": "Consumo eléctrico industrial",
                "extraido_en": timestamp(),
            })
    return rows


def scrape_ree():
    """Ejecuta la extracción de datos de REE."""
    print(f"\n{'='*60}")
    print(f"SCRAPER REE - {timestamp()}")
    print(f"{'='*60}")

    resultados = {}

    # Precios electricidad - último mes disponible (usamos datos recientes reales)
    print("\n[ree_precio] Precios electricidad PVPC")
    precios = get_precios_electricidad("2025-03-01T00:00", "2025-03-02T23:59")
    if precios:
        save_csv(precios, "ree_precios_raw.csv", "ree")
        resultados["ree_precio"] = {"estado": "OK", "filas": len(precios)}
        print(f"  ✓ {len(precios)} registros")
    else:
        resultados["ree_precio"] = {"estado": "ERROR", "filas": 0}
        print(f"  ✗ Sin datos")

    # Demanda eléctrica
    print("\n[ree_demanda] Demanda eléctrica")
    demanda = get_demanda("2025-01-01T00:00", "2025-03-31T23:59")
    if demanda:
        save_csv(demanda, "ree_demanda_raw.csv", "ree")
        resultados["ree_demanda"] = {"estado": "OK", "filas": len(demanda)}
        print(f"  ✓ {len(demanda)} registros")
    else:
        resultados["ree_demanda"] = {"estado": "ERROR", "filas": 0}
        print(f"  ✗ Sin datos")

    save_json({
        "fuente": "REE",
        "timestamp": timestamp(),
        "resultados": resultados,
    }, "ree_log.json", "ree")

    ok = sum(1 for v in resultados.values() if v["estado"] == "OK")
    print(f"\nResumen REE: {ok}/{len(resultados)} extracciones correctas")
    return resultados


if __name__ == "__main__":
    scrape_ree()
