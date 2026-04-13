"""
Configuración central de los scrapers ISEU+ Barcelona.
Define variables, fuentes, mapeos y rutas de salida.
"""
import os
from pathlib import Path

# --- Rutas ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# --- Configuración de fuentes ---
FUENTES = {
    "ine": {
        "nombre": "INE (Instituto Nacional de Estadística)",
        "base_url": "https://servicios.ine.es/wstempus/js/ES",
        "tipo": "API JSON",
        "doc": "https://www.ine.es/dyngs/DataLab/manual.html?cid=1259945948443",
    },
    "idescat": {
        "nombre": "Idescat (Estadísticas de Cataluña)",
        "base_url": "https://api.idescat.cat",
        "tipo": "API JSON",
        "doc": "https://www.idescat.cat/api/",
    },
    "opendata_bcn": {
        "nombre": "Open Data BCN (Ajuntament de Barcelona)",
        "base_url": "https://opendata-ajuntament.barcelona.cat/data/api/action",
        "tipo": "CKAN API / CSV",
        "doc": "https://opendata-ajuntament.barcelona.cat/data/es/",
    },
    "mitma": {
        "nombre": "MITMA (Ministerio Transportes - Vivienda)",
        "base_url": "https://www.mitma.gob.es",
        "tipo": "CSV / Portal descarga",
        "doc": "https://www.mitma.gob.es/vivienda",
    },
    "ree": {
        "nombre": "REE (Red Eléctrica de España)",
        "base_url": "https://apidatos.ree.es",
        "tipo": "API JSON",
        "doc": "https://www.ree.es/es/apidatos",
    },
    "sepe": {
        "nombre": "SEPE (Servicio Público de Empleo)",
        "base_url": "https://www.sepe.es",
        "tipo": "CSV / Portal descarga",
        "doc": "https://www.sepe.es/HomeSepe/que-es-el-sepe/estadisticas",
    },
    "seg_social": {
        "nombre": "Seguridad Social",
        "base_url": "https://w6.seg-social.es",
        "tipo": "CSV / Portal descarga",
        "doc": "https://www.seg-social.es/wps/portal/wss/internet/EstadisticasPresupuestosEstudios/Estadisticas",
    },
    "bde": {
        "nombre": "Banco de España",
        "base_url": "https://www.bde.es/webbe/es/estadisticas",
        "tipo": "CSV / API",
        "doc": "https://www.bde.es/webbe/es/estadisticas/",
    },
}

