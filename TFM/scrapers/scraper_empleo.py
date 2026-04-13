"""
Scraper: SEPE + Seguridad Social
Portales de empleo y afiliación.

Cubre: paro registrado (joven), afiliación SS por municipio.
Los datos suelen estar en CSV/XLSX descargables mensualmente.
"""
from utils import fetch_json, fetch_csv_text, save_json, save_csv, timestamp
import csv
import io


def scrape_sepe_paro():
    """
    Scraper de paro registrado del SEPE.
    El SEPE publica datos mensuales por municipio en su portal de estadísticas.
    URL de referencia: https://www.sepe.es/HomeSepe/que-es-el-sepe/estadisticas/datos-avance/paro.html
    
    NOTA: El SEPE no tiene API REST pública estable. Los datos se descargan
    como ficheros mensuales. Aquí se documenta el proceso y se prepara
    la estructura de descarga.
    """
    print(f"\n[sepe_paro] Paro registrado Barcelona")
    print(f"  Fuente: SEPE - Datos de paro registrado por municipio")
    print(f"  ⚠ El SEPE no tiene API pública. Descarga manual requerida.")
    print(f"  URL: https://www.sepe.es/HomeSepe/que-es-el-sepe/estadisticas/datos-avance/paro.html")
    print(f"  Proceso: descargar XLSX mensual → filtrar municipio 080193 (Barcelona)")

    return {"estado": "MANUAL", "filas": 0, "nota": "Descarga manual XLSX desde portal SEPE"}


def scrape_ss_afiliacion():
    """
    Scraper de afiliación a la Seguridad Social.
    Datos de afiliados por municipio y régimen.
    URL: https://www.seg-social.es/wps/portal/wss/internet/EstadisticasPresupuestosEstudios/Estadisticas
    
    NOTA: No hay API REST pública. Los datos se publican en PDF y XLSX.
    """
    print(f"\n[ss_afiliacion] Afiliación Seguridad Social Barcelona")
    print(f"  Fuente: Seguridad Social - Afiliación por municipio")
    print(f"  ⚠ Sin API pública. Descarga manual requerida.")
    print(f"  URL: https://www.seg-social.es")
    print(f"  Alternativa: Open Data BCN publica afiliación por distrito")

    return {"estado": "MANUAL", "filas": 0, "nota": "Descarga manual o usar Open Data BCN"}


def scrape_empleo():
    """Ejecuta scrapers de empleo (SEPE + SS)."""
    print(f"\n{'='*60}")
    print(f"SCRAPERS EMPLEO (SEPE + SS) - {timestamp()}")
    print(f"{'='*60}")

    resultados = {
        "sepe_paro": scrape_sepe_paro(),
        "ss_afiliacion": scrape_ss_afiliacion(),
    }

    save_json({
        "fuente": "SEPE + Seguridad Social",
        "timestamp": timestamp(),
        "resultados": resultados,
        "nota": "Estas fuentes requieren descarga manual. Ver URLs en resultados.",
    }, "empleo_log.json", "empleo")

    print(f"\nResumen Empleo: Ambas fuentes requieren descarga manual")
    return resultados


if __name__ == "__main__":
    scrape_empleo()
