from __future__ import annotations

from _common import ckan_search, print_result


def scrape_barcelona() -> dict:
    return ckan_search(
        city_slug="barcelona",
        source_name="Open Data BCN",
        endpoint="https://opendata-ajuntament.barcelona.cat/data/api/action/package_search",
    )


if __name__ == "__main__":
    print_result(scrape_barcelona())

