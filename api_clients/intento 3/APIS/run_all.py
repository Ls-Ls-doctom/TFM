from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from api_aemet import scrape_aemet
from api_catalogos import scrape_catalogos
from api_ine import scrape_ine
from api_mitma import scrape_mitma
from api_sepe import scrape_sepe


BASE_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


API_CLIENTS = {
    "ine": scrape_ine,
    "mitma": scrape_mitma,
    "sepe": scrape_sepe,
    "catalogos": scrape_catalogos,
    "catalogs": scrape_catalogos,
    "aemet": scrape_aemet,
}

DEFAULT_CLIENTS = ["ine", "mitma", "sepe", "catalogos", "aemet"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecuta APIs del intento 3 ISEU+.")
    parser.add_argument("apis", nargs="*", help="APIs a ejecutar: ine mitma sepe catalogos aemet")
    args = parser.parse_args()

    selected = args.apis or DEFAULT_CLIENTS
    results = {}
    for name in selected:
        if name not in API_CLIENTS:
            results[name] = {"status": "ERROR", "error": f"API desconocida: {name}"}
            continue
        print(f"\n=== API {name} ===")
        try:
            results[name] = API_CLIENTS[name]()
        except Exception as exc:
            results[name] = {"status": "ERROR", "error": str(exc)}
            print(f"ERROR {name}: {exc}")

    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "apis_ejecutadas": selected,
        "resultados": results,
    }
    out = REPORTS_DIR / "apis_run.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nInforme APIs: {out}")
    has_error = any(is_error(result) for result in results.values())
    return 1 if has_error else 0


def is_error(result: object) -> bool:
    return isinstance(result, dict) and result.get("status") == "ERROR"


if __name__ == "__main__":
    raise SystemExit(main())

