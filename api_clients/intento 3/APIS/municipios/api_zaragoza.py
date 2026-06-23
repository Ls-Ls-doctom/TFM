from __future__ import annotations

from _common import json_catalog, print_result


def scrape_zaragoza() -> dict:
    return json_catalog(
        city_slug="zaragoza",
        source_name="Datos Abiertos Zaragoza",
        url="https://www.zaragoza.es/sede/servicio/catalogo.json?rows=1000",
    )


if __name__ == "__main__":
    print_result(scrape_zaragoza())
