from __future__ import annotations

import json
from typing import Any

from _api_common import api_dir, datos_gob_title_search, get_items, get_text, safe_name, write_json, write_manifest


CATALOG_QUERIES = [
    "poblacion municipios",
    "renta municipios",
    "paro municipio",
    "contratos municipio",
    "precio vivienda municipio",
    "movilidad",
    "calidad aire",
    "zonas verdes",
    "accidentes trafico",
]


def scrape_catalogos() -> dict[str, Any]:
    base = api_dir("catalogos")
    resources: list[dict[str, Any]] = []
    for query in CATALOG_QUERIES:
        result = datos_gob_title_search(query, page_size=10)
        items = get_items(result["payload"])
        out = base / f"{safe_name(query)}_datos_gob_search_raw.json"
        write_json(out, result)
        resources.append(
            {
                "query": query,
                "url": result["url"],
                "local_path": str(out),
                "status": "OK",
                "datasets_found": len(items),
                "top_titles": [get_text(item.get("title")) for item in items[:5]],
            }
        )
    manifest = write_manifest(
        "catalogos",
        {
            "status": "OK",
            "source": "datos.gob.es API",
            "resources_total": len(resources),
            "resources_ok": len(resources),
            "resources": resources,
        },
    )
    return {"status": "OK", "resources_ok": len(resources), "resources_total": len(resources), "manifest": str(manifest)}


if __name__ == "__main__":
    print(json.dumps(scrape_catalogos(), ensure_ascii=False, indent=2))
