from __future__ import annotations

from _common import html_catalog, print_result


def scrape_bilbao() -> dict:
    return html_catalog(
        city_slug="bilbao",
        source_name="Bilbao Open Data",
        url="https://www.bilbao.eus/opendata/",
    )


if __name__ == "__main__":
    print_result(scrape_bilbao())

