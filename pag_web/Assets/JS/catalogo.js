const menuButtons = document.querySelectorAll(".menu-button");
const sidebarBackdrop = document.querySelector(".sidebar-backdrop");
const sidebarLinks = document.querySelectorAll(".sidebar a");
const catalogSearch = document.querySelector("#catalogSearch");
const categoryChips = document.querySelector("#categoryChips");
const catalogGrid = document.querySelector("#catalogGrid");
const catalogCount = document.querySelector("#catalogCount");
const cityCoverageChart = document.querySelector("#cityCoverageChart");

const LOCAL_HOSTNAMES = new Set(["127.0.0.1", "localhost", "::1"]);
const isLocalPreview = window.location.protocol === "file:" || LOCAL_HOSTNAMES.has(window.location.hostname);
const API_URL = isLocalPreview ? "http://127.0.0.1:5500/api/dashboard" : "/api/dashboard";
const CACHE_KEY = "iseu-dashboard-v3";
const CACHE_TTL = 5 * 60 * 1000;

// Keys are the actual `variable` column values from iseu_indicadores (output of pipeline variable_label())
const VARIABLE_LABELS = {
  // SEPE / Open Data (snake_case originals, kept for fallback)
  "unemployed_registered":        "Paro registrado",
  "contracts_registered":         "Contratos registrados",
  "job_seekers":                  "Demandantes de empleo",
  "traffic_accidents":            "Accidentes de tráfico",
  "mobility_resources_records":   "Registros de movilidad compartida",
  // Spanish labels from pipeline variable_label() (missing accents/tildes → corrected here)
  "Paro registrado":              "Paro registrado",
  "Contratos registrados":        "Contratos registrados",
  "Demandantes de empleo":        "Demandantes de empleo",
  "Renta":                        "Renta bruta municipal",
  "Renta mediana":                "Renta mediana",
  "Renta por hogar":              "Renta por hogar",
  "Renta por persona":            "Renta per cápita (municipal)",
  "Registros de movilidad":       "Registros de movilidad compartida",
  "Desigualdad Gini":             "Índice de Gini",
  "Desigualdad P80/P20":          "Ratio P80/P20",
  "Accidentes de trafico":        "Accidentes de tráfico",
  "Poblacion total":              "Población total",
  "Poblacion residente":          "Población residente",
  "Edad mediana":                 "Edad mediana",
  "Esperanza de vida":            "Esperanza de vida",
  "Numero de hogares":            "Número de hogares",
  "Tamano medio del hogar":       "Tamaño medio del hogar",
  "Viviendas vacias":             "Viviendas vacías (%)",
  "Alquiler medio anual por m2":  "Alquiler medio anual (€/m²)",
  "Alquiler medio mensual":       "Alquiler medio mensual",
  "Mediana del alquiler mensual": "Mediana del alquiler mensual",
  "Precio medio de la vivienda":  "Precio medio de la vivienda",
  "Precio medio de vivienda por m2": "Precio medio por m² de vivienda",
  "Tasa de desempleo":            "Tasa de desempleo",
  "Tasa de actividad":            "Tasa de actividad",
  "Empleo en servicios":          "Empleo en el sector servicios (%)",
  "Empleo en industria":          "Empleo en industria (%)",
  "Renta neta media por hogar":   "Renta neta media del hogar",
  "Renta neta media por habitante": "Renta neta per cápita",
  "Renta neta por unidad de consumo": "Renta por unidad de consumo",
  "Desplazamientos al trabajo en coche": "Desplazamientos al trabajo en coche (%)",
  "Desplazamientos al trabajo a pie":    "Desplazamientos al trabajo a pie (%)",
  "Desplazamientos al trabajo en transporte publico": "Desplazamientos al trabajo en transporte público (%)",
  "Duracion del desplazamiento al trabajo": "Duración media del desplazamiento al trabajo",
  "Pernoctaciones turisticas":    "Pernoctaciones turísticas",
  "Plazas turisticas":            "Plazas en establecimientos turísticos",
  "Variacion anual del IPC general": "Variación anual del IPC general",
  "Variacion anual del IPC de alimentos": "Variación anual del IPC de alimentos",
  "Variacion anual del IPC de vivienda y energia": "Variación anual del IPC de vivienda y energía",
  "Variacion anual del IPC de transporte": "Variación anual del IPC de transporte",
  "Variacion anual del IPC de restauracion y alojamiento": "Variación anual del IPC de restauración y alojamiento",
  "Variacion anual del precio del alquiler": "Variación anual del precio del alquiler",
  "Indice del precio del alquiler": "Índice del precio del alquiler",
  "Locales empresariales activos": "Unidades locales empresariales activas",
  "Locales empresariales sin asalariados": "Unidades locales sin asalariados",
  "Usuarios bicicleta publica":   "Usuarios de bicicleta pública",
  // English fallback labels (variable_label() fallback: raw.replace("_"," ").capitalize())
  "Birth rate":                   "Tasa de natalidad",
  "Mortality rate":               "Tasa de mortalidad",
  "Fertility rate":               "Índice de fecundidad",
  "Population 0 14 pct":         "Población 0–14 años (%)",
  "Population 15 64 pct":        "Población 15–64 años (%)",
  "Population 65 plus pct":      "Población 65 o más años (%)",
  "Native born pct":              "Nacidos nacionales (%)",
  "Foreign born pct":             "Nacidos en el extranjero (%)",
  "Foreign population pct":       "Población extranjera (%)",
  "National population pct":      "Población de nacionalidad española (%)",
  "Single person households pct": "Hogares unipersonales (%)",
  "Dwellings cadastre":           "Viviendas según catastro",
  "Dwellings census":             "Viviendas según censo",
  "Rent median eur m2 year":      "Mediana del alquiler anual (€/m²)",
  "Rent q1 eur m2 year":          "Primer cuartil del alquiler anual (€/m²)",
  "Rent q1 monthly":              "Primer cuartil del alquiler mensual",
  "Rent q3 eur m2 year":          "Tercer cuartil del alquiler anual (€/m²)",
  "Rent q3 monthly":              "Tercer cuartil del alquiler mensual",
  "House price mean m2 detached": "Precio medio vivienda unifamiliar (€/m²)",
  "House price mean m2 flat":     "Precio medio piso (€/m²)",
  "House price mean detached":    "Precio medio vivienda unifamiliar",
  "House price mean flat":        "Precio medio piso",
  "Robbery theft rate":           "Tasa de robos y hurtos",
  "Sexual offences rate":         "Tasa de delitos sexuales",
  "Crime rate":                   "Tasa de infracciones penales",
  "Employment rate 20 64":        "Tasa de empleo 20–64 años",
  "Childcare coverage pct":       "Cobertura de guarderías (%)",
  "Education low pct":            "Nivel educativo bajo – CINE 0–2 (%)",
  "Education mid pct":            "Nivel educativo medio – CINE 3–4 (%)",
  "Education high pct":           "Nivel educativo alto – CINE 5–8 (%)",
  "Area total km2":               "Superficie total (km²)",
  "Land discontinuous urban pct": "Tejido urbano discontinuo (%)",
  "Land continuous urban pct":    "Tejido urbano continuo (%)",
  "Land industrial commercial pct": "Suelo industrial y comercial (%)",
  "Land transport infrastructure pct": "Infraestructuras de transporte (%)",
  "Land other artificial pct":    "Otras zonas artificiales (%)",
  "Land urban green pct":         "Zonas verdes urbanas (%)",
  "Land agricultural pct":        "Suelo agrícola (%)",
  "Land natural pct":             "Zonas naturales (%)",
  "Green space to residential ratio": "Ratio zonas verdes / residencial",
  "Cpi general index":            "IPC general (índice)",
  "Cpi general change pct":       "Variación anual del IPC general",
};

