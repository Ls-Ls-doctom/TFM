from __future__ import annotations

from _common import ckan_search, print_result


def scrape_valencia() -> dict:
    return ckan_search(
        city_slug="valencia",
        source_name="Open Data Valencia",
        endpoint="https://opendata.vlci.valencia.es/api/3/action/package_search",
    )


if __name__ == "__main__":
    print_result(scrape_valencia())

