from __future__ import annotations

from _common import ckan_search, print_result


def scrape_malaga() -> dict:
    return ckan_search(
        city_slug="malaga",
        source_name="Datos Abiertos Malaga",
        endpoint="https://datosabiertos.malaga.eu/api/3/action/package_search",
    )


if __name__ == "__main__":
    print_result(scrape_malaga())

