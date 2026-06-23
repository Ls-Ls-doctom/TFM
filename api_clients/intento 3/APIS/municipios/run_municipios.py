from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from api_barcelona import scrape_barcelona
from api_bilbao import scrape_bilbao
from api_madrid import scrape_madrid
from api_malaga import scrape_malaga
from api_sevilla import scrape_sevilla
from api_valencia import scrape_valencia
from api_zaragoza import scrape_zaragoza


BASE_DIR = Path(__file__).resolve().parents[2]
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

MUNICIPAL_APIS = {
    "barcelona": scrape_barcelona,
    "madrid": scrape_madrid,
    "valencia": scrape_valencia,
    "sevilla": scrape_sevilla,
    "bilbao": scrape_bilbao,
    "malaga": scrape_malaga,
    "zaragoza": scrape_zaragoza,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecuta APIs municipales del intento 3.")
    parser.add_argument("municipios", nargs="*", help="barcelona madrid valencia sevilla bilbao malaga zaragoza")
    args = parser.parse_args()
    selected = args.municipios or list(MUNICIPAL_APIS)

    results = {}
    for name in selected:
        if name not in MUNICIPAL_APIS:
            results[name] = {"status": "ERROR", "error": f"Municipio desconocido: {name}"}
            continue
        print(f"\n=== Municipio {name} ===")
        try:
            results[name] = MUNICIPAL_APIS[name]()
        except Exception as exc:
            results[name] = {"status": "ERROR", "error": str(exc)}
            print(f"ERROR {name}: {exc}")

    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "municipios_ejecutados": selected,
        "resultados": results,
    }
    out = REPORTS_DIR / "municipios_run.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nInforme municipios: {out}")
    return 1 if any(isinstance(item, dict) and item.get("status") == "ERROR" for item in results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())

