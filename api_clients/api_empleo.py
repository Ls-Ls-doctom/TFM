"""
Cliente de empleo: SEPE + Seguridad Social.

SEPE no ofrece una API REST publica estable para paro/contratos municipales,
pero publica ficheros XLS mensuales enlazados desde su portal. Este cliente
descubre los meses disponibles, descarga los XLS nacionales y normaliza hojas
de paro registrado y contratos por municipio.
"""
from __future__ import annotations

import re
import ssl
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd

from config import DATA_DIR, SEPE_MAX_MONTHS
from utils import save_csv, save_json, timestamp


SEPE_MUNICIPIOS_URL = (
    "https://www.sepe.es/HomeSepe/que-es-el-sepe/estadisticas/"
    "datos-estadisticos/municipios.html"
)
SS_URL = "https://www.seg-social.es/wps/portal/wss/internet/EstadisticasPresupuestosEstudios/Estadisticas"

MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

SEPE_PARO_COLUMNS = [
    "codigo_municipio",
    "municipio",
    "paro_total",
    "hombres_menor_25",
    "hombres_25_44",
    "hombres_45_mas",
    "mujeres_menor_25",
    "mujeres_25_44",
    "mujeres_45_mas",
    "sector_agricultura",
    "sector_industria",
    "sector_construccion",
    "sector_servicios",
    "sin_empleo_anterior",
]

SEPE_CONTRATOS_COLUMNS = [
    "codigo_municipio",
    "municipio",
    "contratos_total",
    "hombres_indefinido_inicial",
    "hombres_temporal_inicial",
    "hombres_indefinido_convertido",
    "mujeres_indefinido_inicial",
    "mujeres_temporal_inicial",
    "mujeres_indefinido_convertido",
    "sector_agricultura",
    "sector_industria",
    "sector_construccion",
    "sector_servicios",
]

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


class LinkParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._current = {"href": urljoin(self.base_url, href), "text": ""}

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["text"] += data.strip() + " "

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current is not None:
            self._current["text"] = self._current["text"].strip()
            self.links.append(self._current)
            self._current = None


def scrape_empleo() -> dict:
    """Ejecuta scrapers de empleo."""
    print(f"\n{'=' * 60}")
    print(f"SCRAPERS EMPLEO (SEPE + SS) - {timestamp()}")
    print(f"{'=' * 60}")

    resultados = {
        "sepe_paro": scrape_sepe_paro(),
        "ss_afiliacion": scrape_ss_afiliacion(),
    }

    manuales = sum(1 for item in resultados.values() if item.get("estado") == "MANUAL")
    save_json(
        {
            "fuente": "SEPE + Seguridad Social",
            "timestamp": timestamp(),
            "resultados": resultados,
            "nota": "SEPE queda automatizado mediante descarga XLS; Seguridad Social pendiente de automatizar.",
        },
        "empleo_log.json",
        "empleo",
    )

    print(f"\nResumen Empleo: SEPE automatizado | {manuales} fuente(s) manual(es)")
    return resultados


def scrape_sepe_paro() -> dict:
    print("\n[sepe_paro] Paro registrado y contratos municipales")
    print("  Fuente: SEPE - Estadisticas por municipios")
    print(f"  Meses a recuperar: {SEPE_MAX_MONTHS}")

    months = discover_sepe_months(SEPE_MUNICIPIOS_URL)
    selected = months[-SEPE_MAX_MONTHS:]
    if not selected:
        return {"estado": "ERROR", "filas": 0, "nota": "No se encontraron enlaces mensuales SEPE"}

    folder = DATA_DIR / "empleo" / "sepe_xls"
    folder.mkdir(parents=True, exist_ok=True)

    paro_rows: list[dict] = []
    contratos_rows: list[dict] = []
    downloads: list[dict] = []

    for item in selected:
        try:
            xls_url = find_monthly_xls(item["url"])
            if not xls_url:
                downloads.append({**item, "estado": "SIN_XLS"})
                continue

            filename = f"sepe_municipios_{item['year']}_{item['month']:02d}.xls"
            path = download_file(xls_url, folder / filename)
            downloads.append({**item, "estado": "OK", "url_xls": xls_url, "archivo": str(path)})

            parsed = parse_sepe_workbook(path, item["year"], item["month"], xls_url)
            paro_rows.extend(parsed["paro"])
            contratos_rows.extend(parsed["contratos"])
            print(
                f"  {item['year']}-{item['month']:02d}: "
                f"{len(parsed['paro'])} paro | {len(parsed['contratos'])} contratos"
            )
            time.sleep(0.2)
        except Exception as exc:
            downloads.append({**item, "estado": "ERROR", "error": str(exc)})
            print(f"  Error SEPE {item['year']}-{item['month']:02d}: {exc}")

    save_csv(paro_rows, "sepe_paro_raw.csv", "empleo")
    save_csv(contratos_rows, "sepe_contratos_raw.csv", "empleo")
    save_json(downloads, "sepe_descargas.json", "empleo")

    estado = "OK" if paro_rows or contratos_rows else "ERROR"
    return {
        "estado": estado,
        "filas_paro": len(paro_rows),
        "filas_contratos": len(contratos_rows),
        "meses_descargados": sum(1 for item in downloads if item.get("estado") == "OK"),
        "meses_intentados": len(selected),
    }


