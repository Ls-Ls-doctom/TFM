from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
BRONZE_APIS_DIR = BASE_DIR / "data_lake" / "bronze" / "apis"
REPORTS_DIR = BASE_DIR / "reports"
USER_AGENT = "ISEU-TFM-APIS/3.0"


def api_dir(api_name: str) -> Path:
    path = BRONZE_APIS_DIR / api_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_manifest(api_name: str, payload: dict[str, Any]) -> Path:
    out = api_dir(api_name) / "manifest_raw.json"
    payload = {
        "api": api_name,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        **payload,
    }
    write_json(out, payload)
    return out


def fetch_json(url: str, timeout: int = 120, headers: dict[str, str] | None = None) -> Any:
    request = urllib.request.Request(url, headers=request_headers(headers))
    with urllib.request.urlopen(request, timeout=timeout, context=ssl_context()) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def fetch_text(url: str, timeout: int = 120, headers: dict[str, str] | None = None) -> str:
    request = urllib.request.Request(url, headers=request_headers(headers))
    with urllib.request.urlopen(request, timeout=timeout, context=ssl_context()) as response:
        return response.read().decode("utf-8", "replace")


def download_url(
    url: str,
    output_path: Path,
    timeout: int = 180,
    headers: dict[str, str] | None = None,
    max_mb: int = 300,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "url": url,
        "local_path": str(output_path),
        "status": "PENDING",
    }
    if output_path.exists() and output_path.stat().st_size > 0:
        result["status"] = "OK_CACHED"
        result["bytes"] = output_path.stat().st_size
        return result
    try:
        request = urllib.request.Request(url, headers=request_headers(headers))
        with urllib.request.urlopen(request, timeout=timeout, context=ssl_context()) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > max_mb * 1024 * 1024:
                result["status"] = "SKIPPED_TOO_LARGE"
                result["content_length"] = int(length)
                return result
            output_path.parent.mkdir(parents=True, exist_ok=True)
            total = 0
            with output_path.open("wb") as fh:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_mb * 1024 * 1024:
                        fh.close()
                        output_path.unlink(missing_ok=True)
                        result["status"] = "SKIPPED_TOO_LARGE"
                        result["bytes"] = total
                        return result
                    fh.write(chunk)
            result["status"] = "OK"
            result["bytes"] = total
            result["content_type"] = response.headers.get("Content-Type")
            return result
    except urllib.error.HTTPError as exc:
        result["status"] = "ERROR"
        result["error"] = f"HTTP {exc.code}: {exc.reason}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        result["status"] = "ERROR"
        result["error"] = str(exc)
    return result


def datos_gob_title_search(title: str, page_size: int = 10) -> dict[str, Any]:
    encoded = urllib.parse.quote(title)
    url = f"https://datos.gob.es/apidata/catalog/dataset/title/{encoded}.json?_pageSize={page_size}"
    payload = fetch_json(url, headers={"Accept": "application/json"})
    return {"url": url, "payload": payload}


def get_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("result", {}).get("items", [])
    return items if isinstance(items, list) else []


def get_text(value: Any) -> str:
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("_value", "")))
            else:
                parts.append(str(item))
        return " ".join(part for part in parts if part)
    if isinstance(value, dict):
        return str(value.get("_value", ""))
    return "" if value is None else str(value)


def extract_year(text: str) -> int | None:
    match = re.search(r"(20\d{2}|19\d{2})", text)
    return int(match.group(1)) if match else None


def safe_name(value: str, fallback: str = "resource") -> str:
    value = value.strip().replace("\\", "/").split("/")[-1]
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return value[:150] or fallback


def extension_from_url(url: str, default: str = ".dat") -> str:
    path = urllib.parse.urlparse(url).path
    suffix = Path(path).suffix
    return suffix or default


def request_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT}
    if extra:
        headers.update(extra)
    return headers


def ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context()
