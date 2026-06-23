from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


BASE_DIR = Path(__file__).resolve().parents[2]
BRONZE_MUNICIPIOS_DIR = BASE_DIR / "data_lake" / "bronze" / "municipios"
REPORTS_DIR = BASE_DIR / "reports"
USER_AGENT = "ISEU-TFM-Municipios/3.0"

for directory in (BRONZE_MUNICIPIOS_DIR, REPORTS_DIR):
    directory.mkdir(parents=True, exist_ok=True)

SEARCH_TERMS = [
    "poblacion",
    "renta",
    "desempleo",
    "actividad economica",
    "vivienda",
    "movilidad",
    "trafico",
    "transporte publico",
    "calidad aire",
    "ruido",
    "zonas verdes",
    "accidentes",
    "equipamientos",
]


def ssl_context(verify: bool = True) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if not verify or os.getenv("ISEU3_DISABLE_SSL_VERIFY", "0") == "1":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def request(url: str, accept: str = "*/*") -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
        },
    )


def fetch_json(url: str, retries: int = 3) -> Any | None:
    cert_failed = False
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request(url, "application/json"), timeout=60, context=ssl_context()) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            cert_failed = cert_failed or "CERTIFICATE_VERIFY_FAILED" in str(exc)
            print(f"  intento {attempt}/{retries}: {exc}")
            if attempt < retries:
                time.sleep(1.5)
    if cert_failed and os.getenv("ISEU3_ALLOW_SSL_FALLBACK", "1") == "1":
        print("  aviso: reintentando con SSL sin verificacion por certificados locales")
        try:
            with urllib.request.urlopen(request(url, "application/json"), timeout=60, context=ssl_context(False)) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"  fallback SSL fallo: {exc}")
    return None


def fetch_text(url: str, retries: int = 3) -> str | None:
    cert_failed = False
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request(url, "text/html,*/*"), timeout=60, context=ssl_context()) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            cert_failed = cert_failed or "CERTIFICATE_VERIFY_FAILED" in str(exc)
            print(f"  intento {attempt}/{retries}: {exc}")
            if attempt < retries:
                time.sleep(1.5)
    if cert_failed and os.getenv("ISEU3_ALLOW_SSL_FALLBACK", "1") == "1":
        print("  aviso: reintentando con SSL sin verificacion por certificados locales")
        try:
            with urllib.request.urlopen(request(url, "text/html,*/*"), timeout=60, context=ssl_context(False)) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"  fallback SSL fallo: {exc}")
    return None


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def city_dir(city_slug: str) -> Path:
    path = BRONZE_MUNICIPIOS_DIR / city_slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(city_slug: str, filename: str, payload: Any) -> Path:
    path = city_dir(city_slug) / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_text(city_slug: str, filename: str, payload: str) -> Path:
    path = city_dir(city_slug) / filename
    path.write_text(payload, encoding="utf-8", errors="replace")
    return path


def ckan_search(city_slug: str, source_name: str, endpoint: str, rows: int | None = None) -> dict[str, Any]:
    if rows is None:
        rows = int(os.getenv("ISEU3_CKAN_ROWS", "100"))
    searches = []
    for term in SEARCH_TERMS:
        url = endpoint + "?" + urlencode({"q": term, "rows": rows})
        data = fetch_json(url)
        searches.append({"term": term, "url": url, "status": "OK" if data else "ERROR", "data": data})
    payload = {
        "source_name": source_name,
        "access_type": "CKAN API",
        "collected_at": now(),
        "search_terms": SEARCH_TERMS,
        "results": searches,
    }
    out = save_json(city_slug, "catalog_search_raw.json", payload)
    ok = sum(1 for item in searches if item["status"] == "OK")
    return {"status": "OK" if ok else "ERROR", "queries_ok": ok, "queries_total": len(searches), "output": str(out)}


def json_catalog(city_slug: str, source_name: str, url: str) -> dict[str, Any]:
    data = fetch_json(url)
    payload = {
        "source_name": source_name,
        "access_type": "JSON API",
        "source_url": url,
        "collected_at": now(),
        "data": data,
    }
    out = save_json(city_slug, "catalog_raw.json", payload)
    return {"status": "OK" if data else "ERROR", "output": str(out)}


def html_catalog(city_slug: str, source_name: str, url: str) -> dict[str, Any]:
    text = fetch_text(url)
    if not text:
        return {"status": "ERROR", "source_url": url}
    out = save_text(city_slug, "catalog_raw.html", text)
    metadata = {
        "source_name": source_name,
        "access_type": "HTML",
        "source_url": url,
        "collected_at": now(),
        "output": str(out),
        "note": "Catalogo descargado como HTML; requiere parser especifico si no existe API publica estable.",
    }
    save_json(city_slug, "catalog_metadata.json", metadata)
    return {"status": "PARTIAL", "output": str(out), "metadata": metadata["note"]}


def text_catalog(city_slug: str, source_name: str, url: str, filename: str = "catalog_raw.txt") -> dict[str, Any]:
    text = fetch_text(url)
    if not text:
        return {"status": "ERROR", "source_url": url}
    out = save_text(city_slug, filename, text)
    metadata = {
        "source_name": source_name,
        "access_type": "TEXT/RDF",
        "source_url": url,
        "collected_at": now(),
        "output": str(out),
    }
    save_json(city_slug, "catalog_metadata.json", metadata)
    return {"status": "OK", "output": str(out)}


def print_result(result: dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))
