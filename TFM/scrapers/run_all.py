"""
Orquestador principal de scrapers ISEU+ Barcelona.
Ejecuta todos los scrapers y genera un informe consolidado.

Uso:
  python run_all.py          # Ejecutar todos
  python run_all.py ine      # Solo INE
  python run_all.py bcn ree  # Solo Open Data BCN y REE
"""
import sys
import json
from datetime import datetime
from pathlib import Path

# Añadir directorio actual al path
sys.path.insert(0, str(Path(__file__).parent))

from config import DATA_DIR, VARIABLES, FUENTES
from utils import save_json, timestamp


def run_scraper(name: str) -> dict:
    """Ejecuta un scraper por nombre y devuelve sus resultados."""
    try:
        if name == "ine":
            from scraper_ine import scrape_ine
            return scrape_ine()
        elif name == "bcn":
            from scraper_opendata_bcn import scrape_opendata_bcn
            return scrape_opendata_bcn()
        elif name == "ree":
            from scraper_ree import scrape_ree
            return scrape_ree()
        elif name == "idescat":
            from scraper_idescat import scrape_idescat
            return scrape_idescat()
        elif name == "mitma":
            from scraper_mitma import scrape_mitma
            return scrape_mitma()
        elif name == "empleo":
            from scraper_empleo import scrape_empleo
            return scrape_empleo()
        else:
            print(f"⚠ Scraper desconocido: {name}")
            return {}
    except Exception as exc:
        print(f"✗ Error ejecutando scraper {name}: {exc}")
        return {"_error": str(exc)}


SCRAPERS_DISPONIBLES = ["ine", "bcn", "ree", "idescat", "mitma", "empleo"]


def main():
    args = sys.argv[1:]
    scrapers_to_run = args if args else SCRAPERS_DISPONIBLES

    print("=" * 70)
    print(f"  ISEU+ Barcelona - Ejecución de scrapers")
    print(f"  Fecha: {timestamp()}")
    print(f"  Scrapers: {', '.join(scrapers_to_run)}")
    print("=" * 70)

    resultados_global = {}

    for name in scrapers_to_run:
        if name not in SCRAPERS_DISPONIBLES:
            print(f"\n⚠ Scraper '{name}' no reconocido. Disponibles: {SCRAPERS_DISPONIBLES}")
            continue
        resultados_global[name] = run_scraper(name)

    # --- Informe consolidado ---
    print("\n" + "=" * 70)
    print("  INFORME CONSOLIDADO")
    print("=" * 70)

    total_ok = 0
    total_error = 0
    total_manual = 0

    for scraper_name, results in resultados_global.items():
        if "_error" in results:
            print(f"  {scraper_name}: ERROR FATAL - {results['_error']}")
            total_error += 1
            continue

        fuente = FUENTES.get(scraper_name, {})
        nombre = fuente.get("nombre", scraper_name.upper())
        ok = sum(1 for v in results.values() if isinstance(v, dict) and v.get("estado") == "OK")
        err = sum(1 for v in results.values() if isinstance(v, dict) and v.get("estado") in ("ERROR", "NO_ENCONTRADO"))
        manual = sum(1 for v in results.values() if isinstance(v, dict) and v.get("estado") == "MANUAL")
        total_ok += ok
        total_error += err
        total_manual += manual
        print(f"  {nombre}: {ok} OK | {err} errores | {manual} manuales")

    print(f"\n  TOTAL: {total_ok} extracciones OK | {total_error} errores | {total_manual} manuales")

    # Cobertura de variables MVP
    mvp_vars = [v for v in VARIABLES if v[6]]  # v[6] = es_mvp
    mvp_with_scraper = [v for v in mvp_vars if v[5] is not None]  # v[5] = scraper_id
    print(f"\n  Variables MVP: {len(mvp_vars)} totales, {len(mvp_with_scraper)} con scraper asignado")
    print(f"  Variables sin fuente automatizable: {sum(1 for v in VARIABLES if v[4] is None)}")

    # Guardar informe
    save_json({
        "timestamp": timestamp(),
        "scrapers_ejecutados": list(scrapers_to_run),
        "resultados": {k: v for k, v in resultados_global.items()},
        "resumen": {
            "total_ok": total_ok,
            "total_error": total_error,
            "total_manual": total_manual,
            "variables_mvp": len(mvp_vars),
            "variables_mvp_con_scraper": len(mvp_with_scraper),
        }
    }, "informe_ejecucion.json")

    print(f"\n  Informe guardado en: {DATA_DIR / 'informe_ejecucion.json'}")
    print("=" * 70)


if __name__ == "__main__":
    main()
