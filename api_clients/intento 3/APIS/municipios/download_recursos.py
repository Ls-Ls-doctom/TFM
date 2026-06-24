from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse


BASE_DIR = Path(__file__).resolve().parents[2]
BRONZE_DIR = BASE_DIR / "data_lake" / "bronze" / "municipios"
REPORTS_DIR = BASE_DIR / "reports"
USER_AGENT = "ISEU-TFM-Municipios-Downloader/3.0"
DEFAULT_SINCE_YEAR = 2010
MAX_RESOURCE_MB = int(os.getenv("ISEU3_MAX_RESOURCE_MB", "250"))

STRUCTURED_FORMATS = {
    "csv",
    "json",
    "geojson",
    "xls",
    "xlsx",
    "xml",
    "zip",
    "wfs",
    "shp",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Descarga recursos estructurados encontrados en catálogos municipales.")
    parser.add_argument("cities", nargs="*", help="barcelona valencia malaga zaragoza madrid bilbao sevilla")
    parser.add_argument("--since", type=int, default=DEFAULT_SINCE_YEAR, help="Año mínimo orientativo para metadatos históricos.")
    parser.add_argument("--max-resources", type=int, default=0, help="Límite opcional de recursos por ejecución. 0 = sin límite.")
    args = parser.parse_args()

    cities = args.cities or sorted(path.name for path in BRONZE_DIR.iterdir() if path.is_dir())
    manifest_path = REPORTS_DIR / "municipios_resources_manifest.json"
    manifest: list[dict[str, Any]] = load_existing_manifest(manifest_path)
    for city in cities:
        print(f"\n=== Descarga recursos {city} ===")
        resources = discover_city_resources(city, args.since)
        print(f"  recursos detectados: {len(resources)}")
        downloaded = 0
        for resource in resources:
            if args.max_resources and downloaded >= args.max_resources:
                resource["download_status"] = "SKIPPED_LIMIT"
                manifest.append(resource)
                write_manifest(manifest_path, manifest, args.since)
                continue
            result = download_resource(city, resource)
            manifest.append(result)
            write_manifest(manifest_path, manifest, args.since)
            if result.get("download_status") in {"OK", "OK_CACHED"}:
                downloaded += 1
        print(f"  descargados OK: {downloaded}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    write_manifest(manifest_path, manifest, args.since)
    print(f"\nManifest: {manifest_path}")
    return 0


def write_manifest(path: Path, manifest: list[dict[str, Any]], since_year: int) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in manifest:
        key = (
            str(item.get("city", "")),
            str(item.get("resource_url", "")),
            str(item.get("local_path", "")),
        )
        deduped[key] = item
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "since_year": since_year,
        "max_resource_mb": MAX_RESOURCE_MB,
        "resources": list(deduped.values()),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_existing_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    resources = payload.get("resources", [])
    return resources if isinstance(resources, list) else []


def discover_city_resources(city: str, since_year: int) -> list[dict[str, Any]]:
    city_path = BRONZE_DIR / city
    resources: list[dict[str, Any]] = []
    search_path = city_path / "catalog_search_raw.json"
    if search_path.exists():
        resources.extend(discover_ckan_resources(city, search_path, since_year))
    catalog_path = city_path / "catalog_raw.json"
    if catalog_path.exists():
        resources.extend(discover_json_catalog_resources(city, catalog_path, since_year))
    html_path = city_path / "catalog_raw.html"
    if html_path.exists():
        resources.extend(discover_html_resources(city, html_path, since_year))
    return dedupe_resources(resources)


def discover_ckan_resources(city: str, path: Path, since_year: int) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    output = []
    for query in data.get("results", []):
        ckan = query.get("data") or {}
        packages = (ckan.get("result") or {}).get("results") or []
        for package in packages:
            package_date = first_date(package, ("metadata_modified", "metadata_created", "fecha_publicacion"))
            if package_date and package_date.year < since_year:
                continue
            for resource in package.get("resources", []):
                url = resource.get("url") or resource.get("downloadURL") or resource.get("accessURL")
                fmt = normalize_format(resource.get("format") or resource.get("mimetype") or resource.get("mediaType") or url)
                if not url or not is_structured(fmt, url):
                    continue
                output.append(
                    {
                        "city": city,
                        "source_type": "ckan",
                        "search_term": query.get("term", ""),
                        "dataset_id": package.get("id", ""),
                        "dataset_name": package.get("name") or package.get("title", ""),
                        "dataset_title": package.get("title", ""),
                        "dataset_modified": package.get("metadata_modified", ""),
                        "resource_id": resource.get("id", ""),
                        "resource_name": resource.get("name") or resource.get("title", ""),
                        "format": fmt,
                        "url": url,
                    }
                )
    return output


def discover_json_catalog_resources(city: str, path: Path, since_year: int) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    data = payload.get("data", payload)
    output = []
    if city == "zaragoza":
        for item in data.get("result", []):
            item_date = first_date(item, ("modified", "issued", "lastUpdated"))
            if item_date and item_date.year < since_year:
                continue
            for resource in item.get("formato") or []:
                url = resource.get("downloadURL") or resource.get("accessURL")
                if url and url.startswith("/"):
                    url = urljoin("https://www.zaragoza.es", url)
                fmt = normalize_format(resource.get("mediaType") or resource.get("title") or url)
                if not url or not is_structured(fmt, url):
                    continue
                output.append(
                    {
                        "city": city,
                        "source_type": "json_catalog",
                        "dataset_id": str(item.get("id", "")),
                        "dataset_name": safe_text(item.get("name") or item.get("title", "")),
                        "dataset_title": safe_text(item.get("title", "")),
                        "dataset_modified": item.get("modified") or item.get("lastUpdated") or "",
                        "resource_id": str(resource.get("id", "")),
                        "resource_name": safe_text(resource.get("title", "")),
                        "format": fmt,
                        "url": url,
                    }
                )
    elif city == "sevilla":
        features = data.get("features") or []
        for feature in features:
            props = feature.get("properties") or {}
            item_date = epoch_year(props.get("modified") or props.get("created"))
            if item_date and item_date < since_year:
                continue
            title = safe_text(props.get("title") or props.get("name") or feature.get("id"))
            service_url = safe_text(props.get("url"))
            item_id = safe_text(props.get("id") or feature.get("id"))
            item_type = safe_text(props.get("type"))
            if service_url and "FeatureServer" in service_url:
                output.append(
                    {
                        "city": city,
                        "source_type": "arcgis_hub",
                        "dataset_id": item_id,
                        "dataset_name": title,
                        "dataset_title": title,
                        "dataset_modified": str(props.get("modified") or ""),
                        "resource_id": f"{item_id}_geojson",
                        "resource_name": f"{title}_geojson",
                        "format": "GEOJSON",
                        "url": arcgis_feature_geojson_url(service_url),
                    }
                )
            for link in feature.get("links") or []:
                url = link.get("href")
                fmt = normalize_format(link.get("type") or link.get("title") or url)
                if not url or not is_structured(fmt, url):
                    continue
                output.append(
                    {
                        "city": city,
                        "source_type": "arcgis_hub_link",
                        "dataset_id": item_id,
                        "dataset_name": title,
                        "dataset_title": title,
                        "dataset_modified": str(props.get("modified") or ""),
                        "resource_id": safe_text(link.get("rel") or item_id),
                        "resource_name": safe_text(link.get("title") or title),
                        "format": fmt,
                        "url": url,
                    }
                )
    return output


def discover_html_resources(city: str, path: Path, since_year: int) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    parser = LinkParser()
    parser.feed(text)
    output = []
    for index, url in enumerate(parser.links):
        full_url = urljoin(str(path), url)
        fmt = normalize_format(full_url)
        if not is_structured(fmt, full_url):
            continue
        output.append(
            {
                "city": city,
                "source_type": "html_link",
                "dataset_id": f"html_{index}",
                "dataset_name": safe_filename(Path(urlparse(full_url).path).stem or f"html_{index}"),
                "dataset_title": "",
                "dataset_modified": "",
                "resource_id": f"html_{index}",
                "resource_name": safe_filename(Path(urlparse(full_url).path).name or f"html_{index}"),
                "format": fmt,
                "url": full_url,
            }
        )
    return output


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name.lower() in {"href", "src"} and value:
                self.links.append(value)


def download_resource(city: str, resource: dict[str, Any]) -> dict[str, Any]:
    result = dict(resource)
    url = resource["url"]
    folder = BRONZE_DIR / city / "resources" / safe_filename(resource.get("dataset_name") or resource.get("dataset_id") or "dataset")
    folder.mkdir(parents=True, exist_ok=True)
    ext = extension_for(resource.get("format", ""), url)
    filename = safe_filename(resource.get("resource_name") or resource.get("resource_id") or hashlib.sha1(url.encode()).hexdigest())
    if not filename.lower().endswith(ext):
        filename += ext
    path = folder / filename
    result["local_path"] = str(path)
    if path.exists() and path.stat().st_size > 0:
        result["download_status"] = "OK_CACHED"
        result["bytes"] = path.stat().st_size
        return result
    try:
        with open_url(url) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_RESOURCE_MB * 1024 * 1024:
                result["download_status"] = "SKIPPED_TOO_LARGE"
                result["bytes_expected"] = int(length)
                return result
            content = read_limited(response, MAX_RESOURCE_MB * 1024 * 1024)
        if content is None:
            result["download_status"] = "SKIPPED_TOO_LARGE"
            result["bytes_expected"] = f">{MAX_RESOURCE_MB}MB"
            return result
        path.write_bytes(content)
        result["download_status"] = "OK"
        result["bytes"] = len(content)
        result["sha256"] = hashlib.sha256(content).hexdigest()
    except Exception as exc:
        result["download_status"] = "ERROR"
        result["error"] = str(exc)
    return result


def read_limited(response, max_bytes: int) -> bytes | None:
    chunks = []
    total = 0
    while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def open_url(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        return urllib.request.urlopen(req, timeout=120, context=ssl_context(True))
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            return urllib.request.urlopen(req, timeout=120, context=ssl_context(False))
        raise


def ssl_context(verify: bool) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if not verify or os.getenv("ISEU3_DISABLE_SSL_VERIFY", "0") == "1":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def dedupe_resources(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for resource in resources:
        key = resource.get("url")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(resource)
    return deduped


def is_structured(fmt: str, url: str) -> bool:
    text = f"{fmt} {url}".lower()
    return any(token in text for token in STRUCTURED_FORMATS)


def normalize_format(value: Any) -> str:
    text = safe_text(value).lower()
    for fmt in ("geojson", "json", "csv", "xlsx", "xls", "xml", "zip", "wfs", "shp"):
        if fmt in text:
            return fmt.upper()
    suffix = Path(urlparse(text).path).suffix.lower().strip(".")
    return suffix.upper() if suffix else safe_text(value).upper()


def extension_for(fmt: str, url: str) -> str:
    suffix = Path(urlparse(url).path).suffix
    if suffix and len(suffix) <= 8:
        return suffix
    mapping = {
        "CSV": ".csv",
        "JSON": ".json",
        "GEOJSON": ".geojson",
        "XLS": ".xls",
        "XLSX": ".xlsx",
        "XML": ".xml",
        "ZIP": ".zip",
        "WFS": ".xml",
        "SHP": ".zip",
    }
    return mapping.get(fmt.upper(), ".dat")


def first_date(item: dict[str, Any], keys: tuple[str, ...]):
    for key in keys:
        value = item.get(key)
        if not value:
            continue
        match = re.search(r"(20\d{2}|19\d{2})", str(value))
        if match:
            return datetime(int(match.group(1)), 1, 1)
    return None


def epoch_year(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number > 10_000_000_000:
        return datetime.fromtimestamp(number / 1000).year
    if number > 10_000_000:
        return datetime.fromtimestamp(number).year
    return None


def arcgis_feature_geojson_url(service_url: str) -> str:
    base = service_url.rstrip("/")
    if not re.search(r"/FeatureServer/\d+$", base, flags=re.IGNORECASE):
        base = f"{base}/0"
    return f"{base}/query?{urlencode({'where': '1=1', 'outFields': '*', 'f': 'geojson'})}"


def safe_filename(value: Any) -> str:
    text = safe_text(value)
    text = re.sub(r"[^\w\-\.]+", "_", text, flags=re.UNICODE).strip("_")
    return text[:120] or "resource"


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


if __name__ == "__main__":
    raise SystemExit(main())