const VARIABLE_DESCRIPTIONS = {
  // Empleo
  "Paro registrado":              "Personas inscritas como desempleadas en las oficinas del SEPE al final de cada mes. Serie mensual comparable entre las siete ciudades desde 2007.",
  "Contratos registrados":        "Contratos de trabajo registrados en el SEPE cada mes. Refleja la actividad de contratación laboral, no el volumen total de empleo. Incluye contratos temporales e indefinidos.",
  "Demandantes de empleo":        "Personas que buscan empleo registradas en el SEPE, incluyendo ocupados que buscan activamente cambiar de trabajo.",
  "Tasa de desempleo":            "Porcentaje de la población activa sin empleo. Fuente: INE Indicadores Urbanos. Serie anual homogénea comparable entre ciudades.",
  "Tasa de actividad":            "Proporción de la población en edad de trabajar que participa en el mercado laboral (activos). Fuente: INE Indicadores Urbanos.",
  "Employment rate 20 64":        "Porcentaje de la población entre 20 y 64 años que tiene empleo. Indicador de integración laboral de la población en edad productiva principal.",
  "Empleo en servicios (%)":      "Proporción del empleo urbano en el sector servicios. Las ciudades con mayor terciarización tienden a mayor valor añadido por ocupado.",
  "Empleo en industria (%)":      "Proporción del empleo urbano en el sector industrial. Refleja el peso de la economía manufacturera y la diversificación económica local.",
  // Economía y renta
  "Renta":                        "Renta bruta declarada por los hogares en el municipio, a partir de datos fiscales y encuestas publicadas por los portales de datos abiertos municipales.",
  "Renta mediana":                "Mediana de la distribución de renta del municipio. A diferencia de la media, no se ve distorsionada por valores extremos y refleja mejor la renta del hogar típico.",
  "Renta por persona":            "Renta bruta total del municipio dividida entre el número de habitantes. Permite comparar el nivel económico ajustado por tamaño de la ciudad.",
  "Renta neta media por hogar":   "Renta neta media anual del hogar estimada por el INE para el área urbana. Serie homogénea disponible para todas las ciudades (2011–2023), ideal para comparaciones.",
  "Renta neta media por habitante": "Renta neta por persona estimada por el INE. Ajusta por tamaño del hogar y permite comparar el nivel de vida real entre ciudades.",
  "Renta neta por unidad de consumo": "Renta equivalente por unidad de consumo según la escala OCDE modificada. Es el indicador de bienestar económico comparativo más robusto de los disponibles.",
  "Desigualdad Gini":             "Coeficiente de Gini de desigualdad de renta (0 = igualdad perfecta, 1 = máxima desigualdad). Calculado a nivel municipal por el INE para las principales ciudades.",
  "Desigualdad P80/P20":          "Ratio entre la renta del percentil 80 y el percentil 20. Muestra cuántas veces más ingresa el 20 % más rico respecto al 20 % más pobre del municipio.",
  "Variacion anual del IPC general": "Variación porcentual de la media anual del IPC general publicado por el INE a nivel provincial. Se usa como proxy del nivel de precios urbano.",
  "Variacion anual del IPC de alimentos": "Variación del IPC del grupo de alimentos y bebidas no alcohólicas. Indicador del coste básico de la cesta de la compra.",
  "Variacion anual del IPC de vivienda y energia": "Variación del IPC del grupo de vivienda, agua, electricidad y gas. Refleja la presión inflacionaria en los costes del hogar.",
  "Variacion anual del IPC de transporte": "Variación del IPC del grupo de transporte. Incluye combustibles, tarifas de transporte público y mantenimiento de vehículos.",
  "Variacion anual del IPC de restauracion y alojamiento": "Variación del IPC del grupo de restaurantes, cafeterías y alojamientos. Proxy del coste de hostelería urbana.",
  "Variacion anual del precio del alquiler": "Variación anual del IPVA (Índice de Precios de la Vivienda en Alquiler) publicado por el INE a nivel municipal. Solo disponible para ciertas ciudades.",
  "Indice del precio del alquiler": "Índice del precio del alquiler residencial (base 2015 = 100). Permite comparar la evolución del mercado de alquiler entre ciudades.",
  "Locales empresariales activos": "Unidades locales activas (establecimientos) registradas en la provincia por el DIRCE del INE. Proxy de la actividad empresarial del área urbana.",
  "Locales empresariales sin asalariados": "Unidades locales sin trabajadores asalariados. Refleja el peso de los autónomos y microempresas sin empleados.",
  // Vivienda
  "Alquiler medio anual por m2":  "Precio medio anual del alquiler por metro cuadrado estimado por el INE para el área urbana. Permite comparar directamente el mercado del alquiler entre ciudades.",
  "Alquiler medio mensual":       "Gasto medio mensual en alquiler de vivienda habitual. Estimación del INE de Indicadores Urbanos; disponible para las 7 ciudades (2011–2023).",
  "Mediana del alquiler mensual": "Mediana del precio mensual del alquiler. Al ser la mediana, no se ve distorsionada por pisos de lujo y refleja mejor el alquiler típico del mercado.",
  "Rent q1 monthly":              "Primer cuartil del precio mensual del alquiler: el 25 % de los alquileres están por debajo de este valor. Referencia para el segmento asequible.",
  "Rent q3 monthly":              "Tercer cuartil del precio mensual del alquiler: el 75 % de los alquileres están por debajo de este valor. Referencia para el segmento alto del mercado.",
  "Precio medio de la vivienda":  "Precio medio de compraventa de vivienda libre en el municipio, según estadísticas del INE. Incluye vivienda nueva y de segunda mano.",
  "Precio medio de vivienda por m2": "Precio medio por metro cuadrado de vivienda libre. Indicador estándar de comparación del mercado inmobiliario entre ciudades.",
  "Viviendas vacias":             "Porcentaje de viviendas convencionales desocupadas sobre el total del parque residencial. Fuente: Indicadores Urbanos INE.",
  "Dwellings cadastre":           "Número total de viviendas convencionales según el Catastro. Refleja el parque residencial total registrado fiscalmente.",
  "Dwellings census":             "Número total de viviendas convencionales según el Censo de Población y Viviendas del INE.",
  // Movilidad y seguridad
  "Accidentes de trafico":        "Total de accidentes de tráfico con víctimas registrados mensualmente. Datos de Open Data municipal de Madrid, Barcelona y Valencia.",
  "Registros de movilidad":       "Registros de uso de sistemas de movilidad compartida (bicicletas, patinetes, etc.) como aproximación a los desplazamientos urbanos.",
  "Desplazamientos al trabajo en coche": "Porcentaje de trabajadores que se desplazan al trabajo en vehículo privado. Fuente: INE Indicadores Urbanos.",
  "Desplazamientos al trabajo a pie":    "Porcentaje de trabajadores que se desplazan a pie. Indicador de ciudad compacta y de calidad del espacio público.",
  "Desplazamientos al trabajo en transporte publico": "Porcentaje de trabajadores que usan el transporte público. Indicador de eficiencia del sistema de movilidad urbana.",
  "Duracion del desplazamiento al trabajo": "Tiempo medio del desplazamiento diario al trabajo en minutos. Mayor valor indica mayor dispersión o congestión urbana.",
  "Robbery theft rate":           "Tasa de robos y hurtos por mil habitantes. Fuente: INE Indicadores Urbanos a partir de estadísticas judiciales y policiales.",
  "Sexual offences rate":         "Tasa de delitos contra la libertad sexual por mil habitantes. Fuente: INE Indicadores Urbanos.",
  "Crime rate":                   "Tasa de infracciones penales totales por mil habitantes. Indicador amplio de seguridad ciudadana.",
  // Demografía
  "Poblacion total":              "Número de habitantes del municipio según el Padrón Municipal de Habitantes del INE. Serie anual oficial.",
  "Poblacion residente":          "Población residente habitual estimada por el INE en el marco de los Indicadores Urbanos. Puede diferir ligeramente del padrón en ciertos años.",
  "Birth rate":                   "Número de nacidos vivos por cada mil habitantes. Fuente: INE Indicadores Urbanos. Indicador del dinamismo demográfico de la ciudad.",
  "Mortality rate":               "Número de fallecidos por cada mil habitantes. Junto con la natalidad, determina el crecimiento natural de la población.",
  "Fertility rate":               "Número medio de hijos por mujer. Por debajo de 2,1 no hay reemplazo generacional. Refleja el comportamiento reproductivo de la población.",
  "Edad mediana":                 "Edad que divide la población en dos partes iguales. Un valor creciente indica envejecimiento poblacional.",
  "Esperanza de vida":            "Número medio de años que se espera que viva un recién nacido. Indicador clave de bienestar y calidad de los servicios de salud.",
  "Population 0 14 pct":         "Porcentaje de la población menor de 15 años. Indicador de juventud poblacional y demanda futura de servicios educativos.",
  "Population 15 64 pct":        "Porcentaje de la población en edad de trabajar (15–64 años). Indica el peso de la población potencialmente activa.",
  "Population 65 plus pct":      "Porcentaje de personas de 65 o más años. Indicador del grado de envejecimiento de la ciudad.",
  "Foreign population pct":       "Porcentaje de residentes de nacionalidad extranjera sobre el total. Indicador de diversidad e integración de la población.",
  "Single person households pct": "Porcentaje de hogares formados por una sola persona. Refleja cambios en la estructura familiar y genera mayor demanda de vivienda.",
  "Numero de hogares":            "Total de hogares residentes en el municipio según el INE. Junto con el tamaño medio, permite entender la estructura residencial.",
  "Tamano medio del hogar":       "Número medio de personas por hogar. Ha caído en España de ~3 a ~2,5 en las últimas décadas, aumentando la demanda de vivienda.",
  // Entorno y territorio
  "Area total km2":               "Superficie total del término municipal en kilómetros cuadrados. Permite calcular densidades y comparar la extensión de las ciudades.",
  "Land urban green pct":         "Porcentaje de superficie urbana destinada a zonas verdes. Indicador de calidad del espacio público y sostenibilidad.",
  "Land discontinuous urban pct": "Porcentaje de superficie con tejido urbano discontinuo (urbanizaciones, residencial de baja densidad). Indicador de sprawl urbano.",
  "Land continuous urban pct":    "Porcentaje de superficie con tejido urbano continuo (ciudad compacta). Ciudad compacta implica mayor eficiencia energética y de movilidad.",
  "Green space to residential ratio": "Relación entre zonas verdes y superficie residencial. Indicador de la proporción de espacio verde por habitante.",
  // Educación
  "Childcare coverage pct":       "Porcentaje de niños menores de 3 años escolarizados en guarderías o centros de educación infantil de primer ciclo. Fuente: INE Indicadores Urbanos.",
  "Education low pct":            "Porcentaje de la población adulta con nivel educativo bajo (CINE 0–2: sin estudios o Educación Secundaria incompleta).",
  "Education mid pct":            "Porcentaje de la población adulta con nivel educativo medio (CINE 3–4: Bachillerato, FP de Grado Medio).",
  "Education high pct":           "Porcentaje de la población adulta con nivel educativo alto (CINE 5–8: grado universitario, máster o doctorado).",
  // Turismo
  "Pernoctaciones turisticas":    "Número total de pernoctaciones en establecimientos turísticos reglados. Indicador de atractivo turístico y presión sobre la ciudad.",
  "Plazas turisticas":            "Número de plazas disponibles en establecimientos turísticos. Refleja la capacidad de acogida del sector turístico.",
};

