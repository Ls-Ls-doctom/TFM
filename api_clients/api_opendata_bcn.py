"""
Cliente API: Open Data BCN (Ajuntament de Barcelona)
API: CKAN (https://opendata-ajuntament.barcelona.cat/data/api/action)

Cubre: alquiler, calidad del aire, zonas verdes, movilidad, turismo,
       licencias comerciales, equipamientos, seguridad.
"""
import csv
import io
import json
import re
import ssl
import urllib.request
from urllib.parse import urlencode

from config import DATA_DIR, BCN_DATASTORE_MAX_RECORDS, BCN_DATASTORE_PAGE_SIZE
from utils import fetch_json, save_json, save_csv, timestamp

BASE = "https://opendata-ajuntament.barcelona.cat/data/api/action"


def buscar_dataset(query: str, rows: int = 20) -> list[dict]:
    """Busca datasets en el catálogo Open Data BCN."""
    params = urlencode({"q": query, "rows": rows})
    url = f"{BASE}/package_search?{params}"
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


def score_dataset(
    dataset: dict,
    positive_terms: list[str],
    negative_terms: list[str] | None = None,
    must_terms: list[str] | None = None,
) -> int:
    """Puntua un dataset CKAN segun titulo, descripcion y recursos."""
    negative_terms = negative_terms or []
    searchable = " ".join([
        dataset.get("title", ""),
        dataset.get("notes", ""),
        " ".join(resource.get("name", "") for resource in dataset.get("resources", [])),
        " ".join(resource.get("format", "") for resource in dataset.get("resources", [])),
    ]).lower()

    must_terms = must_terms or []
    if must_terms and not any(term.lower() in searchable for term in must_terms):
        return -999

    score = 0
    for term in positive_terms:
        if term.lower() in searchable:
            score += 3
    for term in negative_terms:
        if term.lower() in searchable:
            score -= 5
    if any(resource.get("format", "").upper() in ("CSV", "JSON") for resource in dataset.get("resources", [])):
        score += 2
    return score


def elegir_dataset(
    datasets: list[dict],
    positive_terms: list[str],
    negative_terms: list[str] | None = None,
    must_terms: list[str] | None = None,
) -> dict | None:
    """Elige el dataset mas coherente con la variable buscada."""
    if not datasets:
        return None
    scored = sorted(
        ((score_dataset(dataset, positive_terms, negative_terms, must_terms), dataset) for dataset in datasets),
        key=lambda item: item[0],
        reverse=True,
    )
    best_score, best_dataset = scored[0]
    return best_dataset if best_score >= 5 else None


def descargar_recurso(resource_id: str, limit: int = BCN_DATASTORE_PAGE_SIZE) -> list[dict]:
    """Descarga registros de un recurso CKAN por datastore_search con paginacion."""
    records: list[dict] = []
    offset = 0
    total = None

    while offset < BCN_DATASTORE_MAX_RECORDS:
        params = urlencode({"resource_id": resource_id, "limit": limit, "offset": offset})
        url = f"{BASE}/datastore_search?{params}"
        print(f"  GET datastore_search resource={resource_id[:12]}... offset={offset}")
        data = fetch_json(url)
        if not data or not data.get("success"):
            break

        result = data.get("result", {})
        page_records = result.get("records", [])
        if total is None:
            total = result.get("total")
        if not page_records:
            break

        records.extend(page_records)
        offset += len(page_records)
        if total is not None and offset >= int(total):
            break
        if len(page_records) < limit:
            break

    if records:
        print(f"  -> {len(records)} registros CKAN descargados")
    return records


def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "recurso_raw"