# --- Catálogo de las 60 variables con mapeo a fuente y scraper ---
# Formato: (variable, pilar, polaridad, viabilidad, fuente_principal, scraper_id, mvp)
VARIABLES = [
    # === CAPACIDAD DE CONSUMO ===
    ("Ingreso disponible per cápita", "Capacidad de consumo", "+", "Media", "ine", "ine_renta", True),
    ("Salario medio bruto", "Capacidad de consumo", "+", "Alta", "ine", "ine_salarios", True),
    ("Salario mediano", "Capacidad de consumo", "+", "Media", "ine", "ine_salarios", False),
    ("Tasa de ahorro", "Capacidad de consumo", "+", "Baja", "bde", "bde_ahorro", False),
    ("Crédito al consumo", "Capacidad de consumo", "+", "Baja", "bde", "bde_credito", False),
    ("Índice de confianza del consumidor", "Capacidad de consumo", "+", "Baja", "ine", "ine_confianza", False),
    ("Ventas retail", "Capacidad de consumo", "+", "Alta", "ine", "ine_comercio", True),
    ("Gasto medio por hogar", "Capacidad de consumo", "+", "Media", "ine", "ine_epf", True),
    ("Consumo con tarjeta", "Capacidad de consumo", "+", "Baja", None, None, False),
    ("Inflación ajustada (IPC real)", "Capacidad de consumo", "+", "Alta", "ine", "ine_ipc", True),

    # === COSTE DE VIDA ===
    ("Precio alquiler medio", "Coste de vida", "-", "Alta", "opendata_bcn", "bcn_alquiler", True),
    ("Precio vivienda m2", "Coste de vida", "-", "Alta", "mitma", "mitma_vivienda", True),
    ("Coste energético hogar", "Coste de vida", "-", "Media", "ree", "ree_precio", False),
    ("Precio electricidad", "Coste de vida", "-", "Alta", "ree", "ree_precio", True),
    ("Precio gas", "Coste de vida", "-", "Media", "ine", "ine_ipc", False),
    ("Cesta básica alimentos", "Coste de vida", "-", "Media", "ine", "ine_ipc", False),
    ("Transporte público coste", "Coste de vida", "-", "Alta", "opendata_bcn", "bcn_transporte", True),
    ("Coste sanitario privado", "Coste de vida", "-", "Baja", None, None, False),
    ("Inflación alimentaria", "Coste de vida", "-", "Alta", "ine", "ine_ipc", False),
    ("Índice general IPC", "Coste de vida", "-", "Alta", "ine", "ine_ipc", False),

    # === DINAMISMO ECONÓMICO ===
    ("PIB regional", "Dinamismo económico", "+", "Alta", "idescat", "idescat_pib", False),
    ("Crecimiento PIB", "Dinamismo económico", "+", "Alta", "idescat", "idescat_pib", False),
    ("Creación de empresas", "Dinamismo económico", "+", "Alta", "ine", "ine_empresas", True),
    ("Cierre de empresas", "Dinamismo económico", "-", "Media", "ine", "ine_empresas", False),
    ("Inversión extranjera", "Dinamismo económico", "+", "Media", "ine", "ine_datainvex", False),
    ("Licencias comerciales", "Dinamismo económico", "+", "Alta", "opendata_bcn", "bcn_licencias", True),
    ("Turismo (nº visitantes)", "Dinamismo económico", "+", "Alta", "opendata_bcn", "bcn_turismo", True),
    ("Ocupación hotelera", "Dinamismo económico", "+", "Alta", "ine", "ine_turismo", True),
    ("Consumo eléctrico industrial", "Dinamismo económico", "+", "Media", "ree", "ree_demanda", False),
    ("Índice actividad servicios", "Dinamismo económico", "+", "Media", "ine", "ine_servicios", False),

    # === MERCADO LABORAL ===
    ("Tasa de paro", "Mercado laboral", "-", "Alta", "ine", "ine_epa", True),
    ("Paro juvenil", "Mercado laboral", "-", "Alta", "sepe", "sepe_paro", True),
    ("Tasa de empleo", "Mercado laboral", "+", "Alta", "ine", "ine_epa", True),
    ("Temporalidad", "Mercado laboral", "-", "Alta", "ine", "ine_epa", False),
    ("Salario mínimo vs medio", "Mercado laboral", "+", "Alta", "ine", "ine_salarios", False),
    ("Vacantes laborales", "Mercado laboral", "+", "Media", "ine", "ine_epa", False),
    ("Rotación laboral", "Mercado laboral", "-", "Media", "seg_social", "ss_afiliacion", False),
    ("Horas trabajadas", "Mercado laboral", "+", "Media", "ine", "ine_epa", False),
    ("Productividad laboral", "Mercado laboral", "+", "Media", "idescat", "idescat_pib", False),
    ("Afiliación a seguridad social", "Mercado laboral", "+", "Alta", "seg_social", "ss_afiliacion", True),

    # === ACCESIBILIDAD Y BIENESTAR ===
    ("Ratio precio vivienda / ingresos", "Accesibilidad y bienestar", "-", "Alta", "ine", "ine_calculada", True),
    ("Índice Gini", "Accesibilidad y bienestar", "-", "Media", "ine", "ine_condiciones_vida", False),
    ("Acceso a salud", "Accesibilidad y bienestar", "+", "Media", "opendata_bcn", "bcn_equipamientos", False),
    ("Acceso a educación", "Accesibilidad y bienestar", "+", "Media", "opendata_bcn", "bcn_equipamientos", False),
    ("Esperanza de vida", "Accesibilidad y bienestar", "+", "Alta", "idescat", "idescat_demografia", True),
    ("Seguridad ciudadana", "Accesibilidad y bienestar", "+", "Media", "opendata_bcn", "bcn_seguridad", False),
    ("Índice de pobreza", "Accesibilidad y bienestar", "-", "Media", "ine", "ine_condiciones_vida", False),
    ("Calidad del aire", "Accesibilidad y bienestar", "+", "Alta", "opendata_bcn", "bcn_aire", True),
    ("Zonas verdes por habitante", "Accesibilidad y bienestar", "+", "Alta", "opendata_bcn", "bcn_zonas_verdes", True),
    ("Movilidad urbana", "Accesibilidad y bienestar", "+", "Alta", "opendata_bcn", "bcn_movilidad", True),

    # === ENTORNO EMPRESARIAL ===
    ("Coste apertura negocio", "Entorno empresarial", "-", "Media", "opendata_bcn", "bcn_licencias", False),
    ("Tiempo apertura empresa", "Entorno empresarial", "-", "Media", "opendata_bcn", "bcn_licencias", False),
    ("Presión fiscal", "Entorno empresarial", "-", "Media", "opendata_bcn", "bcn_fiscal", False),
    ("Coste laboral empresa", "Entorno empresarial", "-", "Alta", "ine", "ine_salarios", True),
    ("Precio alquiler comercial", "Entorno empresarial", "-", "Media", "opendata_bcn", "bcn_alquiler", True),
    ("Densidad empresarial", "Entorno empresarial", "+", "Alta", "ine", "ine_empresas", True),
    ("Competencia sectorial", "Entorno empresarial", "+", "Media", "ine", "ine_empresas", False),
    ("Digitalización empresas", "Entorno empresarial", "+", "Media", "ine", "ine_tic", False),
    ("Acceso a financiación", "Entorno empresarial", "+", "Baja", "bde", "bde_credito", False),
    ("Índice facilidad negocios", "Entorno empresarial", "+", "Baja", None, None, False),
]