const CATEGORY_LABELS = {
  employment:        "Mercado laboral",
  economy:           "Economía y renta",
  housing:           "Vivienda",
  mobility:          "Movilidad",
  demography:        "Demografía",
  environment:       "Territorio",
  education:         "Educación",
  safety:            "Seguridad",
  living_conditions: "Condiciones de vida",
  tourism:           "Turismo",
  business:          "Tejido empresarial",
  cost_of_living:    "Coste de vida",
  other:             "Otros",
};

const CATEGORY_ICONS = {
  employment:        "work",
  economy:           "monitoring",
  housing:           "home",
  mobility:          "commute",
  demography:        "groups",
  environment:       "park",
  education:         "school",
  safety:            "local_police",
  living_conditions: "family_restroom",
  tourism:           "luggage",
  business:          "store",
  cost_of_living:    "price_change",
  other:             "analytics",
};

const UNIT_LABELS = {
  "accidents":          "accidentes",
  "eur_m2_year":        "€/m²·año",
  "eur_month":          "€/mes",
  "eur_m2":             "€/m²",
  "eur":                "€/año",
  "per_thousand":       "por mil hab.",
  "percent":            "%",
  "km2":                "km²",
  "index":              "índice",
  "index_2015":         "índice (base 2015)",
  "persons":            "personas",
  "households":         "hogares",
  "dwellings":          "viviendas",
  "years":              "años",
  "minutes":            "minutos",
  "overnight_stays":    "pernoctaciones",
  "beds":               "plazas",
  "ratio":              "ratio",
  "local_units":        "unidades locales",
  "children_per_woman": "hijos/mujer",
  "contracts":          "contratos",
};