def descargar_url_directa(resource: dict, dataset_key: str):
    """Descarga un recurso directo cuando CKAN datastore no esta disponible."""
    url = resource.get("url", "")
    if not url:
        return None

    headers = {"User-Agent": "ISEU-TFM-Barcelona/1.0"}
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=90, context=ctx) as resp:
        content_type = resp.headers.get_content_type()
        charset = resp.headers.get_content_charset() or "utf-8"
        content = resp.read()

    if content_type == "text/html" and content.lstrip().lower().startswith(b"<!doctype"):
        return None

    fmt = resource.get("format", "").upper()
    if fmt == "CSV" or content_type in ("text/csv", "application/csv"):
        text = content.decode(charset, errors="replace")
        first_line = text.splitlines()[0] if text.splitlines() else ""
        delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
        rows = list(csv.DictReader(io.StringIO(text), delimiter=delimiter))
        return {"tipo": "rows", "rows": rows} if rows else None

    if fmt == "JSON" or content_type == "application/json":
        data = json.loads(content.decode(charset, errors="replace"))
        if isinstance(data, list):
            return {"tipo": "rows", "rows": data}
        if isinstance(data, dict):
            records = data.get("records") or data.get("data") or data.get("result", {}).get("records")
            if isinstance(records, list):
                return {"tipo": "rows", "rows": records}

    folder = DATA_DIR / "opendata_bcn"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / _safe_filename(resource.get("name") or f"{dataset_key}_raw")
    with open(path, "wb") as f:
        f.write(content)
    return {"tipo": "file", "path": str(path), "bytes": len(content)}


# =====================================================
# Datasets conocidos de Open Data BCN para ISEU+
# =====================================================
DATASETS = {
    "bcn_alquiler": {
        "query": "lloguer",
        "positive_terms": ["lloguer", "alquiler", "rental", "habitatge", "vivienda", "taxa_lloguer"],
        "negative_terms": ["car rental", "bicicletes", "transport"],
        "variable": "Precio alquiler medio",
        "descripcion": "Precio medio del alquiler por distrito de Barcelona",
        "resource_hint": "csv",
    },
    "bcn_aire": {
        "query": "qualitat aire estacions contaminacio",
        "positive_terms": ["aire", "contaminacio", "contaminación", "qualitat"],
        "negative_terms": ["zbe", "lez", "low emission zone"],
        "variable": "Calidad del aire",
        "descripcion": "Datos de estaciones de calidad del aire de Barcelona",
        "resource_hint": "csv",
    },
    "bcn_zonas_verdes": {
        "query": "espais verds",
        "positive_terms": ["verd", "verds", "parcs", "jardins", "superficie"],
        "negative_terms": ["turistic", "touristic", "turisme"],
        "variable": "Zonas verdes por habitante",
        "descripcion": "Superficie de zonas verdes por distrito",
        "resource_hint": "csv",
    },
    "bcn_turismo": {
        "query": "turisme visitants hotels barcelona",
        "positive_terms": ["turisme", "turismo", "visitants", "hotels", "allotjament"],
        "negative_terms": [],
        "variable": "Turismo (nº visitantes)",
        "descripcion": "Estadísticas de turismo y visitantes en Barcelona",
        "resource_hint": "csv",
    },
    "bcn_movilidad": {
        "query": "Bicing service use",
        "positive_terms": ["bicing", "service use", "bicing_us"],
        "negative_terms": ["stations information", "estacions", "informacio_estacions"],
        "variable": "Movilidad urbana",
        "descripcion": "Viajeros en transporte público (TMB, metro, bus)",
        "resource_hint": "csv",
    },
    "bcn_licencias": {
        "query": "locals comercials",
        "positive_terms": ["census", "premises", "economic activity", "locals", "comercial"],
        "negative_terms": [],
        "variable": "Licencias comerciales",
        "descripcion": "Licencias de actividad económica por distrito",
        "resource_hint": "csv",
    },
    "bcn_equipamientos": {
        "query": "equipaments salut educacio centres",
        "positive_terms": ["equipaments", "equipamientos", "salut", "educacio", "centres"],
        "negative_terms": [],
        "variable": "Acceso a salud",
        "descripcion": "Equipamientos de salud y educación por distrito",
        "resource_hint": "csv",
    },
    "bcn_seguridad": {
        "query": "accidents guardia urbana",
        "positive_terms": ["accidents", "guardia urbana", "gu", "persones", "causa"],
        "negative_terms": [],
        "variable": "Seguridad ciudadana",
        "descripcion": "Indicadores de seguridad por distrito",
        "resource_hint": "csv",
    },
    "bcn_transporte": {
        "query": "tarifes transport",
        "positive_terms": ["tarifes", "tarifas", "rates", "parking", "transport"],
        "negative_terms": [],
        "variable": "Coste movilidad urbana",
        "descripcion": "Tarifas de movilidad urbana disponibles en Open Data BCN",
        "resource_hint": "csv",
    },
    "bcn_poblacion": {
        "query": "poblacio",
        "positive_terms": ["poblacio", "population", "sex", "sexe", "pad", "mdbas"],
        "negative_terms": ["ibi", "tax", "impost", "fee", "property", "noise", "soroll"],
        "must_terms": ["poblacio", "population"],
        "variable": "Población distritos",
        "descripcion": "Padrón municipal por distrito (para denominadores per cápita)",
        "resource_hint": "csv",
    },
}

