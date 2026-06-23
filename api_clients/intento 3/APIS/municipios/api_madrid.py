from __future__ import annotations

from _common import print_result, text_catalog


def scrape_madrid() -> dict:
    return text_catalog(
        city_slug="madrid",
        source_name="Madrid Datos Abiertos",
        url="https://datos.madrid.es/catalog/dataset.rdf",
        filename="catalog_raw.rdf",
    )


if __name__ == "__main__":
    print_result(scrape_madrid())
