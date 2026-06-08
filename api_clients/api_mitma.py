"""
Cliente API: MITMA (Ministerio de Transportes - Vivienda)
Portal: https://www.mitma.gob.es/vivienda

Cubre: precio vivienda m2 (tasado y transacción).
Los datos se publican como CSV/XLSX descargables.
"""
from utils import fetch_csv_text, fetch_json, save_json, save_csv, timestamp
import csv
import io
import ssl
import urllib.request
from config import DATA_DIR

# URLs conocidas de datos de vivienda del MITMA
# Estos enlaces pueden cambiar; se verifican en cada ejecución.
URLS_VIVIENDA = {
    "precio_m2_venta": {
        "url": "https://apps.fomento.gob.es/BoletinOnline2/sedal/35103500.XLS",
        "variable": "Precio vivienda m2",
        "descripcion": "Valor tasado medio de vivienda libre (€/m2), provincial",
    },
}


def descargar_xls(url: str, filename: str):
    """Descarga una hoja XLS oficial para procesarla en la fase de limpieza."""
    headers = {"User-Agent": "ISEU-TFM-Barcelona/1.0"}
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
        content = resp.read()

    folder = DATA_DIR / "mitma"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    with open(path, "wb") as f:
        f.write(content)
    print(f"  -> Guardado: {path} ({len(content)} bytes)")
    return path


def parse_mitma_csv(text: str) -> list[dict]:
    """Parsea un CSV del MITMA (separador ; típico en España)."""
    rows = []
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    for row in reader:
        # Filtrar por Barcelona (provincia 08)
        provincia = row.get("Provincia", row.get("provincia", ""))
        if "Barcelona" in str(provincia) or "08" in str(provincia):
            row["extraido_en"] = timestamp()
            rows.append(row)
    return rows


def scrape_mitma():
    """Ejecuta la extracción de datos de vivienda del MITMA."""
    print(f"\n{'='*60}")
    print(f"SCRAPER MITMA - {timestamp()}")
    print(f"{'='*60}")

    resultados = {}

    for key, cfg in URLS_VIVIENDA.items():
        print(f"\n[{key}] {cfg['descripcion']}")
        print(f"  GET {cfg['url']}")
        if cfg["url"].lower().endswith(".xls"):
            try:
                path = descargar_xls(cfg["url"], f"{key}_raw.xls")
                resultados[key] = {
                    "estado": "XLS_DESCARGADO",
                    "filas": 0,
                    "archivo": str(path),
                    "nota": "Pendiente de limpieza/conversion desde Excel binario.",
                }
                print("  ✓ XLS descargado para limpieza posterior")
                continue
            except Exception as exc:
                print(f"  ✗ Error descargando XLS: {exc}")

        text = fetch_csv_text(cfg["url"])
        if text:
            rows = parse_mitma_csv(text)
            if rows:
                for r in rows:
                    r["variable_iseu"] = cfg["variable"]
                save_csv(rows, f"{key}_raw.csv", "mitma")
                resultados[key] = {"estado": "OK", "filas": len(rows)}
                print(f"  ✓ {len(rows)} registros (Barcelona)")
            else:
                resultados[key] = {"estado": "SIN_DATOS_BCN", "filas": 0}
                print(f"  ⚠ CSV descargado pero sin filas de Barcelona")
        else:
            resultados[key] = {"estado": "ERROR", "filas": 0}
            print(f"  ✗ No se pudo descargar")

    save_json({
        "fuente": "MITMA",
        "timestamp": timestamp(),
        "resultados": resultados,
    }, "mitma_log.json", "mitma")

    ok = sum(1 for v in resultados.values() if v["estado"] in ("OK", "XLS_DESCARGADO"))
    print(f"\nResumen MITMA: {ok}/{len(URLS_VIVIENDA)} extracciones correctas")
    return resultados


if __name__ == "__main__":
    scrape_mitma()
