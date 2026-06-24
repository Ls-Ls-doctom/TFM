from __future__ import annotations

from _common import json_catalog, print_result


def scrape_sevilla() -> dict:
    return json_catalog(
        city_slug="sevilla",
        source_name="Centro de Datos Urbanos del Ayuntamiento de Sevilla",
        url="https://cda-idesevilla.opendata.arcgis.com/api/search/v1/collections/all/items?limit=100",
    )


if __name__ == "__main__":
    print_result(scrape_sevilla())