const SOURCE_URLS = {
  "INE INDICADORES URBANOS": "https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736177012&menu=ultiDatos&idp=1254734710990",
  "INE IPVA":                "https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736177015&menu=ultiDatos&idp=1254735976602",
  "INE IPC PROVINCIAL (PROXY URBANO)": "https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176802&menu=ultiDatos&idp=1254735976607",
  "INE ATLAS":               "https://www.ine.es/experimental/atlas/experimental_atlas.htm",
  "SEPE":                    "https://www.sepe.es/HomeSepe/que-es-el-sepe/estadisticas.html",
  "MUNICIPAL OPEN DATA":     "https://datos.gob.es/es/catalogo",
  "DIRCE":                   "https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176927&menu=ultiDatos&idp=1254735576550",
  "CORINE LAND COVER":       "https://land.copernicus.eu/en/products/corine-land-cover",
};

function normalizeCategory(desc) {
  if (!desc) return "other";
  const raw = String(desc).trim().toLowerCase();
  const mapping = {
    "movilidad": "mobility",
    "demografía": "demography",
    "demografia": "demography",
    "economía y renta": "economy",
    "economia y renta": "economy",
    "economía": "economy",
    "economia": "economy",
    "empleo": "employment",
    "mercado laboral": "employment",
    "vivienda": "housing",
    "educación": "education",
    "educacion": "education",
    "territorio y entorno": "environment",
    "medio ambiente": "environment",
    "seguridad ciudadana": "safety",
    "seguridad": "safety",
    "condiciones de vida": "living_conditions",
    "turismo": "tourism",
    "tejido empresarial": "business",
    "coste de vida": "cost_of_living",
  };
  return mapping[raw] || raw;
}

