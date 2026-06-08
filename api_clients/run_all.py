"""
Orquestador principal de conectores API ISEU+ Barcelona.
Ejecuta todos los clientes API y genera un informe consolidado.

Uso:
  python run_all.py             # Ejecutar todos, regenerar SQLite y EDA
  python run_all.py ine         # Solo INE, regenerar SQLite y EDA
  python run_all.py bcn ree     # Solo Open Data BCN y REE, regenerar SQLite y EDA
  python run_all.py --skip-sql  # Ejecutar APIs sin limpiar/cargar SQLite ni EDA
  python run_all.py --skip-eda  # Ejecutar APIs y SQL sin regenerar EDA
"""
import sys
import json
import subprocess
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


def run_sql_pipeline() -> dict:
    """Ejecuta limpieza y carga SQLite para dejar la capa SQL lista."""
    project_root = Path(__file__).resolve().parents[1]
    steps = [
        project_root / "pag_web" / "Procesos" / "Limpieza" / "clean_datasets.py",
        project_root / "pag_web" / "Procesos" / "Datasets" / "build_sqlite.py",
    ]
    results = []

    print("\n" + "=" * 70)
    print("  PIPELINE SQL")
    print("=" * 70)

    for script in steps:
        print(f"  Ejecutando: {script.relative_to(project_root)}")
        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=project_root,
            text=True,
            capture_output=True,
        )
        if completed.stdout:
            print(completed.stdout.strip())
        if completed.stderr:
            print(completed.stderr.strip())

        results.append({
            "script": str(script.relative_to(project_root)),
            "returncode": completed.returncode,
            "ok": completed.returncode == 0,
        })
        if completed.returncode != 0:
            break

    ok = all(item["ok"] for item in results)
    print(f"  SQL listo: {'SI' if ok else 'NO'}")
    return {
        "estado": "OK" if ok else "ERROR",
        "pasos": results,
    }


def run_eda_pipeline() -> dict:
    """Regenera los reportes EDA sobre raw, limpios y SQLite."""
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "EDA" / "eda_datasets.py"

    print("\n" + "=" * 70)
    print("  PIPELINE EDA")
    print("=" * 70)

    if not script.exists():
        print(f"  EDA no encontrado: {script.relative_to(project_root)}")
        return {
            "estado": "NO_ENCONTRADO",
            "script": str(script.relative_to(project_root)),
            "ok": False,
        }

    print(f"  Ejecutando: {script.relative_to(project_root)}")
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=project_root,
        text=True,
        capture_output=True,
    )
    if completed.stdout:
        print(completed.stdout.strip())
    if completed.stderr:
        print(completed.stderr.strip())

    ok = completed.returncode == 0
    print(f"  EDA listo: {'SI' if ok else 'NO'}")
    return {
        "estado": "OK" if ok else "ERROR",
        "script": str(script.relative_to(project_root)),
        "returncode": completed.returncode,
        "ok": ok,
    }


def main():
    args = sys.argv[1:]
    skip_sql = "--skip-sql" in args
    skip_eda = "--skip-eda" in args
    clients_to_run = [arg for arg in args if not arg.startswith("--")] or API_CLIENTS_DISPONIBLES

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

    sql_result = None
    eda_result = None
    if skip_sql:
        print("\n  Pipeline SQL omitido por --skip-sql")
        print("  Pipeline EDA omitido porque depende de SQL actualizado")
    else:
        sql_result = run_sql_pipeline()
        if skip_eda:
            print("\n  Pipeline EDA omitido por --skip-eda")
        elif sql_result.get("estado") == "OK":
            eda_result = run_eda_pipeline()
        else:
            print("\n  Pipeline EDA omitido porque SQL no terminó correctamente")

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
        ok = sum(1 for v in results.values() if isinstance(v, dict) and v.get("estado") in ("OK", "XLS_DESCARGADO", "RAW_DESCARGADO"))
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
        "pipeline_sql": sql_result,
        "pipeline_eda": eda_result,
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
