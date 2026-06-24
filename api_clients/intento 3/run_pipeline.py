from __future__ import annotations

import argparse
from pathlib import Path

from pipeline._common import BASE_DIR, REPORTS_DIR, now, run_python, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline reproducible ISEU+ Bronze -> Silver -> Gold -> SQLite.")
    parser.add_argument("--skip-collect", action="store_true", help="No ejecuta APIs; usa Bronze ya descargado.")
    parser.add_argument(
        "--skip-municipal-resources",
        action="store_true",
        help="No descarga recursos municipales; util si ya existen o se quiere una prueba rapida.",
    )
    parser.add_argument(
        "--municipal-max-resources",
        default="80",
        help="Límite por ciudad para descarga municipal cuando no se omite.",
    )
    args = parser.parse_args()

    steps = []
    if not args.skip_collect:
        steps.append(("apis", BASE_DIR / "APIS" / "run_all.py", []))
        steps.append(("municipios_catalogos", BASE_DIR / "APIS" / "municipios" / "run_municipios.py", []))
        if not args.skip_municipal_resources:
            steps.append(
                (
                    "municipios_recursos",
                    BASE_DIR / "APIS" / "municipios" / "download_recursos.py",
                    [
                        "barcelona",
                        "madrid",
                        "valencia",
                        "sevilla",
                        "bilbao",
                        "zaragoza",
                        "--since",
                        "2010",
                        "--max-resources",
                        args.municipal_max_resources,
                    ],
                )
            )

    steps.extend(
        [
            ("inventory_bronze", BASE_DIR / "pipeline" / "01_inventory_bronze.py", []),
            ("clean_silver", BASE_DIR / "pipeline" / "02_clean_silver.py", []),
            ("build_gold", BASE_DIR / "pipeline" / "03_build_gold.py", []),
            ("build_sqlite", BASE_DIR / "pipeline" / "04_build_sqlite.py", []),
        ]
    )

    results = []
    for name, script, step_args in steps:
        print(f"\n=== {name} ===")
        result = run_python(script, step_args)
        results.append({"name": name, **result})
        print(result["stdout"])
        if result["stderr"]:
            print(result["stderr"])
        if result["returncode"] != 0:
            break

    report = {
        "started_at": results[0]["started_at"] if results else now(),
        "finished_at": now(),
        "status": "OK" if all(item["returncode"] == 0 for item in results) else "ERROR",
        "steps": results,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(REPORTS_DIR / "pipeline_run.json", report)
    print(f"\nReporte pipeline: {REPORTS_DIR / 'pipeline_run.json'}")
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
