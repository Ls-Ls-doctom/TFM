from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any

from _api_common import api_dir, download_url, fetch_json, write_json, write_manifest


AEMET_ENDPOINTS = [
    {
        "name": "observacion_convencional_todas",
        "url": "https://opendata.aemet.es/opendata/api/observacion/convencional/todas",
        "file": "observacion_convencional_todas.json",
    },
    {
        "name": "prediccion_municipios_diaria",
        "url": "https://opendata.aemet.es/opendata/api/prediccion/especifica/municipio/diaria/28079",
        "file": "prediccion_madrid_diaria.json",
    },
]


def scrape_aemet() -> dict[str, Any]:
    base = api_dir("aemet")
    api_key = os.getenv("AEMET_API_KEY", "").strip()
    docs = download_url(
        "https://opendata.aemet.es/dist/index.html",
        base / "aemet_swagger_ui.html",
        timeout=120,
        max_mb=20,
    )
    if not api_key:
        manifest = write_manifest(
            "aemet",
            {
                "status": "SKIPPED_AUTH",
                "source": "AEMET OpenData",
                "resources_total": len(AEMET_ENDPOINTS),
                "resources_ok": 0,
                "resources": [docs],
                "error": "AEMET_API_KEY is not defined. Define it to download real AEMET data.",
            },
        )
        return {"status": "SKIPPED_AUTH", "resources_ok": 0, "resources_total": len(AEMET_ENDPOINTS), "manifest": str(manifest)}

    resources: list[dict[str, Any]] = [docs]
    for endpoint in AEMET_ENDPOINTS:
        descriptor_url = endpoint["url"] + "?" + urllib.parse.urlencode({"api_key": api_key})
        descriptor_path = base / f"{endpoint['name']}_descriptor.json"
        try:
            descriptor = fetch_json(descriptor_url, timeout=120)
            write_json(descriptor_path, descriptor)
            data_url = descriptor.get("datos")
            if not data_url:
                resources.append(
                    {
                        **endpoint,
                        "url": descriptor_url,
                        "local_path": str(descriptor_path),
                        "status": "ERROR",
                        "error": "AEMET descriptor did not include datos URL",
                    }
                )
                continue
            result = download_url(data_url, base / endpoint["file"], timeout=180, max_mb=100)
            result.update(endpoint)
            result["descriptor_path"] = str(descriptor_path)
            resources.append(result)
        except Exception as exc:  # noqa: BLE001
            resources.append({**endpoint, "url": descriptor_url, "status": "ERROR", "error": str(exc)})
    ok = sum(1 for item in resources if item.get("status") in {"OK", "OK_CACHED"})
    manifest = write_manifest(
        "aemet",
        {
            "status": "OK" if ok > 1 else "ERROR",
            "source": "AEMET OpenData",
            "resources_total": len(resources),
            "resources_ok": ok,
            "resources": resources,
        },
    )
    return {"status": "OK" if ok > 1 else "ERROR", "resources_ok": ok, "resources_total": len(resources), "manifest": str(manifest)}


if __name__ == "__main__":
    print(json.dumps(scrape_aemet(), ensure_ascii=False, indent=2))
