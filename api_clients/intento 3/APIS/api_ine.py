from __future__ import annotations

import json
from typing import Any

from _api_common import api_dir, download_url, write_json, write_manifest


INE_TABLES = [
    {
        "table_id": "73027",
        "name": "poblacion_municipio_sexo",
        "description": "Poblacion por municipio y sexo. Censo anual. Municipios.",
    },
    {
        "table_id": "33791",
        "name": "poblacion_municipio_pais_nacimiento",
        "description": "Poblacion por sexo, municipios y pais de nacimiento. Padron continuo.",
    },
]


def scrape_ine() -> dict[str, Any]:
    base = api_dir("ine")
    resources: list[dict[str, Any]] = []
    for table in INE_TABLES:
        table_id = table["table_id"]
        dataset_dir = base / table["name"]
        urls = {
            "csv_semicolon": f"https://www.ine.es/jaxiT3/files/t/csv_bdsc/{table_id}.csv",
            "xlsx": f"https://www.ine.es/jaxiT3/files/t/xlsx/{table_id}.xlsx",
            "json_latest_metadata": f"https://servicios.ine.es/wstempus/js/es/DATOS_TABLA/{table_id}?nult=1&tip=AM",
        }
        metadata_path = dataset_dir / "dataset_metadata.json"
        write_json(metadata_path, table)
        for label, url in urls.items():
            suffix = ".json" if label == "json_metadata" else "." + label.split("_")[0].replace("semicolon", "csv")
            out = dataset_dir / f"{table['name']}_{label}{suffix}"
            result = download_url(url, out, timeout=240, max_mb=350)
            result.update(
                {
                    "dataset": table["name"],
                    "table_id": table_id,
                    "source": "INE",
                    "format": label,
                }
            )
            resources.append(result)
    ok = sum(1 for item in resources if item["status"] in {"OK", "OK_CACHED"})
    manifest = write_manifest(
        "ine",
        {
            "status": "OK" if ok else "ERROR",
            "source": "Instituto Nacional de Estadistica",
            "resources_total": len(resources),
            "resources_ok": ok,
            "resources": resources,
        },
    )
    return {"status": "OK" if ok else "ERROR", "resources_ok": ok, "resources_total": len(resources), "manifest": str(manifest)}


if __name__ == "__main__":
    print(json.dumps(scrape_ine(), ensure_ascii=False, indent=2))
