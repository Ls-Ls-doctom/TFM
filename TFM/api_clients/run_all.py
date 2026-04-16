"""
Orquestador principal de conectores API ISEU+ Barcelona.
Ejecuta todos los clientes API y genera un informe consolidado.

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


def run_api_client(name: str) -> dict:
    """Ejecuta un cliente API por nombre y devuelve sus resultados."""
    try:
        if name == "ine":
            from api_ine import scrape_ine
            return scrape_ine()
        elif name == "bcn":
            from api_opendata_bcn import scrape_opendata_bcn
            return scrape_opendata_bcn()
        elif name == "ree":
            from api_ree import scrape_ree
            return scrape_ree()
        elif name == "idescat":
            from api_idescat import scrape_idescat
            return scrape_idescat()
        elif name == "mitma":
            from api_mitma import scrape_mitma
            return scrape_mitma()
        elif name == "empleo":
            from api_empleo import scrape_empleo
            return scrape_empleo()
        else:
            print(f"⚠ Cliente API desconocido: {name}")
            return {}
    except Exception as exc:
        print(f"✗ Error ejecutando cliente API {name}: {exc}")
        return {"_error": str(exc)}


API_CLIENTS_DISPONIBLES = ["ine", "bcn", "ree", "idescat", "mitma", "empleo"]


def main():
    args = sys.argv[1:]
    clients_to_run = args if args else API_CLIENTS_DISPONIBLES

    print("=" * 70)
    print(f"  ISEU+ Barcelona - Ejecución de conectores API")
    print(f"  Fecha: {timestamp()}")
    print(f"  APIs: {', '.join(clients_to_run)}")
    print("=" * 70)

    resultados_global = {}

    for name in clients_to_run:
        if name not in API_CLIENTS_DISPONIBLES:
            print(f"\n⚠ Cliente API '{name}' no reconocido. Disponibles: {API_CLIENTS_DISPONIBLES}")
            continue
        resultados_global[name] = run_api_client(name)

    # --- Informe consolidado ---
    print("\n" + "=" * 70)
    print("  INFORME CONSOLIDADO")
    print("=" * 70)

    total_ok = 0
    total_error = 0
    total_manual = 0

    for api_name, results in resultados_global.items():
        if "_error" in results:
            print(f"  {api_name}: ERROR FATAL - {results['_error']}")
            total_error += 1
            continue

        fuente = FUENTES.get(api_name, {})
        nombre = fuente.get("nombre", api_name.upper())
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
    mvp_with_api = [v for v in mvp_vars if v[5] is not None]  # v[5] = api_id
    print(f"\n  Variables MVP: {len(mvp_vars)} totales, {len(mvp_with_api)} con API asignada")
    print(f"  Variables sin fuente automatizable: {sum(1 for v in VARIABLES if v[4] is None)}")

    # Guardar informe
    save_json({
        "timestamp": timestamp(),
        "apis_ejecutadas": list(clients_to_run),
        "resultados": {k: v for k, v in resultados_global.items()},
        "resumen": {
            "total_ok": total_ok,
            "total_error": total_error,
            "total_manual": total_manual,
            "variables_mvp": len(mvp_vars),
            "variables_mvp_con_api": len(mvp_with_api),
        }
    }, "informe_ejecucion.json")

    print(f"\n  Informe guardado en: {DATA_DIR / 'informe_ejecucion.json'}")
    print("=" * 70)


if __name__ == "__main__":
    main()