const numberFormatter = new Intl.NumberFormat("es-ES");

function formatNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? numberFormatter.format(n) : "—";
}

function formatPeriod(str) {
  if (!str) return "—";
  const d = new Date(str);
  if (isNaN(d)) return str;
  return d.toLocaleDateString("es-ES", { month: "short", year: "numeric" });
}

function normalizeText(str) {
  return String(str || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9\s]/g, " ").trim();
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function cityBar(count) {
  const total = 7;
  const filled = Math.min(total, Math.max(0, Number(count) || 0));
  const pct = ((filled / total) * 100).toFixed(0);
  return `<div class="city-coverage-bar" title="${filled} de ${total} ciudades">
    <div class="city-coverage-fill" style="width:${pct}%"></div>
  </div><span class="city-coverage-label">${filled} de ${total} ciudades</span>`;
}

let allIndicators = [];
let allCities = [];
let activeCategory = "all";
let searchQuery = "";

function renderCatalog() {
  if (!catalogGrid) return;
  const normQ = normalizeText(searchQuery);
  const visible = allIndicators.filter((item) => {
    const catKey = normalizeCategory(item.description);
    const catMatch = activeCategory === "all" || catKey === activeCategory;
    if (!catMatch) return false;
    if (!normQ) return true;
    const label = VARIABLE_LABELS[item.variable] || item.variable || "";
    const desc = VARIABLE_DESCRIPTIONS[item.variable] || "";
    const sources = item.sources || "";
    return normalizeText(`${label} ${item.variable} ${desc} ${sources}`).includes(normQ);
  });

  if (catalogCount) {
    catalogCount.textContent = normQ || activeCategory !== "all"
      ? `${formatNumber(visible.length)} de ${formatNumber(allIndicators.length)} indicadores`
      : `${formatNumber(allIndicators.length)} indicadores disponibles`;
  }

  if (!visible.length) {
    catalogGrid.innerHTML = `<p class="trace-empty">No hay indicadores que coincidan con los filtros seleccionados.</p>`;
    return;
  }

  catalogGrid.innerHTML = visible.map((item) => {
    const catKey = normalizeCategory(item.description);
    const label = VARIABLE_LABELS[item.variable] || item.variable;
    const desc = VARIABLE_DESCRIPTIONS[item.variable] || VARIABLE_DESCRIPTIONS[label] || "";
    const catLabel = CATEGORY_LABELS[catKey] || item.description || "Indicador";
    const catIcon = CATEGORY_ICONS[catKey] || "analytics";
    const unitLabel = UNIT_LABELS[item.unit] || item.unit || "";
    const sources = String(item.sources || "Fuente no disponible").split(",").map((s) => s.trim()).filter(Boolean);
    const period = item.first_period === item.latest_period
      ? formatPeriod(item.latest_period)
      : `${formatPeriod(item.first_period)} — ${formatPeriod(item.latest_period)}`;

    return `<article class="catalog-detail-card">
      <div class="catalog-card-top">
        <span class="catalog-cat-badge catalog-cat-badge--${escapeHtml(catKey)}">
          <span class="material-symbols-outlined">${escapeHtml(catIcon)}</span>
          ${escapeHtml(catLabel)}
        </span>
        <div class="catalog-source-pills">
          ${sources.map((s) => {
            const url = SOURCE_URLS[s];
            return url
              ? `<a class="catalog-source-pill" href="${url}" target="_blank" rel="noopener noreferrer">${escapeHtml(s)}</a>`
              : `<span class="catalog-source-pill">${escapeHtml(s)}</span>`;
          }).join("")}
        </div>
      </div>
      <h2 class="catalog-var-label">${escapeHtml(label)}</h2>
      ${desc ? `<p class="catalog-var-desc">${escapeHtml(desc)}</p>` : ""}
      <dl class="catalog-detail-dl">
        <div>
          <dt><span class="material-symbols-outlined">calendar_month</span>Cobertura temporal</dt>
          <dd>${escapeHtml(period)}</dd>
        </div>
        <div>
          <dt><span class="material-symbols-outlined">location_city</span>Ciudades</dt>
          <dd class="catalog-city-dd">${cityBar(item.city_count)}</dd>
        </div>
        ${unitLabel ? `<div>
          <dt><span class="material-symbols-outlined">straighten</span>Unidad</dt>
          <dd>${escapeHtml(unitLabel)}</dd>
        </div>` : ""}
        <div>
          <dt><span class="material-symbols-outlined">database</span>Registros</dt>
          <dd>${formatNumber(item.rows)}</dd>
        </div>
      </dl>
    </article>`;
  }).join("");
}

