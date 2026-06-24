from __future__ import annotations

from _common import ckan_search, print_result


def scrape_madrid() -> dict:
    return ckan_search(
        city_slug="madrid",
        source_name="Madrid Datos Abiertos",
        endpoint="https://datos.madrid.es/api/3/action/package_search",
    )


if __name__ == "__main__":
    print_result(scrape_madrid())