DATASETS.update(
    {
        "bcn_renta": {
            "query": "renda barris",
            "positive_terms": ["disposable income", "renda", "income", "per capita", "barri", "neighborhood"],
            "negative_terms": ["rent", "lloguer", "rental"],
            "variable": "Ingreso disponible per capita",
            "descripcion": "Renta disponible de los hogares per capita por barrios",
            "resource_hint": "csv",
        },
        "bcn_locales_precio": {
            "query": "mercat treball barris",
            "positive_terms": ["real estate market", "premises", "retail price", "locals", "barri"],
            "negative_terms": ["factsheets", "occupation"],
            "variable": "Precio alquiler comercial",
            "descripcion": "Precio estimado de locales comerciales por barrio",
            "resource_hint": "csv",
        },
        "bcn_compraventa_numero": {
            "query": "habitatge compravenda",
            "positive_terms": ["number", "transactions", "sale transaction", "notarial", "property"],
            "negative_terms": ["area"],
            "variable": "Compraventa inmobiliaria",
            "descripcion": "Numero de transmisiones inmobiliarias por compraventa",
            "resource_hint": "csv",
        },
        "bcn_compraventa_superficie": {
            "query": "habitatge compravenda",
            "positive_terms": ["area", "m2", "transactions", "sale transaction", "notarial", "property"],
            "negative_terms": ["number"],
            "variable": "Superficie inmobiliaria transmitida",
            "descripcion": "Superficie transmitida por compraventa inmobiliaria",
            "resource_hint": "csv",
        },
        "bcn_ruido_poblacion": {
            "query": "poblacio barris noise",
            "positive_terms": ["noise", "soroll", "exposed population", "strategic noise map"],
            "negative_terms": ["raster", "facade", "gpkg"],
            "variable": "Ruido urbano",
            "descripcion": "Poblacion expuesta a niveles de ruido",
            "resource_hint": "csv",
        },
        "bcn_contaminacion_poblacion": {
            "query": "population exposed atmospheric pollution",
            "positive_terms": ["population exposed", "atmospheric pollution", "contamination", "pollution"],
            "negative_terms": ["lez", "low emission zone"],
            "variable": "Poblacion expuesta contaminacion",
            "descripcion": "Poblacion expuesta a contaminacion atmosferica",
            "resource_hint": "csv",
        },
        "bcn_terrazas": {
            "query": "terrasses",
            "positive_terms": ["ordinary terraces", "terraces", "terrasses", "authorizations"],
            "negative_terms": ["exceptional"],
            "variable": "Terrazas actividad economica",
            "descripcion": "Autorizaciones de terrazas en espacio publico",
            "resource_hint": "csv",
        },
        "bcn_iae": {
            "query": "activitat economica",
            "positive_terms": ["economic activities tax", "quota", "iae", "impost", "activitats economiques"],
            "negative_terms": ["census of premises"],
            "variable": "Presion fiscal actividad economica",
            "descripcion": "Cuota del impuesto de actividades economicas",
            "resource_hint": "csv",
        },
    }
)


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

        best = elegir_dataset(
            datasets,
            cfg.get("positive_terms", []),
            cfg.get("negative_terms", []),
            cfg.get("must_terms", []),
        )
        if not best:
            print(f"  ✗ No se encontro un dataset suficientemente coherente para '{cfg['query']}'")
            resultados[key] = {"estado": "NO_ENCONTRADO", "filas": 0}
            continue

        print(f"  Dataset: {best['title']}")
        catalogo[key] = {
            "dataset_id": best["id"],
            "title": best["title"],
            "resources": best["resources"],
            "variable_iseu": cfg["variable"],
        }

        csv_resources = [r for r in best["resources"] if r["format"].upper() in ("CSV", "JSON")]
        downloaded = False
        all_records = []
        resource_results = []

        for resource in csv_resources:
            records = descargar_recurso(resource["id"])
            if not records:
                direct = descargar_url_directa(resource, key)
                if direct and direct["tipo"] == "rows":
                    records = direct["rows"]
                elif direct and direct["tipo"] == "file":
                    resource_results.append({
                        "resource_id": resource["id"],
                        "resource_name": resource.get("name", ""),
                        "estado": "RAW_DESCARGADO",
                        "archivo": direct["path"],
                        "bytes": direct["bytes"],
                        "filas": 0,
                    })
                    print(f"  ✓ Recurso bruto descargado: {direct['path']}")
                    continue

            if not records:
                resource_results.append({
                    "resource_id": resource["id"],
                    "resource_name": resource.get("name", ""),
                    "estado": "SIN_DATOS",
                    "filas": 0,
                })
                continue

            for r in records:
                r["_variable_iseu"] = cfg["variable"]
                r["_dataset_key"] = key
                r["_resource_id"] = resource["id"]
                r["_resource_name"] = resource.get("name", "")
                r["_extraido_en"] = timestamp()
            all_records.extend(records)
            resource_results.append({
                "resource_id": resource["id"],
                "resource_name": resource.get("name", ""),
                "estado": "OK",
                "filas": len(records),
            })
            print(f"  ✓ {len(records)} registros descargados desde {resource.get('name', resource['id'])}")
            downloaded = True

        if all_records:
            save_csv(all_records, f"{key}_raw.csv", "opendata_bcn")
            resultados[key] = {
                "estado": "OK",
                "filas": len(all_records),
                "recursos_ok": sum(1 for item in resource_results if item.get("estado") == "OK"),
                "recursos_intentados": len(csv_resources),
                "recursos": resource_results,
            }

        if not downloaded:
            raw_resources = [
                r for r in best["resources"]
                if r["format"].upper() in ("GPKG", "ZIP", "GEOJSON", "SHP", "APPLICATION/X-7Z-COMPRESSED")
            ]
            positive_terms = [term.lower() for term in cfg.get("positive_terms", [])]
            raw_resources = sorted(
                raw_resources,
                key=lambda r: sum(term in (r.get("name", "") + " " + r.get("url", "")).lower() for term in positive_terms),
                reverse=True,
            )
            for resource in raw_resources:
                direct = descargar_url_directa(resource, key)
                if direct and direct["tipo"] == "file":
                    resultados[key] = {
                        "estado": "RAW_DESCARGADO",
                        "archivo": direct["path"],
                        "bytes": direct["bytes"],
                        "filas": 0,
                    }
                    print(f"  ✓ Recurso bruto descargado: {direct['path']}")
                    downloaded = True
                    break

        if not downloaded:
            if csv_resources:
                resultados[key] = {"estado": "URL_DISPONIBLE", "url": csv_resources[0]["url"], "filas": 0}
                print(f"  ~ Datastore no disponible, URL directa: {csv_resources[0]['url']}")
            else:
                resultados[key] = {"estado": "SIN_CSV", "filas": 0}
                print("  ⚠ No hay recursos CSV/JSON descargables en este dataset")

    # Guardar catálogo y log
    save_json(catalogo, "bcn_catalogo.json", "opendata_bcn")
    save_json({
        "fuente": "Open Data BCN",
        "timestamp": timestamp(),
        "page_size": BCN_DATASTORE_PAGE_SIZE,
        "max_records": BCN_DATASTORE_MAX_RECORDS,
        "datasets_buscados": len(DATASETS),
        "resultados": resultados,
    }, "bcn_log.json", "opendata_bcn")

    ok = sum(1 for v in resultados.values() if v["estado"] in ("OK", "RAW_DESCARGADO"))
    print(f"\nResumen BCN: {ok}/{len(DATASETS)} datasets descargados")
    return resultados


if __name__ == "__main__":
    scrape_opendata_bcn()