def scrape_ss_afiliacion() -> dict:
    print("\n[ss_afiliacion] Afiliacion Seguridad Social")
    print("  Fuente: Seguridad Social - Afiliacion por municipio")
    print("  Estado: pendiente de automatizar en el siguiente paso")
    print(f"  URL: {SS_URL}")
    return {"estado": "MANUAL", "filas": 0, "nota": "Descarga XLSX mensual pendiente de automatizar"}


def discover_sepe_months(url: str) -> list[dict]:
    links = parse_links(fetch_text(url), url)
    months: dict[tuple[int, int], dict] = {}

    for link in links:
        href = link["href"]
        match = re.search(r"/municipios/(\d{4})/([a-z]+)(?:-\d{4})?\.html", href, re.IGNORECASE)
        if not match:
            continue
        year = int(match.group(1))
        month_name = match.group(2).lower()
        month = MONTHS.get(month_name)
        if not month:
            continue
        period_date = date(year, month, 1)
        if period_date > date.today().replace(day=1):
            continue
        months[(year, month)] = {
            "year": year,
            "month": month,
            "period": f"{year}-{month:02d}",
            "url": href,
        }

    return [months[key] for key in sorted(months)]


def find_monthly_xls(month_url: str) -> str | None:
    links = parse_links(fetch_text(month_url), month_url)
    national = [
        link["href"]
        for link in links
        if "ESTADISTICA_MUNICIPIOS" in link["href"].upper() and link["href"].lower().endswith(".xls")
    ]
    if national:
        return national[0]
    candidates = [link["href"] for link in links if link["href"].lower().endswith((".xls", ".xlsx"))]
    return candidates[0] if candidates else None


def parse_sepe_workbook(path: Path, year: int, month: int, source_url: str) -> dict[str, list[dict]]:
    xls = pd.ExcelFile(path)
    extracted_at = timestamp()
    paro_rows: list[dict] = []
    contratos_rows: list[dict] = []

    for sheet in xls.sheet_names:
        sheet_upper = sheet.upper()
        if not sheet_upper.startswith(("PARO ", "CONTRATOS ")):
            continue

        raw = pd.read_excel(path, sheet_name=sheet, header=None)
        if sheet_upper.startswith("PARO "):
            rows = parse_sheet(raw, SEPE_PARO_COLUMNS, "paro", sheet, year, month, source_url, extracted_at)
            paro_rows.extend(rows)
        else:
            rows = parse_sheet(raw, SEPE_CONTRATOS_COLUMNS, "contratos", sheet, year, month, source_url, extracted_at)
            contratos_rows.extend(rows)

    return {"paro": paro_rows, "contratos": contratos_rows}


def parse_sheet(
    raw: pd.DataFrame,
    columns: list[str],
    tipo: str,
    sheet: str,
    year: int,
    month: int,
    source_url: str,
    extracted_at: str,
) -> list[dict]:
    rows: list[dict] = []
    province = sheet.replace("PARO ", "").replace("CONTRATOS ", "").strip().title()

    for _, row in raw.iloc[8:].iterrows():
        municipality = row.get(1)
        code = row.get(0)
        if pd.isna(municipality):
            continue
        municipality = str(municipality).strip()
        if not municipality or municipality.upper() in {"MUNICIPIOS", "TOTAL"}:
            continue

        values = {}
        censored = False
        for idx, column in enumerate(columns):
            value = row.get(idx)
            if idx == 0:
                values[column] = parse_code(value)
            elif idx == 1:
                values[column] = municipality
            else:
                parsed, is_censored = parse_sepe_number(value)
                values[column] = parsed
                censored = censored or is_censored

        values.update(
            {
                "tipo": tipo,
                "provincia": province,
                "periodo": f"{year}-{month:02d}",
                "anio": year,
                "mes": month,
                "es_total_provincia": pd.isna(code),
                "contiene_valores_censurados": censored,
                "fuente": "SEPE",
                "url_fuente": source_url,
                "extraido_en": extracted_at,
            }
        )
        rows.append(values)

    return rows


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "ISEU-TFM-Barcelona/1.0"})
    with urllib.request.urlopen(req, timeout=60, context=_ssl_ctx) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def download_file(url: str, path: Path) -> Path:
    if path.exists() and path.stat().st_size > 0:
        return path
    req = urllib.request.Request(url, headers={"User-Agent": "ISEU-TFM-Barcelona/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=90, context=_ssl_ctx) as resp:
            path.write_bytes(resp.read())
    except urllib.error.URLError:
        if path.exists():
            path.unlink()
        raise
    return path


def parse_links(html: str, base_url: str) -> list[dict[str, str]]:
    parser = LinkParser(base_url)
    parser.feed(html)
    return parser.links


def parse_code(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value)).zfill(5)
    text = str(value).strip()
    return text.zfill(5) if text.isdigit() else text


def parse_sepe_number(value) -> float | tuple[float | None, bool]:
    if pd.isna(value):
        return None, False
    text = str(value).strip()
    if not text:
        return None, False
    if text.startswith("<"):
        return 2.5, True
    text = text.replace(".", "").replace(",", ".")
    try:
        return float(text), False
    except ValueError:
        return None, False


if __name__ == "__main__":
    scrape_empleo()
