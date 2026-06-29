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
    {
        "table_id": "69301",
        "name": "indicadores_urbanos_demografia",
        "description": "Indicadores Urbanos comparables de demografia por ciudad.",
        "csv_only": True,
    },
    {
        "table_id": "69302",
        "name": "indicadores_urbanos_social",
        "description": "Indicadores Urbanos de hogares, vivienda, alquiler y seguridad por ciudad.",
        "csv_only": True,
    },
    {
        "table_id": "69303",
        "name": "indicadores_urbanos_economia",
        "description": "Indicadores Urbanos de empleo, estructura sectorial y renta por ciudad.",
        "csv_only": True,
    },
    {
        "table_id": "69304",
        "name": "indicadores_urbanos_educacion",
        "description": "Indicadores Urbanos de educacion por ciudad.",
        "csv_only": True,
    },
    {
        "table_id": "69305",
        "name": "indicadores_urbanos_suelo",
        "description": "Indicadores Urbanos de superficie, zonas verdes y usos del suelo.",
        "csv_only": True,
    },
    {
        "table_id": "69306",
        "name": "indicadores_urbanos_movilidad",
        "description": "Indicadores Urbanos de desplazamientos al trabajo por ciudad.",
        "csv_only": True,
    },
    {
        "table_id": "69307",
        "name": "indicadores_urbanos_turismo",
        "description": "Indicadores Urbanos de pernoctaciones y plazas turisticas por ciudad.",
        "csv_only": True,
    },
    {
        "table_id": "76154",
        "name": "ipc_provincial_anual",
        "description": "IPC provincial anual: indice general y grupos ECOICOP. Se usa como proxy de precios de cada ciudad.",
        "csv_only": True,
    },
    {
        "table_id": "59060",
        "name": "ipva_municipal",
        "description": "Indice de Precios de Vivienda en Alquiler para municipios de mas de 10.000 habitantes.",
        "csv_only": True,
    },
    {
        "table_id": "306",
        "name": "dirce_locales_provinciales",
        "description": "Unidades locales activas por provincia y estrato de asalariados. Proxy provincial de tejido empresarial.",
        "csv_only": True,
    },
]


def scrape_ine() -> dict[str, Any]:
    base = api_dir("ine")
    resources: list[dict[str, Any]] = []
    for table in INE_TABLES:
        table_id = table["table_id"]
        dataset_dir = base / table["name"]
        urls = {"csv_semicolon": f"https://www.ine.es/jaxiT3/files/t/csv_bdsc/{table_id}.csv"}
        if not table.get("csv_only"):
            urls.update(
                {
                    "xlsx": f"https://www.ine.es/jaxiT3/files/t/xlsx/{table_id}.xlsx",
                    "json_latest_metadata": f"https://servicios.ine.es/wstempus/js/es/DATOS_TABLA/{table_id}?nult=1&tip=AM",
                }
            )
        metadata_path = dataset_dir / "dataset_metadata.json"
        write_json(metadata_path, table)
        for label, url in urls.items():
            suffix = ".json" if label.startswith("json_") else "." + label.split("_")[0].replace("semicolon", "csv")
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
