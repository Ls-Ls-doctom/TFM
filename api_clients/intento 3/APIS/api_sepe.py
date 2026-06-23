from __future__ import annotations

import json
from typing import Any

from _api_common import (
    api_dir,
    datos_gob_title_search,
    download_url,
    extract_year,
    get_items,
    get_text,
    safe_name,
    write_json,
    write_manifest,
)


SEPE_SEARCHES = [
    {"query": "paro", "needle": "paro registrado por municipio", "folder": "paro_registrado"},
    {"query": "contratos", "needle": "contratos registrados por municipio", "folder": "contratos_registrados"},
    {"query": "empleo", "needle": "demandantes de empleo por municipio", "folder": "demandantes_empleo"},
]


def scrape_sepe(since_year: int = 2010) -> dict[str, Any]:
    base = api_dir("sepe")
    resources: list[dict[str, Any]] = []
    datasets: list[dict[str, Any]] = []
    manifest_path = base / "manifest_raw.json"
    for spec in SEPE_SEARCHES:
        search = datos_gob_title_search(spec["query"], page_size=10)
        write_json(base / spec["folder"] / "datos_gob_search_raw.json", search)
        dataset = select_dataset(get_items(search["payload"]), spec["needle"])
        if not dataset:
            resources.append({"dataset": spec["folder"], "status": "ERROR", "error": "Dataset not found in datos.gob.es"})
            continue
        datasets.append(dataset)
        write_json(base / spec["folder"] / "dataset_metadata_raw.json", dataset)
        for distribution in dataset.get("distribution", []):
            item = normalize_distribution(spec["folder"], distribution)
            year = item.get("year")
            if year is not None and year < since_year:
                continue
            if item["format"] != "CSV":
                continue
            out = base / spec["folder"] / "resources" / f"{year or 'sin_anio'}_{safe_name(item['title'], item['dataset'])}.csv"
            result = download_url(item["url"], out, timeout=90, max_mb=120)
            result.update(item)
            resources.append(result)
            write_json(
                manifest_path,
                {
                    "api": "sepe",
                    "status": "RUNNING",
                    "source": "SEPE via datos.gob.es",
                    "since_year": since_year,
                    "datasets_found": len(datasets),
                    "resources_total": len(resources),
                    "resources_ok": sum(1 for item in resources if item.get("status") in {"OK", "OK_CACHED"}),
                    "resources": resources,
                },
            )
    ok = sum(1 for item in resources if item.get("status") in {"OK", "OK_CACHED"})
    manifest = write_manifest(
        "sepe",
        {
            "status": "OK" if ok else "ERROR",
            "source": "SEPE via datos.gob.es",
            "since_year": since_year,
            "datasets_found": len(datasets),
            "resources_total": len(resources),
            "resources_ok": ok,
            "resources": resources,
        },
    )
    return {"status": "OK" if ok else "ERROR", "resources_ok": ok, "resources_total": len(resources), "manifest": str(manifest)}


def select_dataset(items: list[dict[str, Any]], needle: str) -> dict[str, Any] | None:
    needle = needle.lower()
    for item in items:
        title = get_text(item.get("title")).lower()
        if needle in title:
            return item
    return items[0] if items else None


def normalize_distribution(dataset: str, distribution: dict[str, Any]) -> dict[str, Any]:
    title = get_text(distribution.get("title"))
    fmt = str(distribution.get("format", "")).rsplit("/", 1)[-1].upper()
    url = str(distribution.get("accessURL", ""))
    return {
        "dataset": dataset,
        "title": title,
        "year": extract_year(title + " " + url),
        "format": fmt,
        "url": url,
        "source": "SEPE",
    }


if __name__ == "__main__":
    print(json.dumps(scrape_sepe(), ensure_ascii=False, indent=2))
