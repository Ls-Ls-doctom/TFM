from __future__ import annotations

import json
from typing import Any

from _api_common import api_dir, download_url, fetch_text, write_manifest


MITMA_RESOURCES = [
    {
        "name": "portal_opendata_movilidad",
        "url": "https://opendata-movilidad.mitma.es/",
        "file": "portal_opendata_movilidad.html",
        "description": "Indice publico de Open Data Movilidad MITMA.",
    },
    {
        "name": "relaciones_distrito_mitma",
        "url": "https://opendata-movilidad.mitma.es/relaciones_distrito_mitma.csv",
        "file": "relaciones_distrito_mitma.csv",
        "description": "Relacion de distritos MITMA y geografias.",
    },
    {
        "name": "readme_formato_ficheros",
        "url": "https://opendata-movilidad.mitma.es/README%20-%20formato%20ficheros%20movilidad%20MITMA%2020201228.pdf",
        "file": "README_formato_ficheros_movilidad_MITMA_20201228.pdf",
        "description": "Documento tecnico de formato de ficheros de movilidad.",
    },
]


def scrape_mitma() -> dict[str, Any]:
    base = api_dir("mitma")
    resources: list[dict[str, Any]] = []
    for item in MITMA_RESOURCES:
        result = download_url(item["url"], base / item["file"], timeout=180, max_mb=80)
        result.update(item)
        result["source"] = "MITMA Open Data Movilidad"
        resources.append(result)

    try:
        html = fetch_text("https://opendata-movilidad.mitma.es/", timeout=60)
        discovered = {
            "source_url": "https://opendata-movilidad.mitma.es/",
            "html_chars": len(html),
            "note": "Portal index saved as raw HTML; time-series files are large and should be selected by period/geography in a later ETL step.",
        }
    except Exception as exc:  # noqa: BLE001
        discovered = {"error": str(exc)}

    ok = sum(1 for item in resources if item["status"] in {"OK", "OK_CACHED"})
    manifest = write_manifest(
        "mitma",
        {
            "status": "OK" if ok else "ERROR",
            "source": "Ministerio de Transportes / Open Data Movilidad",
            "coverage_note": "Open Data Movilidad publica datos desde 2020/2022 segun version, no desde 2010.",
            "resources_total": len(resources),
            "resources_ok": ok,
            "resources": resources,
            "portal_probe": discovered,
        },
    )
    return {"status": "OK" if ok else "ERROR", "resources_ok": ok, "resources_total": len(resources), "manifest": str(manifest)}


if __name__ == "__main__":
    print(json.dumps(scrape_mitma(), ensure_ascii=False, indent=2))
