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

const VARIABLE_LABELS = {
  unemployed_registered:        "Paro registrado",
  contracts_registered:         "Contratos registrados",
  job_seekers:                  "Demandantes de empleo",
  income:                       "Renta bruta municipal",
  income_median:                "Renta mediana",
  income_per_person:            "Renta per cápita (municipal)",
  net_income_household:         "Renta neta media del hogar",
  net_income_per_capita:        "Renta neta per cápita",
  net_income_consumption_unit:  "Renta por unidad de consumo",
  gini_inequality:              "Índice de Gini (desigualdad)",
  inequality_p80p20:            "Ratio P80/P20 (desigualdad)",
  traffic_accidents:            "Accidentes de tráfico",
  mobility_resources_records:   "Registros de movilidad compartida",
  cpi_general:                  "IPC general",
  rent_price:                   "Precio medio del alquiler",
  tourism_overnights:           "Pernoctaciones turísticas",
  population:                   "Población total",
  population_density:           "Densidad de población",
};

const VARIABLE_DESCRIPTIONS = {
  unemployed_registered:        "Personas inscritas como desempleadas en las oficinas del SEPE al final de cada mes. Serie mensual disponible desde 2007, comparable entre las siete ciudades.",
  contracts_registered:         "Contratos de trabajo registrados en el SEPE cada mes. Refleja la actividad de contratación laboral, no el volumen de empleo total. Incluye contratos temporales e indefinidos.",
  job_seekers:                  "Personas que buscan empleo registradas en el SEPE, incluyendo a ocupados que buscan activamente cambiar de trabajo.",
  income:                       "Renta bruta declarada por los hogares en el municipio, a partir de datos fiscales y encuestas publicadas por los portales de datos abiertos municipales.",
  income_median:                "Mediana de la distribución de renta en el municipio. A diferencia de la media, no se ve distorsionada por valores extremos y refleja mejor la renta del hogar típico.",
  income_per_person:            "Renta bruta total del municipio dividida entre el número de habitantes. Permite comparar el nivel económico ajustado por tamaño de la ciudad.",
  net_income_household:         "Renta neta media del hogar estimada por el INE para el área urbana. Serie homogénea disponible para todas las ciudades (2011–2023), ideal para comparaciones interurbanas.",
  net_income_per_capita:        "Renta neta por persona estimada por el INE. Ajusta por tamaño del hogar y permite comparar el nivel de vida real entre ciudades.",
  net_income_consumption_unit:  "Renta equivalente por unidad de consumo según la escala OCDE modificada. Es el indicador de bienestar económico comparativo más robusto de los disponibles.",
  gini_inequality:              "Coeficiente de Gini de desigualdad de renta (0 = igualdad perfecta, 1 = máxima desigualdad). Calculado a nivel municipal por el INE para las principales ciudades.",
  inequality_p80p20:            "Ratio entre la renta del percentil 80 y el percentil 20. Muestra cuántas veces más ingresa el 20% más rico respecto al 20% más pobre del municipio.",
  traffic_accidents:            "Total de accidentes de tráfico con víctimas registrados en el municipio. Datos mensuales procedentes de los portales de datos abiertos de Madrid, Barcelona y Valencia.",
  mobility_resources_records:   "Registros de uso de sistemas de movilidad compartida (bicicletas, patinetes, etc.) disponibles como aproximación a los desplazamientos urbanos.",
  cpi_general:                  "Índice de Precios de Consumo general (base 2021 = 100) publicado por el INE a nivel provincial, utilizado como proxy del nivel de precios urbano.",
  rent_price:                   "Precio medio mensual del alquiler residencial estimado por el INE a nivel de área urbana. Incluye contratos de nueva firma en el mercado libre.",
  tourism_overnights:           "Número total de pernoctaciones en establecimientos turísticos reglados registradas por el INE. Indicador de atractivo y presión turística de la ciudad.",
};

const CATEGORY_LABELS = {
  economy:    "Economía y renta",
  employment: "Mercado laboral",
  mobility:   "Movilidad",
  demography: "Demografía",
};

const CATEGORY_ICONS = {
  economy:    "monitoring",
  employment: "work",
  mobility:   "commute",
  demography: "groups",
};

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
    const catMatch = activeCategory === "all" || (item.description || "") === activeCategory;
    if (!catMatch) return false;
    if (!normQ) return true;
    const label = VARIABLE_LABELS[item.variable] || item.variable || "";
    const desc = VARIABLE_DESCRIPTIONS[item.variable] || item.description || "";
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
    const label = VARIABLE_LABELS[item.variable] || item.variable;
    const desc = VARIABLE_DESCRIPTIONS[item.variable] || "Indicador disponible para consulta territorial.";
    const catLabel = CATEGORY_LABELS[item.description] || item.description || "Indicador";
    const catIcon = CATEGORY_ICONS[item.description] || "analytics";
    const sources = String(item.sources || "Fuente no disponible").split(",").map((s) => s.trim()).filter(Boolean);
    const period = item.first_period === item.latest_period
      ? formatPeriod(item.latest_period)
      : `${formatPeriod(item.first_period)} — ${formatPeriod(item.latest_period)}`;

    return `<article class="catalog-detail-card">
      <div class="catalog-card-top">
        <span class="catalog-cat-badge catalog-cat-badge--${escapeHtml(item.description || "other")}">
          <span class="material-symbols-outlined">${escapeHtml(catIcon)}</span>
          ${escapeHtml(catLabel)}
        </span>
        <div class="catalog-source-pills">
          ${sources.map((s) => `<span class="catalog-source-pill">${escapeHtml(s)}</span>`).join("")}
        </div>
      </div>
      <h2 class="catalog-var-label">${escapeHtml(label)}</h2>
      <code class="catalog-var-id">${escapeHtml(String(item.variable || ""))}</code>
      <p class="catalog-var-desc">${escapeHtml(desc)}</p>
      <dl class="catalog-detail-dl">
        <div>
          <dt><span class="material-symbols-outlined">calendar_month</span>Cobertura temporal</dt>
          <dd>${escapeHtml(period)}</dd>
        </div>
        <div>
          <dt><span class="material-symbols-outlined">location_city</span>Ciudades</dt>
          <dd class="catalog-city-dd">${cityBar(item.city_count)}</dd>
        </div>
        ${item.unit ? `<div>
          <dt><span class="material-symbols-outlined">straighten</span>Unidad</dt>
          <dd>${escapeHtml(String(item.unit))}</dd>
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
