"""
Utilidades comunes para todos los scrapers ISEU+ Barcelona.
"""
import csv
import json
import ssl
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

from config import DATA_DIR

# Contexto SSL que acepta certificados de instituciones públicas españolas
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


def fetch_json(url: str, retries: int = 3, delay: float = 2.0) -> dict | list | None:
    """GET a JSON endpoint with retries and basic error handling."""
    headers = {
        "User-Agent": "ISEU-TFM-Barcelona/1.0",
        "Accept": "application/json",
    }
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30, context=_ssl_ctx) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"  [intento {attempt + 1}/{retries}] Error en {url}: {exc}")
            if attempt < retries - 1:
                time.sleep(delay)
    return None


def fetch_csv_text(url: str, retries: int = 3, delay: float = 2.0) -> str | None:
    """GET a CSV/text endpoint with retries."""
    headers = {"User-Agent": "ISEU-TFM-Barcelona/1.0"}
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60, context=_ssl_ctx) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"  [intento {attempt + 1}/{retries}] Error en {url}: {exc}")
            if attempt < retries - 1:
                time.sleep(delay)
    return None


def save_json(data, filename: str, subfolder: str = "") -> Path:
    """Save dict/list as JSON in data directory."""
    folder = DATA_DIR / subfolder if subfolder else DATA_DIR
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  -> Guardado: {path}")
    return path


def save_csv(rows: list[dict], filename: str, subfolder: str = "") -> Path:
    """Save list of dicts as CSV in data directory."""
    folder = DATA_DIR / subfolder if subfolder else DATA_DIR
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    if not rows:
        print(f"  -> Sin datos para {filename}")
        return path
    fieldnames = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  -> Guardado: {path} ({len(rows)} filas)")
    return path


def timestamp() -> str:
    """ISO timestamp for logs."""
    return datetime.now().isoformat(timespec="seconds")
