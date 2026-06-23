from __future__ import annotations

from _common import html_catalog, print_result


def scrape_sevilla() -> dict:
    return html_catalog(
        city_slug="sevilla",
        source_name="IDE Sevilla Open Data",
        url="https://sig.urbanismosevilla.org/sevilla.art/datosabiertos/index.html",
    )


if __name__ == "__main__":
    print_result(scrape_sevilla())