function renderCityCoverage(cities, totalVars) {
  if (!cityCoverageChart || !cities.length) return;
  const sorted = [...cities].sort((a, b) => Number(b.variables || 0) - Number(a.variables || 0));
  const max = Number(sorted[0]?.variables) || 1;
  cityCoverageChart.innerHTML = sorted.map((item) => {
    const v = Number(item.variables) || 0;
    const pct = ((v / max) * 100).toFixed(1);
    return `<div class="source-bar-row">
      <span class="source-bar-label">${escapeHtml(String(item.city || ""))}</span>
      <div class="source-bar-wrap">
        <div class="source-bar" style="width:${pct}%"></div>
        <span class="source-bar-value">${formatNumber(v)} variables</span>
      </div>
    </div>`;
  }).join("");
}

async function loadData() {
  if (catalogCount) catalogCount.textContent = "Cargando indicadores…";
  if (catalogGrid) catalogGrid.innerHTML = `<p class="trace-empty">Conectando con la API…</p>`;

  try {
    let payload = null;
    const cached = sessionStorage.getItem(CACHE_KEY);
    if (cached) {
      try {
        const { ts, data } = JSON.parse(cached);
        if (Date.now() - ts < CACHE_TTL) payload = data;
      } catch (_) { /* ignore */ }
    }
    if (!payload) {
      const res = await fetch(API_URL);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      payload = await res.json();
      sessionStorage.setItem(CACHE_KEY, JSON.stringify({ ts: Date.now(), data: payload }));
    }
    allIndicators = payload.indicatorCatalog || [];
    allCities = payload.cities || [];
    renderCatalog();
    renderCityCoverage(allCities, Number(payload.kpis?.variableCount) || allIndicators.length);
  } catch (err) {
    if (catalogCount) catalogCount.textContent = "Error al cargar los indicadores.";
    if (catalogGrid) catalogGrid.innerHTML = `<p class="trace-empty">No se pudo conectar con la API: ${escapeHtml(String(err.message))}.</p>`;
  }
}

catalogSearch?.addEventListener("input", () => {
  searchQuery = catalogSearch.value;
  renderCatalog();
});

categoryChips?.addEventListener("click", (e) => {
  const chip = e.target.closest("[data-cat]");
  if (!chip) return;
  activeCategory = chip.dataset.cat;
  categoryChips.querySelectorAll(".filter-chip").forEach((c) => c.classList.toggle("is-active", c === chip));
  renderCatalog();
});

function setSidebarOpen(open) {
  document.body.classList.toggle("sidebar-open", open);
  menuButtons.forEach((b) => b.setAttribute("aria-expanded", String(open)));
  if (sidebarBackdrop) sidebarBackdrop.tabIndex = open ? 0 : -1;
}
menuButtons.forEach((b) => b.addEventListener("click", () => setSidebarOpen(!document.body.classList.contains("sidebar-open"))));
sidebarBackdrop?.addEventListener("click", () => setSidebarOpen(false));
sidebarLinks.forEach((l) => l.addEventListener("click", () => setSidebarOpen(false)));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && document.body.classList.contains("sidebar-open")) setSidebarOpen(false);
});

loadData();
