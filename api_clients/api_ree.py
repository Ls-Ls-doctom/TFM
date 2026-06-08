"""
Cliente API: REE (Red Eléctrica de España)
API: https://apidatos.ree.es

Cubre: precio electricidad (PVPC/mercado), demanda eléctrica.
Documentación: https://www.ree.es/es/apidatos
"""
from datetime import date, datetime, timedelta

from config import REE_END_DATE, REE_START_DATE
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


def month_chunks(start: date, end: date) -> list[tuple[str, str]]:
    chunks = []
    current = start.replace(day=1)
    while current <= end:
        if current.month == 12:
            next_month = current.replace(year=current.year + 1, month=1)
        else:
            next_month = current.replace(month=current.month + 1)
        chunk_start = max(current, start)
        chunk_end = min(next_month - timedelta(days=1), end)
        chunks.append((f"{chunk_start.isoformat()}T00:00", f"{chunk_end.isoformat()}T23:59"))
        current = next_month
    return chunks


def configured_range() -> tuple[date, date]:
    start = datetime.strptime(REE_START_DATE, "%Y-%m-%d").date()
    if REE_END_DATE:
        end = datetime.strptime(REE_END_DATE, "%Y-%m-%d").date()
    else:
        end = date.today() - timedelta(days=1)
    if end < start:
        end = start
    return start, end


def scrape_ree():
    """Ejecuta la extracción de datos de REE."""
    print(f"\n{'='*60}")
    print(f"SCRAPER REE - {timestamp()}")
    print(f"{'='*60}")

    resultados = {}
    start, end = configured_range()

    # Precios electricidad - último mes disponible (usamos datos recientes reales)
    print("\n[ree_precio] Precios electricidad PVPC")
    precios = []
    for chunk_start, chunk_end in month_chunks(start, end):
        precios.extend(get_precios_electricidad(chunk_start, chunk_end))
    if precios:
        save_csv(precios, "ree_precios_raw.csv", "ree")
        resultados["ree_precio"] = {"estado": "OK", "filas": len(precios)}
        print(f"  ✓ {len(precios)} registros")
    else:
        resultados["ree_precio"] = {"estado": "ERROR", "filas": 0}
        print(f"  ✗ Sin datos")

    # Demanda eléctrica
    print("\n[ree_demanda] Demanda eléctrica")
    demanda = []
    for chunk_start, chunk_end in month_chunks(start, end):
        demanda.extend(get_demanda(chunk_start, chunk_end))
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
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "resultados": resultados,
    }, "ree_log.json", "ree")

    ok = sum(1 for v in resultados.values() if v["estado"] == "OK")
    print(f"\nResumen REE: {ok}/{len(resultados)} extracciones correctas")
    return resultados


if __name__ == "__main__":
    scrape_ree()
