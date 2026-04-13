"""
Scraper: Open Data BCN (Ajuntament de Barcelona)
API: CKAN (https://opendata-ajuntament.barcelona.cat/data/api/action)

Cubre: alquiler, calidad del aire, zonas verdes, movilidad, turismo,
       licencias comerciales, equipamientos, seguridad.
"""
from utils import fetch_json, save_json, save_csv, timestamp

BASE = "https://opendata-ajuntament.barcelona.cat/data/api/action"


def buscar_dataset(query: str, rows: int = 5) -> list[dict]:
    """Busca datasets en el catálogo Open Data BCN."""
    url = f"{BASE}/package_search?q={query}&rows={rows}"
    print(f"  Buscando: {query}")
    data = fetch_json(url)
    if not data or not data.get("success"):
        return []
    results = []
    for pkg in data.get("result", {}).get("results", []):
        resources = []
        for res in pkg.get("resources", []):
            resources.append({
                "id": res["id"],
                "name": res.get("name", ""),
                "format": res.get("format", ""),
                "url": res.get("url", ""),
            })
        results.append({
            "id": pkg["id"],
            "title": pkg.get("title", ""),
            "notes": pkg.get("notes", "")[:200],
            "num_resources": len(resources),
            "resources": resources,
        })
    return results


def descargar_recurso(resource_id: str, limit: int = 1000) -> list[dict]:
    """Descarga registros de un recurso CKAN por datastore_search."""
    url = f"{BASE}/datastore_search?resource_id={resource_id}&limit={limit}"
    print(f"  GET datastore_search resource={resource_id[:12]}...")
    data = fetch_json(url)
    if not data or not data.get("success"):
        return []
    return data.get("result", {}).get("records", [])


# =====================================================
# Datasets conocidos de Open Data BCN para ISEU+
# =====================================================
DATASETS = {
    "bcn_alquiler": {
        "query": "preu lloguer habitatge districte",
        "variable": "Precio alquiler medio",
        "descripcion": "Precio medio del alquiler por distrito de Barcelona",
        "resource_hint": "csv",
    },
    "bcn_aire": {
        "query": "qualitat aire estacions contaminacio",
        "variable": "Calidad del aire",
        "descripcion": "Datos de estaciones de calidad del aire de Barcelona",
        "resource_hint": "csv",
    },
    "bcn_zonas_verdes": {
        "query": "espais verds parcs jardins superficie",
        "variable": "Zonas verdes por habitante",
        "descripcion": "Superficie de zonas verdes por distrito",
        "resource_hint": "csv",
    },
    "bcn_turismo": {
        "query": "turisme visitants hotels barcelona",
        "variable": "Turismo (nº visitantes)",
        "descripcion": "Estadísticas de turismo y visitantes en Barcelona",
        "resource_hint": "csv",
    },
    "bcn_movilidad": {
        "query": "transport public viatgers tmb metro bus",
        "variable": "Movilidad urbana",
        "descripcion": "Viajeros en transporte público (TMB, metro, bus)",
        "resource_hint": "csv",
    },
    "bcn_licencias": {
        "query": "llicencies activitat economica obertura",
        "variable": "Licencias comerciales",
        "descripcion": "Licencias de actividad económica por distrito",
        "resource_hint": "csv",
    },
    "bcn_equipamientos": {
        "query": "equipaments salut educacio centres",
        "variable": "Acceso a salud",
        "descripcion": "Equipamientos de salud y educación por distrito",
        "resource_hint": "csv",
    },
    "bcn_seguridad": {
        "query": "seguretat incidents delictes districte",
        "variable": "Seguridad ciudadana",
        "descripcion": "Indicadores de seguridad por distrito",
        "resource_hint": "csv",
    },
    "bcn_transporte": {
        "query": "tarifes transport public abonament",
        "variable": "Transporte público coste",
        "descripcion": "Tarifas de transporte público en Barcelona",
        "resource_hint": "csv",
    },
    "bcn_poblacion": {
        "query": "poblacio padro districte barri",
        "variable": "Población distritos",
        "descripcion": "Padrón municipal por distrito (para denominadores per cápita)",
        "resource_hint": "csv",
    },
}


def scrape_opendata_bcn():
    """Ejecuta la exploración y descarga de datasets de Open Data BCN."""
    print(f"\n{'='*60}")
    print(f"SCRAPER OPEN DATA BCN - {timestamp()}")
    print(f"{'='*60}")

    catalogo = {}
    resultados = {}

    for key, cfg in DATASETS.items():
        print(f"\n[{key}] {cfg['descripcion']}")

        # Paso 1: Buscar dataset
        datasets = buscar_dataset(cfg["query"])
        if not datasets:
            print(f"  ✗ No se encontraron datasets para '{cfg['query']}'")
            resultados[key] = {"estado": "NO_ENCONTRADO", "filas": 0}
            continue

        best = datasets[0]
        print(f"  Dataset: {best['title']}")
        catalogo[key] = {
            "dataset_id": best["id"],
            "title": best["title"],
            "resources": best["resources"],
            "variable_iseu": cfg["variable"],
        }

        # Paso 2: Intentar descargar el primer recurso CSV
        csv_resources = [r for r in best["resources"]
                        if r["format"].upper() in ("CSV", "JSON")]
        if csv_resources:
            resource = csv_resources[0]
            records = descargar_recurso(resource["id"])
            if records:
                # Guardar datos
                for r in records:
                    r["_variable_iseu"] = cfg["variable"]
                    r["_dataset_key"] = key
                    r["_extraido_en"] = timestamp()
                save_csv(records, f"{key}_raw.csv", "opendata_bcn")
                resultados[key] = {"estado": "OK", "filas": len(records)}
                print(f"  ✓ {len(records)} registros descargados")
            else:
                # Si datastore_search falla, guardar URL para descarga manual
                resultados[key] = {
                    "estado": "URL_DISPONIBLE",
                    "url": resource["url"],
                    "filas": 0,
                }
                print(f"  ~ Datastore no disponible, URL directa: {resource['url']}")
        else:
            resultados[key] = {"estado": "SIN_CSV", "filas": 0}
            print(f"  ⚠ No hay recursos CSV/JSON en este dataset")

    # Guardar catálogo y log
    save_json(catalogo, "bcn_catalogo.json", "opendata_bcn")
    save_json({
        "fuente": "Open Data BCN",
        "timestamp": timestamp(),
        "datasets_buscados": len(DATASETS),
        "resultados": resultados,
    }, "bcn_log.json", "opendata_bcn")

    ok = sum(1 for v in resultados.values() if v["estado"] == "OK")
    print(f"\nResumen BCN: {ok}/{len(DATASETS)} datasets descargados")
    return resultados


if __name__ == "__main__":
    scrape_opendata_bcn()
