const form = document.querySelector("#chatForm");
const input = document.querySelector("#chatInput");
const messages = document.querySelector("#messages");
const welcomeState = document.querySelector("#welcomeState");
const promptButtons = document.querySelectorAll("[data-prompt]");
const newChatButton = document.querySelector(".new-chat");
const dataTabs = document.querySelectorAll("[data-view]");
const lastUpdateTime = document.querySelector("#lastUpdateTime");
const traceLog = document.querySelector("#traceLog");
const screenTabs = document.querySelectorAll("[data-screen]");
const dashboardScreen = document.querySelector("#dashboardScreen");
const chatbotScreen = document.querySelector("#chatbotScreen");
const composerScreen = document.querySelector("#composerScreen");
const screenTitle = document.querySelector("#screenTitle");
const openChatbotButton = document.querySelector("#openChatbot");
const refreshDashboardButton = document.querySelector("#refreshDashboard");
const pipelineStatus = document.querySelector("#pipelineStatus");
const kpiIndicators = document.querySelector("#kpiIndicators");
const kpiSources = document.querySelector("#kpiSources");
const kpiVariables = document.querySelector("#kpiVariables");
const kpiDetails = document.querySelector("#kpiDetails");
const databaseStatus = document.querySelector("#databaseStatus");
const selectionDetail = document.querySelector("#selectionDetail");
const clearSelectionButton = document.querySelector("#clearSelection");
const sourcePie = document.querySelector("#sourcePie");
const sourceChart = document.querySelector("#sourceChart");
const qualityChart = document.querySelector("#qualityChart");
const topVariablesChart = document.querySelector("#topVariablesChart");
const periodChart = document.querySelector("#periodChart");
const coverageChart = document.querySelector("#coverageChart");
const yearBarsChart = document.querySelector("#yearBarsChart");
const variableScatterChart = document.querySelector("#variableScatterChart");
const sourceCompareChart = document.querySelector("#sourceCompareChart");
const latestRows = document.querySelector("#latestRows");
const cityUpdateGrid = document.querySelector("#cityUpdateGrid");
const cityUpdateCount = document.querySelector("#cityUpdateCount");
const indicatorCatalogGrid = document.querySelector("#indicatorCatalogGrid");
const indicatorCatalogCount = document.querySelector("#indicatorCatalogCount");
const LOCAL_API_BASE_URL = "http://127.0.0.1:5500";
const LOCAL_HOSTNAMES = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);
const isLocalPreview = window.location.protocol === "file:"
  || LOCAL_HOSTNAMES.has(window.location.hostname);
const API_BASE_URL = isLocalPreview ? LOCAL_API_BASE_URL : window.location.origin;

let activeTopic = "general";
let activeView = "general";
let lastAssistantBody = null;
let lastAssistantText = "";
let lastUserQuestion = "";
let lastTrace = null;
let lastLocalData = null;
let isSending = false;
let conversationHistory = [];
let dashboardPayload = null;
let activeSelection = null;

const numberFormatter = new Intl.NumberFormat("es-ES");
const percentFormatter = new Intl.NumberFormat("es-ES", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1
});
const chartPalette = ["#4f7c59", "#b56b45", "#d6a94a", "#6f8f72", "#8b6f4e", "#c26f5b", "#6f7f8d", "#9a8c63"];

const taskLabels = {
  pensando: "Pensando",
  datos: "Recuperando datos",
  respuesta: "Generando respuesta"
};

const datasets = {
  general: {
    label: "Vista general",
    title: "Variables ISEU",
    summary: "Panel listo para mostrar datos segun el tema detectado en la conversacion.",
    source: "INE / Idescat / REE",
    confidence: "Media",
    table: [
      ["Poblacion", "1.713.247", "Idescat", "2025"],
      ["VAB servicios", "73.729,4", "Idescat", "2023"],
      ["IPC general", "119,94", "INE", "2025"],
      ["Demanda electrica", "Disponible", "REE", "2026"]
    ],
    chart: [
      ["Consumo", 68],
      ["Coste vida", 56],
      ["Laboral", 61],
      ["Bienestar", 64]
    ]
  },
  empleo: {
    label: "Mercado laboral",
    title: "Mercado laboral urbano",
    summary: "Lectura de paro, contratos, empleo y actividad economica para comparar territorios.",
    source: "SEPE / INE EPA / Idescat",
    confidence: "Media",
    table: [
      ["Paro registrado", "Municipal España", "SEPE", "OK"],
      ["Contratos registrados", "Municipal España", "SEPE", "OK"],
      ["Tasa de paro", "Autonomica/proxy", "INE EPA", "OK"],
      ["Actividad economica", "Disponible segun territorio", "Idescat/otros", "Parcial"]
    ],
    chart: [
      ["Paro", 48],
      ["Empleo", 66],
      ["Servicios", 78],
      ["Confianza", 58]
    ]
  },
  sanidad: {
    label: "Sanidad",
    title: "Bienestar urbano",
    summary: "Vista de equipamientos, poblacion y cobertura territorial cuando exista fuente comparable.",
    source: "Open Data BCN / INE / Idescat",
    confidence: "Media",
    table: [
      ["Equipamientos salud", "Segun ciudad", "Open Data BCN", "Parcial"],
      ["Poblacion", "Territorial", "INE/Idescat", "OK"],
      ["Crecimiento poblacion", "Segun territorio", "INE/Idescat", "Parcial"],
      ["Cobertura", "Proxy", "ISEU", "Calculado"]
    ],
    chart: [
      ["Cobertura", 62],
      ["Poblacion", 82],
      ["Presion", 55],
      ["Confianza", 52]
    ]
  },
  coste: {
    label: "Coste de vida",
    title: "Presion economica general",
    summary: "Vista general de IPC, energia y fiscalidad. No se centra en vivienda.",
    source: "INE / REE / Idescat",
    confidence: "Alta-media",
    table: [
      ["IPC general", "119,94", "INE", "2025"],
      ["Inflacion anual", "2,8 aprox.", "INE", "2025"],
      ["Precio energia", "Serie horaria", "REE", "OK"],
      ["IBI cuota integra", "829.660.903", "Idescat", "2024"]
    ],
    chart: [
      ["IPC", 72],
      ["Energia", 58],
      ["Fiscalidad", 64],
      ["Confianza", 73]
    ]
  },
  calidad: {
    label: "Calidad de dato",
    title: "Trazabilidad disponible",
    summary: "Estado de fuentes, automatizacion y uso de proxies antes de calcular el score final.",
    source: "Informe de ejecucion",
    confidence: "Variable",
    table: [
      ["INE", "IPC / EPA", "Datos cargados", "OK"],
      ["MITMA/MIVAU", "Vivienda municipal", "Datos cargados", "OK"],
      ["REE", "Precio / demanda", "Datos cargados", "OK"],
      ["SEPE", "Paro registrado / contratos", "Datos cargados", "OK"]
    ],
    chart: [
      ["OK", 70],
      ["Manual", 18],
      ["Error", 12],
      ["MVP", 86]
    ]
  }
};

const sampleAnswers = [
  {
    topic: "general",
    keywords: ["hola", "buenos", "buenas", "que tal", "como estas", "como vas"],
    html: `
      <p>Hola. Soy el asistente ISEU+, centrado en indicadores economicos urbanos de España.</p>
      <p>Puedo responder sobre mercado laboral, vivienda, coste de vida, energia y calidad de los datos disponibles a partir de INE, REE, MITMA/MIVAU, SEPE, Idescat y Open Data BCN.</p>
      <div class="answer-panel">
        <div class="metric-row"><span>Pilares disponibles</span><strong>Empleo, Sanidad, Coste de vida, Energia</strong></div>
        <div class="metric-row"><span>Fuentes activas</span><strong>INE, REE, MITMA/MIVAU, SEPE, Idescat, Open Data BCN</strong></div>
        <div class="metric-row"><span>Estado</span><strong>Datos cargados</strong></div>
      </div>
      <p>Prueba a preguntar por algun tema concreto o usa los accesos directos de abajo.</p>
    `
  },
  {
    topic: "empleo",
    keywords: ["empleo", "trabajo", "paro", "desempleo", "laboral"],
    html: `
      <p>Hay que leerlo como una combinacion de mercado laboral y presion economica, no como una unica causa.</p>
      <p>ISEU miraria si el empleo disponible esta creciendo al mismo ritmo que la poblacion activa, si los sectores fuertes absorben perfiles nuevos y si el coste de vida reduce el margen real de quien busca trabajo.</p>
      <div class="answer-panel">
        <div class="metric-row"><span>Paro y contratos</span><strong>SEPE municipal España</strong></div>
        <div class="metric-row"><span>Tasa de paro / empleo</span><strong>INE EPA, proxy autonomico</strong></div>
        <div class="metric-row"><span>Actividad economica</span><strong>Disponible segun territorio</strong></div>
      </div>
      <p>He actualizado el panel lateral con la tabla y el grafico del pilar laboral.</p>
    `
  },
  {
    topic: "sanidad",
    keywords: ["sanidad", "salud", "hospital", "ambulatorio", "cap", "medico"],
    html: `
      <p>Para sanidad, el sistema deberia hablar de accesibilidad y bienestar: cuantos equipamientos hay, donde estan y cuanta poblacion cubren.</p>
      <div class="answer-panel">
        <div class="metric-row"><span>Equipamientos de salud</span><strong>Open Data BCN cuando exista</strong></div>
        <div class="metric-row"><span>Poblacion de referencia</span><strong>INE / Idescat segun territorio</strong></div>
        <div class="metric-row"><span>Lectura ISEU</span><strong>Cobertura + presion demografica</strong></div>
      </div>
      <p>El panel lateral queda filtrado para sanidad, con datos listos para cruzarse con otros indicadores.</p>
    `
  },
  {
    topic: "coste",
    keywords: ["coste", "vida", "ipc", "inflacion", "energia", "precio", "caro", "gasto"],
    html: `
      <p>Coste de vida se puede responder de forma general con inflacion, energia y presion fiscal disponible.</p>
      <div class="answer-panel">
        <div class="metric-row"><span>IPC general</span><strong>INE mensual</strong></div>
        <div class="metric-row"><span>Energia</span><strong>REE precio/demanda</strong></div>
        <div class="metric-row"><span>IBI</span><strong>Idescat 2024</strong></div>
      </div>
      <p>Lo dejo como pilar transversal para no convertir la pagina en un modulo de vivienda.</p>
    `
  },
  {
    topic: "calidad",
    keywords: ["dato", "fuente", "calidad", "scraper", "api", "apis", "tabla"],
    html: `
      <p>Ahora mismo conviene priorizar variables con cobertura estable y trazabilidad clara.</p>
      <div class="answer-panel">
        <div class="metric-row"><span>Fuentes mas solidas</span><strong>SEPE, MITMA/MIVAU, INE, REE</strong></div>
        <div class="metric-row"><span>Fuentes parciales</span><strong>Idescat, Open Data BCN, Seguridad Social</strong></div>
        <div class="metric-row"><span>Regla de respuesta</span><strong>Fuente + fecha + territorio + confianza</strong></div>
      </div>
      <p>Asi el usuario entiende de donde sale cada conclusion y donde hay incertidumbre.</p>
    `
  }
];

function autoResize() {
  if (!input) {
    return;
  }
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
}

function renderLastUpdateTime() {
  if (!lastUpdateTime) {
    return;
  }

  const now = new Date();
  const updateHour = 7;
  const lastRun = new Date(now);
  lastRun.setHours(updateHour, 0, 0, 0);

  if (now < lastRun) {
    lastRun.setDate(lastRun.getDate() - 1);
  }

  const formatted = new Intl.DateTimeFormat("es-ES", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit"
  }).format(lastRun);

  lastUpdateTime.dateTime = lastRun.toISOString();
  lastUpdateTime.textContent = `${formatted} · 07:00`;
}

function setActiveScreen(screen) {
  const isDashboard = screen === "dashboard";
  dashboardScreen?.classList.toggle("is-active", isDashboard);
  chatbotScreen?.classList.toggle("is-active", !isDashboard);
  composerScreen?.classList.toggle("is-active", !isDashboard);
  screenTabs.forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.screen === screen);
  });
  if (screenTitle) {
    screenTitle.textContent = isDashboard ? "Dashboard" : "Chatbot";
  }
  if (!isDashboard) {
    input?.focus();
  }
}

function formatNumber(value) {
  const number = Number(value || 0);
  return numberFormatter.format(number);
}

function formatDashboardValue(value, unit) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return String(value || "");
  }
  const formatted = Math.abs(number) >= 1000
    ? numberFormatter.format(Math.round(number))
    : number.toLocaleString("es-ES", { maximumFractionDigits: 2 });
  return `${formatted} ${unit || ""}`.trim();
}

function normalizeText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

async function loadDashboard() {
  try {
    if (pipelineStatus) {
      pipelineStatus.textContent = "Actualizando resumen de datos.";
    }
    const response = await fetch(`${API_BASE_URL}/api/dashboard`, {
      headers: { "Accept": "application/json" },
      cache: "no-store"
    });
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      throw new Error(`La API de datos no respondio correctamente (${response.status}). Inicia el servicio local en ${LOCAL_API_BASE_URL}.`);
    }
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "No se pudo cargar el dashboard.");
    }
    renderDashboard(payload);
  } catch (error) {
    const message = error instanceof TypeError
      ? `No se puede conectar con la API de datos en ${LOCAL_API_BASE_URL}. Inicia el servicio local.`
      : error.message;
    if (pipelineStatus) {
      pipelineStatus.textContent = message;
    }
    if (sourceChart) {
      sourceChart.innerHTML = `<p class="trace-empty">${escapeHtml(message)}</p>`;
    }
  }
}

function renderDashboard(payload) {
  dashboardPayload = payload;
  const kpis = payload.kpis || {};
  if (kpiIndicators) kpiIndicators.textContent = formatNumber(kpis.indicatorRows);
  if (kpiSources) kpiSources.textContent = formatNumber(kpis.sourceCount);
  if (kpiVariables) kpiVariables.textContent = formatNumber(kpis.variableCount);
  if (kpiDetails) kpiDetails.textContent = formatNumber(kpis.detailRows);

  if (databaseStatus) {
    databaseStatus.textContent = payload.ready ? "Cobertura por ciudad" : "Base de datos no disponible";
  }
  if (pipelineStatus) {
    const apiSummary = payload.pipeline?.apis || {};
    pipelineStatus.textContent = `Fuentes OK: ${apiSummary.total_ok ?? "-"} | errores: ${apiSummary.total_error ?? "-"} | manuales: ${apiSummary.total_manual ?? "-"}`;
  }
  if (lastUpdateTime && payload.updatedAt) {
    lastUpdateTime.dateTime = payload.updatedAt;
    lastUpdateTime.textContent = payload.updatedAt.replace("T", " ");
  }
  renderSourceChart(payload.cities || []);
  renderSourcePie(payload.cities || []);
  renderDashboardCharts(payload.charts || {});
  renderExpandedCharts(payload);
  renderSelectionDetail();
  renderLatestRows(getFilteredLatestRows());
  renderCityUpdates(payload.cityUpdates || []);
  renderIndicatorCatalog(payload.indicatorCatalog || []);
}

function getFilteredLatestRows() {
  const rows = dashboardPayload?.latestRows || [];
  if (!activeSelection) {
    return rows;
  }
  if (activeSelection.type === "source") {
    return rows.filter((row) => String(row.source || "") === activeSelection.label);
  }
  if (activeSelection.type === "city") {
    const selectedCity = normalizeText(activeSelection.label);
    return rows.filter((row) => normalizeText(row.geo).includes(selectedCity));
  }
  if (activeSelection.type === "quality") {
    return rows.filter((row) => String(row.quality || "Sin clasificar").toLowerCase() === activeSelection.label.toLowerCase());
  }
  if (activeSelection.type === "year") {
    return rows.filter((row) => parseYear(row.period) === Number(activeSelection.label));
  }
  if (activeSelection.type === "variable") {
    return rows.filter((row) => String(row.variable || "") === activeSelection.label);
  }
  return rows;
}

function selectDashboardItem(selection) {
  activeSelection = selection;
  renderSelectionDetail();
  renderLatestRows(getFilteredLatestRows());
  updateInteractiveActiveState();
}

function clearDashboardSelection() {
  activeSelection = null;
  renderSelectionDetail();
  renderLatestRows(getFilteredLatestRows());
  updateInteractiveActiveState();
}

function renderSelectionDetail() {
  if (!selectionDetail) {
    return;
  }
  if (!activeSelection) {
    selectionDetail.innerHTML = "<p>Selecciona una fuente, barra, punto o variable para ver una lectura rapida y filtrar la tabla.</p>";
    return;
  }
  const filteredRows = getFilteredLatestRows();
  const totalRows = Number(dashboardPayload?.kpis?.indicatorRows) || 0;
  const value = Number(activeSelection.value) || 0;
  const pct = totalRows > 0 && value > 0 ? `${percentFormatter.format(value / totalRows * 100)}% del total` : "seleccion activa";
  const prompt = encodeURIComponent(`Explica ${activeSelection.label} con los datos disponibles`);

  selectionDetail.innerHTML = `
    <div class="selection-summary">
      <div>
        <span>${escapeHtml(activeSelection.kind || "Seleccion")}</span>
        <strong>${escapeHtml(activeSelection.label)}</strong>
      </div>
      <div>
        <span>Volumen</span>
        <strong>${escapeHtml(activeSelection.valueLabel || formatNumber(value))}</strong>
      </div>
      <div>
        <span>Peso</span>
        <strong>${escapeHtml(pct)}</strong>
      </div>
      <div>
        <span>Tabla</span>
        <strong>${formatNumber(filteredRows.length)} filas visibles</strong>
      </div>
    </div>
    <p>${escapeHtml(activeSelection.note || "La seleccion filtra los ultimos indicadores cuando hay coincidencias directas.")}</p>
    <a class="selection-action" href="chatbot.html?prompt=${prompt}">Preguntar sobre esta seleccion</a>
  `;
}

function updateInteractiveActiveState() {
  document.querySelectorAll("[data-select-type]").forEach((element) => {
    const isActive = Boolean(
      activeSelection &&
      element.dataset.selectType === activeSelection.type &&
      element.dataset.selectLabel === activeSelection.label
    );
    element.classList.toggle("is-selected", isActive);
  });
}

function attachInteractiveHandlers(container) {
  container?.querySelectorAll("[data-select-type]").forEach((element) => {
    element.addEventListener("click", () => {
      selectDashboardItem({
        type: element.dataset.selectType,
        kind: element.dataset.selectKind,
        label: element.dataset.selectLabel,
        value: Number(element.dataset.selectValue) || 0,
        valueLabel: element.dataset.selectValueLabel,
        note: element.dataset.selectNote
      });
    });
  });
  updateInteractiveActiveState();
}

function renderExpandedCharts(payload) {
  renderVerticalYearBars(yearBarsChart, payload.charts?.periods || []);
  renderVariableScatter(variableScatterChart, payload.variables || []);
  renderSourceComparison(sourceCompareChart, payload.sources || [], payload.charts?.sourceVariables || []);
}

function renderDashboardCharts(charts) {
  renderCompactDistribution(qualityChart, charts.quality || [], {
    labelKey: "quality",
    valueKey: "rows",
    type: "quality",
    kind: "Calidad",
    mode: "percent",
    empty: "No hay calidad clasificada."
  });
  renderCompactDistribution(topVariablesChart, charts.topVariables || [], {
    labelKey: "variable",
    valueKey: "rows",
    type: "variable",
    kind: "Variable",
    limit: 7,
    empty: "No hay variables para mostrar."
  });
  renderCompactDistribution(periodChart, charts.periods || [], {
    labelKey: "period_group",
    valueKey: "rows",
    type: "year",
    kind: "Ano",
    sortAscLabel: true,
    empty: "No hay periodos suficientes."
  });
  renderCompactDistribution(coverageChart, charts.sourceVariables || [], {
    labelKey: "source",
    valueKey: "variables",
    type: "source",
    kind: "Fuente",
    suffix: " variables",
    empty: "No hay cobertura disponible."
  });
}

function parseYear(value) {
  const match = String(value || "").match(/\b(19|20)\d{2}\b/);
  return match ? Number(match[0]) : null;
}

function renderVerticalYearBars(container, rows) {
  if (!container) {
    return;
  }
  const values = rows
    .map((row) => ({
      year: String(row.period_group || ""),
      value: Number(row.rows) || 0
    }))
    .filter((row) => row.year && row.value > 0)
    .sort((a, b) => Number(a.year) - Number(b.year));

  if (!values.length) {
    container.innerHTML = `<p class="trace-empty">No hay anos suficientes para graficar.</p>`;
    return;
  }

  const maxValue = Math.max(...values.map((row) => row.value), 1);
  container.innerHTML = values.map((row, index) => {
    const height = Math.max(8, Math.round(row.value / maxValue * 100));
    const color = chartPalette[index % chartPalette.length];
    return `
      <button class="year-bar-item interactive-chart-item" type="button" title="${escapeHtml(`${row.year}: ${formatNumber(row.value)} registros`)}" data-select-type="year" data-select-kind="Ano" data-select-label="${escapeHtml(row.year)}" data-select-value="${row.value}" data-select-value-label="${escapeHtml(`${formatNumber(row.value)} registros`)}" data-select-note="Este ano concentra los registros mostrados en la serie temporal.">
        <div class="year-bar-value">${formatNumber(row.value)}</div>
        <div class="year-bar-track">
          <div class="year-bar-fill" style="height:${height}%; background:${color}"></div>
        </div>
        <span>${escapeHtml(row.year)}</span>
      </button>
    `;
  }).join("");
  attachInteractiveHandlers(container);
}

function renderVariableScatter(container, variables) {
  if (!container) {
    return;
  }
  const points = variables
    .map((item, index) => ({
      label: String(item.variable || "Variable"),
      source: String(item.source || "Fuente"),
      year: parseYear(item.latest_period),
      rows: Number(item.rows) || 0,
      color: chartPalette[index % chartPalette.length]
    }))
    .filter((item) => item.year && item.rows > 0);

  if (points.length < 2) {
    container.innerHTML = `<p class="trace-empty">No hay variables suficientes para la dispersion.</p>`;
    return;
  }

  const years = points.map((point) => point.year);
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  const maxLogRows = Math.max(...points.map((point) => Math.log10(point.rows + 1)), 1);
  const sortedPoints = points.sort((a, b) => b.rows - a.rows).slice(0, 34);

  container.innerHTML = `
    <div class="scatter-axis y-axis">mas registros</div>
    <div class="scatter-axis x-axis">mas actual</div>
    ${sortedPoints.map((point) => {
      const x = maxYear === minYear ? 50 : ((point.year - minYear) / (maxYear - minYear)) * 86 + 7;
      const y = 88 - (Math.log10(point.rows + 1) / maxLogRows) * 76;
      const size = Math.max(8, Math.min(22, 7 + Math.log10(point.rows + 1) * 3));
      const title = `${point.label} (${point.source}) · ${point.year} · ${formatNumber(point.rows)} registros`;
      return `
        <button class="scatter-point" type="button" title="${escapeHtml(title)}" data-select-type="variable" data-select-kind="Variable" data-select-label="${escapeHtml(point.label)}" data-select-value="${point.rows}" data-select-value-label="${escapeHtml(`${formatNumber(point.rows)} registros`)}" data-select-note="Punto de dispersion cruzando volumen de registros y actualidad temporal." style="left:${x}%; top:${y}%; width:${size}px; height:${size}px; background:${point.color}">
          <span>${escapeHtml(title)}</span>
        </button>
      `;
    }).join("")}
    <div class="scatter-year min">${minYear}</div>
    <div class="scatter-year max">${maxYear}</div>
  `;
  attachInteractiveHandlers(container);
}

function renderSourceComparison(container, sources, coverageRows) {
  if (!container) {
    return;
  }
  const coverageBySource = new Map(
    coverageRows.map((row) => [String(row.source || ""), Number(row.variables) || 0])
  );
  const values = sources
    .map((source) => ({
      label: String(source.source || "Fuente"),
      rows: Number(source.rows) || 0,
      variables: coverageBySource.get(String(source.source || "")) || Number(source.variables) || 0
    }))
    .filter((item) => item.rows > 0 || item.variables > 0);

  if (!values.length) {
    container.innerHTML = `<p class="trace-empty">No hay fuentes suficientes para comparar.</p>`;
    return;
  }

  const maxRows = Math.max(...values.map((item) => item.rows), 1);
  const maxVariables = Math.max(...values.map((item) => item.variables), 1);
  container.innerHTML = values.map((item) => `
    <button class="comparison-row interactive-chart-item" type="button" data-select-type="source" data-select-kind="Fuente" data-select-label="${escapeHtml(item.label)}" data-select-value="${item.rows}" data-select-value-label="${escapeHtml(`${formatNumber(item.rows)} registros · ${formatNumber(item.variables)} variables`)}" data-select-note="Comparativa entre volumen de registros y cobertura de variables para esta fuente.">
      <span>${escapeHtml(item.label)}</span>
      <div class="comparison-track">
        <div class="comparison-fill volume" style="width:${Math.max(4, item.rows / maxRows * 100)}%"></div>
      </div>
      <div class="comparison-track">
        <div class="comparison-fill coverage" style="width:${Math.max(4, item.variables / maxVariables * 100)}%"></div>
      </div>
      <strong>${formatNumber(item.rows)} · ${formatNumber(item.variables)} vars.</strong>
    </button>
  `).join("") + `
    <div class="comparison-legend">
      <span><i class="legend-line volume"></i>registros</span>
      <span><i class="legend-line coverage"></i>variables</span>
    </div>
  `;
  attachInteractiveHandlers(container);
}

function renderCompactDistribution(container, rows, options = {}) {
  if (!container) {
    return;
  }
  const labelKey = options.labelKey || "label";
  const valueKey = options.valueKey || "value";
  let values = rows
    .map((row) => ({
      label: String(row[labelKey] || "Sin clasificar"),
      value: Number(row[valueKey]) || 0
    }))
    .filter((row) => row.value > 0);

  if (options.sortAscLabel) {
    values = values.sort((a, b) => a.label.localeCompare(b.label));
  }
  if (options.limit) {
    values = values.slice(0, options.limit);
  }

  if (!values.length) {
    container.innerHTML = `<p class="trace-empty">${escapeHtml(options.empty || "No hay datos suficientes.")}</p>`;
    return;
  }

  const total = values.reduce((sum, row) => sum + row.value, 0);
  const maxValue = Math.max(...values.map((row) => row.value), 1);
  container.innerHTML = values.map((row, index) => {
    const width = Math.max(4, Math.round(row.value / maxValue * 100));
    const color = chartPalette[index % chartPalette.length];
    const displayValue = options.mode === "percent"
      ? `${percentFormatter.format(row.value / total * 100)}%`
      : `${formatNumber(row.value)}${options.suffix || ""}`;
    const type = options.type || "value";
    const kind = options.kind || "Seleccion";
    const valueLabel = options.mode === "percent" ? `${displayValue} · ${formatNumber(row.value)} registros` : displayValue;
    return `
      <button class="compact-row interactive-chart-item" type="button" data-select-type="${escapeHtml(type)}" data-select-kind="${escapeHtml(kind)}" data-select-label="${escapeHtml(row.label)}" data-select-value="${row.value}" data-select-value-label="${escapeHtml(valueLabel)}" data-select-note="Seleccion procedente de un grafico resumen del dashboard.">
        <div class="compact-meta">
          <span>${escapeHtml(row.label)}</span>
          <strong>${escapeHtml(displayValue)}</strong>
        </div>
        <div class="compact-track">
          <div class="compact-fill" style="width:${width}%; background:${color}"></div>
        </div>
      </button>
    `;
  }).join("");
  attachInteractiveHandlers(container);
}

function renderSourcePie(sources) {
  if (!sourcePie) {
    return;
  }
  const validSources = sources
    .map((item) => ({ ...item, rows: Number(item.rows) || 0 }))
    .filter((item) => item.rows > 0);
  const totalRows = validSources.reduce((sum, item) => sum + item.rows, 0);

  if (!validSources.length || totalRows <= 0) {
    sourcePie.innerHTML = `<p class="trace-empty">No hay porcentajes disponibles.</p>`;
    return;
  }

  let cursor = 0;
  const slices = validSources.map((item, index) => {
    const start = cursor;
    const value = item.rows / totalRows * 100;
    cursor += value;
    const color = chartPalette[index % chartPalette.length];
    return `${color} ${start.toFixed(3)}% ${cursor.toFixed(3)}%`;
  });

  const leader = validSources[0];
  const leaderPct = leader.rows / totalRows * 100;
  sourcePie.innerHTML = `
    <div class="pie-chart" style="background: conic-gradient(${slices.join(", ")})">
      <div class="pie-center">
        <span>Total</span>
        <strong>${formatNumber(totalRows)}</strong>
      </div>
    </div>
    <div class="pie-legend">
      <div class="pie-highlight">
        <span>Mayor volumen</span>
        <strong>${escapeHtml(String(leader.source || "Fuente"))} · ${percentFormatter.format(leaderPct)}%</strong>
      </div>
      ${validSources.map((item, index) => {
        const pct = item.rows / totalRows * 100;
        return `
          <button class="pie-legend-row interactive-chart-item" type="button" data-select-type="source" data-select-kind="Fuente" data-select-label="${escapeHtml(String(item.source || "Fuente"))}" data-select-value="${item.rows}" data-select-value-label="${escapeHtml(`${percentFormatter.format(pct)}% · ${formatNumber(item.rows)} registros`)}" data-select-note="Fuente seleccionada desde el reparto porcentual de registros.">
            <span class="legend-dot" style="background:${chartPalette[index % chartPalette.length]}"></span>
            <span>${escapeHtml(String(item.source || "Fuente"))}</span>
            <strong>${percentFormatter.format(pct)}% · ${formatNumber(item.rows)}</strong>
          </button>
        `;
      }).join("")}
    </div>
  `;
  attachInteractiveHandlers(sourcePie);
}

function renderSourceChart(sources) {
  if (!sourceChart) {
    return;
  }
  if (!sources.length) {
    sourceChart.innerHTML = `<p class="trace-empty">No hay fuentes cargadas.</p>`;
    return;
  }
  const maxRows = Math.max(...sources.map((item) => Number(item.rows) || 0), 1);
  sourceChart.innerHTML = sources.map((item) => {
    const rows = Number(item.rows) || 0;
    const width = Math.max(4, Math.round((rows / maxRows) * 100));
    return `
      <button class="source-row interactive-chart-item" type="button" data-select-type="source" data-select-kind="Fuente" data-select-label="${escapeHtml(String(item.source || "Fuente"))}" data-select-value="${rows}" data-select-value-label="${escapeHtml(`${formatNumber(rows)} filas`)}" data-select-note="Fuente seleccionada desde el grafico de barras por volumen.">
        <div class="bar-meta">
          <span>${escapeHtml(String(item.source || "Fuente"))}</span>
          <strong>${formatNumber(rows)} filas</strong>
        </div>
        <div class="bar-track">
          <div class="bar-fill" style="width: ${width}%"></div>
        </div>
      </button>
    `;
  }).join("");
  attachInteractiveHandlers(sourceChart);
}

function renderSourcePie(cities) {
  if (!sourcePie) {
    return;
  }
  const validCities = cities
    .map((item) => ({ ...item, rows: Number(item.rows) || 0 }))
    .filter((item) => item.rows > 0);
  const totalRows = validCities.reduce((sum, item) => sum + item.rows, 0);

  if (!validCities.length || totalRows <= 0) {
    sourcePie.innerHTML = `<p class="trace-empty">No hay ciudades suficientes para graficar.</p>`;
    return;
  }

  let cursor = 0;
  const slices = validCities.map((item, index) => {
    const start = cursor;
    const value = item.rows / totalRows * 100;
    cursor += value;
    const color = chartPalette[index % chartPalette.length];
    return `${color} ${start.toFixed(3)}% ${cursor.toFixed(3)}%`;
  });

  const leader = validCities[0];
  const leaderPct = leader.rows / totalRows * 100;
  sourcePie.innerHTML = `
    <div class="pie-chart" style="background: conic-gradient(${slices.join(", ")})">
      <div class="pie-center">
        <span>Registros</span>
        <strong>${formatNumber(totalRows)}</strong>
      </div>
    </div>
    <div class="pie-legend">
      <div class="pie-highlight">
        <span>Ciudad con mas datos</span>
        <strong>${escapeHtml(String(leader.city || "Ciudad"))} · ${percentFormatter.format(leaderPct)}%</strong>
      </div>
      ${validCities.map((item, index) => {
        const pct = item.rows / totalRows * 100;
        const label = String(item.city || "Ciudad");
        const variables = Number(item.variables) || 0;
        const sourceCount = Number(item.sources) || 0;
        return `
          <button class="pie-legend-row interactive-chart-item" type="button" data-select-type="city" data-select-kind="Ciudad" data-select-label="${escapeHtml(label)}" data-select-value="${item.rows}" data-select-value-label="${escapeHtml(`${percentFormatter.format(pct)}% · ${formatNumber(item.rows)} registros · ${formatNumber(variables)} variables`)}" data-select-note="Ciudad seleccionada desde el reparto territorial de registros disponibles.">
            <span class="legend-dot" style="background:${chartPalette[index % chartPalette.length]}"></span>
            <span>${escapeHtml(label)}</span>
            <strong>${percentFormatter.format(pct)}% · ${formatNumber(variables)} vars. · ${formatNumber(sourceCount)} fuentes</strong>
          </button>
        `;
      }).join("")}
    </div>
  `;
  attachInteractiveHandlers(sourcePie);
}

function renderSourceChart(cities) {
  if (!sourceChart) {
    return;
  }
  if (!cities.length) {
    sourceChart.innerHTML = `<p class="trace-empty">No hay ciudades cargadas.</p>`;
    return;
  }
  const maxRows = Math.max(...cities.map((item) => Number(item.rows) || 0), 1);
  sourceChart.innerHTML = cities.map((item) => {
    const rows = Number(item.rows) || 0;
    const variables = Number(item.variables) || 0;
    const sourceCount = Number(item.sources) || 0;
    const label = String(item.city || "Ciudad");
    const width = Math.max(4, Math.round((rows / maxRows) * 100));
    return `
      <button class="source-row interactive-chart-item" type="button" data-select-type="city" data-select-kind="Ciudad" data-select-label="${escapeHtml(label)}" data-select-value="${rows}" data-select-value-label="${escapeHtml(`${formatNumber(rows)} registros · ${formatNumber(variables)} variables · ${formatNumber(sourceCount)} fuentes`)}" data-select-note="Ciudad seleccionada desde el grafico territorial de datos disponibles.">
        <div class="bar-meta">
          <span>${escapeHtml(label)}</span>
          <strong>${formatNumber(variables)} variables · ${formatNumber(sourceCount)} fuentes</strong>
        </div>
        <div class="bar-track">
          <div class="bar-fill" style="width: ${width}%"></div>
        </div>
      </button>
    `;
  }).join("");
  attachInteractiveHandlers(sourceChart);
}

function renderSourcePie(cities) {
  if (!sourcePie) {
    return;
  }
  const validCities = cities
    .map((item) => ({
      ...item,
      rows: Number(item.rows) || 0,
      variables: Number(item.variables) || 0,
      sources: Number(item.sources) || 0
    }))
    .filter((item) => item.variables > 0 || item.rows > 0);
  const totalVariables = validCities.reduce((sum, item) => sum + Math.max(item.variables, 1), 0);

  if (!validCities.length || totalVariables <= 0) {
    sourcePie.innerHTML = `<p class="trace-empty">No hay ciudades suficientes para graficar.</p>`;
    return;
  }

  let cursor = 0;
  const slices = validCities.map((item, index) => {
    const start = cursor;
    const value = Math.max(item.variables, 1) / totalVariables * 100;
    cursor += value;
    const color = chartPalette[index % chartPalette.length];
    return `${color} ${start.toFixed(3)}% ${cursor.toFixed(3)}%`;
  });

  const leader = validCities.reduce((best, item) => item.variables > best.variables ? item : best, validCities[0]);
  const leaderPct = Math.max(leader.variables, 1) / totalVariables * 100;
  sourcePie.innerHTML = `
    <div class="pie-chart" style="background: conic-gradient(${slices.join(", ")})">
      <div class="pie-center">
        <span>Variables</span>
        <strong>${formatNumber(totalVariables)}</strong>
      </div>
    </div>
    <div class="pie-legend">
      <div class="pie-highlight">
        <span>Mayor cobertura</span>
        <strong>${escapeHtml(String(leader.city || "Ciudad"))} · ${formatNumber(leader.variables)} variables</strong>
      </div>
      ${validCities.map((item, index) => {
        const pct = Math.max(item.variables, 1) / totalVariables * 100;
        const label = String(item.city || "Ciudad");
        return `
          <button class="pie-legend-row interactive-chart-item" type="button" data-select-type="city" data-select-kind="Ciudad" data-select-label="${escapeHtml(label)}" data-select-value="${item.rows}" data-select-value-label="${escapeHtml(`${formatNumber(item.variables)} variables · ${formatNumber(item.sources)} fuentes · ${formatNumber(item.rows)} registros`)}" data-select-note="Ciudad seleccionada desde la cobertura territorial de variables disponibles.">
            <span class="legend-dot" style="background:${chartPalette[index % chartPalette.length]}"></span>
            <span>${escapeHtml(label)}</span>
            <strong>${percentFormatter.format(pct)}% · ${formatNumber(item.variables)} vars.</strong>
          </button>
        `;
      }).join("")}
    </div>
  `;
  attachInteractiveHandlers(sourcePie);
}

function renderSourceChart(cities) {
  if (!sourceChart) {
    return;
  }
  if (!cities.length) {
    sourceChart.innerHTML = `<p class="trace-empty">No hay ciudades cargadas.</p>`;
    return;
  }
  const maxVariables = Math.max(...cities.map((item) => Number(item.variables) || 0), 1);
  sourceChart.innerHTML = cities.map((item) => {
    const rows = Number(item.rows) || 0;
    const variables = Number(item.variables) || 0;
    const sourceCount = Number(item.sources) || 0;
    const label = String(item.city || "Ciudad");
    const width = Math.max(6, Math.round((variables / maxVariables) * 100));
    return `
      <button class="source-row interactive-chart-item" type="button" data-select-type="city" data-select-kind="Ciudad" data-select-label="${escapeHtml(label)}" data-select-value="${rows}" data-select-value-label="${escapeHtml(`${formatNumber(variables)} variables · ${formatNumber(sourceCount)} fuentes · ${formatNumber(rows)} registros`)}" data-select-note="Ciudad seleccionada desde el grafico de cobertura territorial.">
        <div class="bar-meta">
          <span>${escapeHtml(label)}</span>
          <strong>${formatNumber(variables)} variables · ${formatNumber(sourceCount)} fuentes</strong>
        </div>
        <div class="bar-track">
          <div class="bar-fill" style="width: ${width}%"></div>
        </div>
      </button>
    `;
  }).join("");
  attachInteractiveHandlers(sourceChart);
}

function renderLatestRows(rows) {
  if (!latestRows) {
    return;
  }
  if (!rows.length) {
    latestRows.innerHTML = `<tr><td colspan="4">No hay indicadores recientes.</td></tr>`;
    return;
  }
  latestRows.innerHTML = rows.map((row) => `
    <tr>
      <td>${escapeHtml(String(row.variable || row.metric || ""))}<br><span class="cell-note">${escapeHtml(String(row.period || ""))} &middot; ${escapeHtml(String(row.quality || ""))}</span></td>
      <td>${escapeHtml(String(row.geo || ""))}</td>
      <td>${escapeHtml(formatDashboardValue(row.value, row.unit))}</td>
      <td><span class="status-pill">${escapeHtml(String(row.source || ""))}</span></td>
    </tr>
  `).join("");
}

function formatReceivedAt(value) {
  if (!value) return "Sin fecha de recepcion";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).replace("T", " ");
  return new Intl.DateTimeFormat("es-ES", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function formatDataPeriod(value) {
  if (!value) return "Sin periodo";
  const match = String(value).match(/^(\d{4})-(\d{2})/);
  if (!match) return String(value);
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, 1));
  return new Intl.DateTimeFormat("es-ES", { month: "long", year: "numeric", timeZone: "UTC" }).format(date);
}

function renderCityUpdates(updates) {
  if (!cityUpdateGrid) {
    return;
  }
  if (cityUpdateCount) {
    cityUpdateCount.textContent = `${formatNumber(updates.length)} ciudades`;
  }
  if (!updates.length) {
    cityUpdateGrid.innerHTML = `<p class="trace-empty">No hay recepciones por ciudad registradas.</p>`;
    return;
  }
  cityUpdateGrid.innerHTML = updates.map((item) => `
    <article class="city-update-card">
      <div class="city-update-heading">
        <strong>${escapeHtml(String(item.city || "Ciudad"))}</strong>
        <span>${formatNumber(item.rows)} filas</span>
      </div>
      <div class="city-update-received">
        <span>Recibido por ultima vez</span>
        <time datetime="${escapeHtml(String(item.received_at || ""))}">${escapeHtml(formatReceivedAt(item.received_at))}</time>
      </div>
      <div class="city-update-meta">
        <span>Periodo mas reciente: <strong>${escapeHtml(formatDataPeriod(item.latest_period))}</strong></span>
        <span>${escapeHtml(String(item.sources || "Fuente n/d").replaceAll(",", " · "))}</span>
      </div>
    </article>
  `).join("");
}

function renderIndicatorCatalog(indicators) {
  if (!indicatorCatalogGrid) return;
  if (indicatorCatalogCount) {
    indicatorCatalogCount.textContent = `${formatNumber(indicators.length)} indicadores`;
  }
  if (!indicators.length) {
    indicatorCatalogGrid.innerHTML = `<p class="trace-empty">No hay indicadores catalogados.</p>`;
    return;
  }
  indicatorCatalogGrid.innerHTML = indicators.map((item) => {
    const firstPeriod = formatDataPeriod(item.first_period);
    const latestPeriod = formatDataPeriod(item.latest_period);
    const coverage = firstPeriod === latestPeriod ? latestPeriod : `${firstPeriod} - ${latestPeriod}`;
    const sources = String(item.sources || "Fuente n/d").replaceAll(",", " · ");
    return `
      <article class="indicator-catalog-card">
        <div class="catalog-card-heading">
          <div>
            <span>Indicador</span>
            <h3>${escapeHtml(String(item.variable || "Indicador"))}</h3>
          </div>
          <strong>${formatNumber(item.rows)} registros</strong>
        </div>
        <p class="catalog-description">${escapeHtml(String(item.description || "Indicador disponible para consulta y comparacion territorial."))}</p>
        <dl class="catalog-facts">
          <div><dt>Fuentes</dt><dd>${escapeHtml(sources)}</dd></div>
          <div><dt>Cobertura temporal</dt><dd>${escapeHtml(coverage)}</dd></div>
          <div><dt>Ciudades principales</dt><dd>${formatNumber(item.city_count)} de 7</dd></div>
          <div><dt>Ultima recepcion</dt><dd>${escapeHtml(formatReceivedAt(item.received_at))}</dd></div>
        </dl>
      </article>
    `;
  }).join("");
}

function getDataset() {
  return lastLocalData || datasets[activeTopic] || datasets.general;
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatAssistantText(text) {
  const safeText = escapeHtml(text.trim());
  const blocks = safeText.split(/\n{2,}/).filter(Boolean);

  if (!blocks.length) {
    return "<p>No he recibido una respuesta util.</p>";
  }

  return blocks.map((block) => {
    const withBreaks = block.replace(/\n/g, "<br>");
    return `<p>${withBreaks}</p>`;
  }).join("");
}

function renderTaskStatus(activeLabel = "Pensando", detail = "Preparando la consulta.") {
  const icons = {
    "Pensando": "psychology",
    "Recuperando datos": "database",
    "Generando respuesta": "edit_note",
    "Redactando": "stylus_note"
  };

  return `
    <div class="task-status" aria-live="polite">
      <div class="task-step is-active">
        <span class="material-symbols-outlined">${icons[activeLabel] || "hourglass_top"}</span>
        <strong>${escapeHtml(activeLabel)}</strong>
      </div>
      <p>${escapeHtml(detail)}</p>
    </div>
  `;
}

function renderTraceLog(trace) {
  if (!traceLog) {
    return;
  }

  lastTrace = trace || lastTrace;
  if (trace?.localData?.table?.length) {
    lastLocalData = trace.localData;
  }
  const datasetsUsed = trace?.datasets || [];
  const statusRows = [];

  if (trace?.model) {
    statusRows.push(`
      <div class="trace-row">
        <strong>${escapeHtml(trace.model)}</strong>
        <span>respuesta · limite ${escapeHtml(String(trace.maxTokens ?? "-"))}</span>
      </div>
    `);
  }

  if (trace?.finishReason) {
    const statusText = trace.finishReason === "length"
      ? "cortado por limite de tokens"
      : "respuesta finalizada";
    statusRows.push(`
      <div class="trace-row">
        <strong>${escapeHtml(trace.finishReason)}</strong>
        <span>finish reason · ${statusText}</span>
      </div>
    `);
  }

  if (trace?.analysis) {
    const analysisText = trace.analysis.enabled
      ? `${trace.analysis.items} analisis ejecutados`
      : "no requerido";
    statusRows.push(`
      <div class="trace-row">
        <strong>pandas</strong>
        <span>procesamiento · ${escapeHtml(analysisText)}</span>
      </div>
    `);
  }

  if (!datasetsUsed.length) {
    traceLog.innerHTML = `${statusRows.join("")}<p class="trace-empty">Sin indicadores seleccionados para esta consulta.</p>`;
    return;
  }

  traceLog.innerHTML = statusRows.join("") + datasetsUsed.map((item) => `
      <div class="trace-row">
      <strong>${escapeHtml(item.archivo || "Indicador consultado")}</strong>
      <span>${escapeHtml(item.tipo || "dato")} · score ${escapeHtml(String(item.score ?? "-"))} · ${escapeHtml(item.estado || "seleccionado")}</span>
    </div>
  `).join("");
}

function renderSummary(data) {
  const table = data.table || [];
  return `
    <div class="summary-metrics">
      <div><span>Fuente</span><strong>${data.source}</strong></div>
      <div><span>Confianza</span><strong>${data.confidence}</strong></div>
      <div><span>Variables</span><strong>${table.length}</strong></div>
    </div>
    <div class="mini-table">
      ${table.slice(0, 3).map(([variable, value, source]) => `
        <div><span>${variable}</span><strong>${value} · ${source}</strong></div>
      `).join("")}
    </div>
  `;
}

function renderDataTable(data) {
  const table = data.table || [];
  const headers = data.tableHeaders || ["Variable", "Valor", "Fuente", "Estado"];
  return `
    <div class="data-table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            ${headers.map((header) => `<th>${escapeHtml(String(header || ""))}</th>`).join("")}
          </tr>
        </thead>
        <tbody>
          ${table.map((row) => `
            <tr>
              ${row.map((cell, index) => {
                const value = escapeHtml(String(cell ?? ""));
                return index === row.length - 1
                  ? `<td><span class="status-pill">${value}</span></td>`
                  : `<td>${value}</td>`;
              }).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function formatChartNumber(value) {
  return Number(value).toLocaleString("es-ES", { maximumFractionDigits: 2 });
}

function renderBarChart(chart) {
  const values = chart.values || [];
  const maxValue = Math.max(...values.map((value) => Math.abs(Number(value) || 0)), 1);
  return (chart.labels || []).map((label, index) => {
    const value = Number(values[index]) || 0;
    const percent = Math.max(4, Math.min(100, Math.abs(value) / maxValue * 100));
    const displayValue = chart.displayValues?.[index] || `${formatChartNumber(value)} ${chart.unit || ""}`.trim();
    return `
      <div class="bar-row">
        <div class="bar-meta">
          <span>${escapeHtml(String(label || ""))}</span>
          <strong>${escapeHtml(displayValue)}</strong>
        </div>
        <div class="bar-track"><div class="bar-fill" style="width:${percent}%"></div></div>
      </div>
    `;
  }).join("");
}

function renderLineChart(chart) {
  const labels = chart.labels || [];
  const series = chart.series || [];
  const numericValues = series.flatMap((item) => item.values || []).filter((value) => value != null && Number.isFinite(Number(value)));
  if (labels.length < 2 || !numericValues.length) return "";
  const width = 680;
  const height = 280;
  const left = 64;
  const right = 24;
  const top = 24;
  const bottom = 54;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  let minValue = Math.min(...numericValues);
  let maxValue = Math.max(...numericValues);
  const padding = (maxValue - minValue || Math.abs(maxValue) || 1) * 0.1;
  minValue -= padding;
  maxValue += padding;
  const x = (index) => left + (index / Math.max(1, labels.length - 1)) * plotWidth;
  const y = (value) => top + (1 - (Number(value) - minValue) / (maxValue - minValue)) * plotHeight;
  const grid = Array.from({ length: 5 }, (_, index) => {
    const gridY = top + index * plotHeight / 4;
    const gridValue = maxValue - index * (maxValue - minValue) / 4;
    return `<line x1="${left}" y1="${gridY}" x2="${width - right}" y2="${gridY}" class="chart-grid-line"/><text x="${left - 10}" y="${gridY + 4}" text-anchor="end" class="chart-axis-label">${escapeHtml(formatChartNumber(gridValue))}</text>`;
  }).join("");
  const lines = series.map((item, seriesIndex) => {
    const color = chartPalette[seriesIndex % chartPalette.length];
    const points = (item.values || []).map((value, index) => value == null ? null : `${x(index)},${y(value)}`).filter(Boolean);
    const dots = (item.values || []).map((value, index) => value == null ? "" : `<circle cx="${x(index)}" cy="${y(value)}" r="4" fill="${color}"><title>${escapeHtml(`${item.name}: ${formatChartNumber(value)} ${chart.unit || ""}`)}</title></circle>`).join("");
    return `<polyline points="${points.join(" ")}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${dots}`;
  }).join("");
  const xLabels = labels.map((label, index) => `<text x="${x(index)}" y="${height - 20}" text-anchor="middle" class="chart-axis-label">${escapeHtml(String(label).slice(0, 10))}</text>`).join("");
  return `<div class="chart-svg-wrap"><svg class="adaptive-chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(chart.title || "Serie temporal")}">${grid}${lines}${xLabels}</svg></div>${renderChartLegend(series)}`;
}

function renderRadarChart(chart) {
  const labels = chart.labels || [];
  const series = chart.series || [];
  if (labels.length < 3 || !series.length) return "";
  const width = 680;
  const height = 320;
  const cx = 340;
  const cy = 150;
  const radius = 105;
  const point = (index, value = 100) => {
    const angle = -Math.PI / 2 + index * 2 * Math.PI / labels.length;
    const scaled = radius * Math.max(0, Math.min(100, Number(value) || 0)) / 100;
    return [cx + Math.cos(angle) * scaled, cy + Math.sin(angle) * scaled];
  };
  const rings = [25, 50, 75, 100].map((level) => `<polygon points="${labels.map((_, index) => point(index, level).join(",")).join(" ")}" class="radar-ring"/>`).join("");
  const axes = labels.map((label, index) => {
    const [axisX, axisY] = point(index, 100);
    const [labelX, labelY] = point(index, 122);
    return `<line x1="${cx}" y1="${cy}" x2="${axisX}" y2="${axisY}" class="chart-grid-line"/><text x="${labelX}" y="${labelY}" text-anchor="middle" class="chart-axis-label">${escapeHtml(String(label).slice(0, 22))}</text>`;
  }).join("");
  const polygons = series.map((item, index) => {
    const color = chartPalette[index % chartPalette.length];
    const points = labels.map((_, labelIndex) => point(labelIndex, item.values?.[labelIndex] || 0).join(",")).join(" ");
    return `<polygon points="${points}" fill="${color}" fill-opacity="0.16" stroke="${color}" stroke-width="3"><title>${escapeHtml(item.name)}</title></polygon>`;
  }).join("");
  return `<div class="chart-svg-wrap"><svg class="adaptive-chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(chart.title || "Grafico radar")}">${rings}${axes}${polygons}</svg></div>${renderChartLegend(series)}`;
}

function renderDoughnutChart(chart) {
  const values = (chart.values || []).map((value) => Math.max(0, Number(value) || 0));
  const total = values.reduce((sum, value) => sum + value, 0);
  if (!total) return "";
  const radius = 72;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  const segments = values.map((value, index) => {
    const length = value / total * circumference;
    const segment = `<circle cx="110" cy="110" r="${radius}" fill="none" stroke="${chartPalette[index % chartPalette.length]}" stroke-width="28" stroke-dasharray="${length} ${circumference - length}" stroke-dashoffset="${-offset}" transform="rotate(-90 110 110)"><title>${escapeHtml(`${chart.labels?.[index] || "Valor"}: ${formatChartNumber(value)}`)}</title></circle>`;
    offset += length;
    return segment;
  }).join("");
  const legendSeries = (chart.labels || []).map((name, index) => ({ name: `${name}: ${formatChartNumber(values[index])}` }));
  return `<div class="doughnut-layout"><svg class="doughnut-svg" viewBox="0 0 220 220" role="img" aria-label="${escapeHtml(chart.title || "Distribucion")}">${segments}<text x="110" y="106" text-anchor="middle" class="doughnut-total">Total</text><text x="110" y="130" text-anchor="middle" class="doughnut-value">${escapeHtml(formatChartNumber(total))}</text></svg>${renderChartLegend(legendSeries)}</div>`;
}

function renderChartLegend(series) {
  return `<div class="chart-legend">${(series || []).map((item, index) => `<span><i style="background:${chartPalette[index % chartPalette.length]}"></i>${escapeHtml(String(item.name || "Serie"))}</span>`).join("")}</div>`;
}

function renderChart(data) {
  let chart = data.chart || {};
  if (Array.isArray(chart)) {
    chart = {
      type: "bar",
      title: data.title || "Indicadores",
      labels: chart.map((item) => item[0]),
      values: chart.map((item) => item[1]),
      displayValues: chart.map((item) => item[2])
    };
  }
  if (!chart.type || chart.type === "empty") {
    return `
      <div class="chart-card">
        <p class="trace-empty">No hay valores numericos suficientes para graficar esta consulta.</p>
      </div>
    `;
  }
  const renderers = {
    line: renderLineChart,
    radar: renderRadarChart,
    doughnut: renderDoughnutChart,
    bar: renderBarChart
  };
  const content = (renderers[chart.type] || renderBarChart)(chart);
  return `
    <div class="chart-card adaptive-chart" aria-label="Grafico de ${escapeHtml(String(chart.title || data.title || "Indicadores"))}">
      <div class="chart-card-heading"><div><span>${escapeHtml(String(chart.type || "grafico"))}</span><h3>${escapeHtml(String(chart.title || data.title || "Indicadores"))}</h3></div></div>
      ${content}
      ${chart.reason ? `<p class="chart-reason">${escapeHtml(chart.reason)}</p>` : ""}
    </div>
  `;
}

function getViewData() {
  const data = getDataset();
  return activeView === "coste" ? datasets.coste : data;
}

function getAssistantViewContent(view = activeView) {
  const data = getViewData();
  const requestSummary = lastUserQuestion
    ? `Resumen de la consulta: <strong>${lastUserQuestion}</strong>`
    : "Resumen de la consulta: el usuario aun no ha escrito una pregunta.";

  if (view === "tablas") {
    return `
      <p>${requestSummary}</p>
      <p>He generado una tabla con las variables relacionadas con <strong>${data.title}</strong>.</p>
      ${renderDataTable(data)}
      <p>La tabla se asocia a la pregunta porque agrupa las variables que ayudan a explicar ese tema: valor observado, fuente y estado de disponibilidad.</p>
    `;
  }

  if (view === "graficos") {
    return `
      <p>${requestSummary}</p>
      <p>He generado un grafico con los indicadores recuperados para <strong>${escapeHtml(String(data.title || "Indicadores"))}</strong>.</p>
      ${renderChart(data)}
      <p>El grafico escala los valores numericos de la consulta para comparar magnitudes; la tabla conserva fuente, periodo y calidad.</p>
    `;
  }

  if (view === "coste") {
    return `
      <p>${requestSummary}</p>
      <p>He cambiado la respuesta al modulo de coste de vida general.</p>
      ${renderSummary(data)}
      <p>El foco queda en IPC, energia y fiscalidad disponible, sin convertirlo en un bloque de vivienda.</p>
    `;
  }

  const answer = lastAssistantText || `
    <p>Haz una pregunta y puedo transformar la respuesta en tabla o grafico desde el panel lateral.</p>
    ${renderSummary(data)}
  `;
  if (!lastLocalData?.table?.length) {
    return answer;
  }
  return `
    ${answer}
    <section class="answer-evidence" aria-label="Evidencia utilizada en la respuesta">
      <div class="evidence-heading">
        <div>
          <span>Evidencia utilizada</span>
          <h3>Datos que sostienen la recomendacion</h3>
        </div>
        <strong>${escapeHtml(String(lastLocalData.confidence || "Media"))}</strong>
      </div>
      ${renderDataTable(lastLocalData)}
      ${renderChart(lastLocalData)}
      <p class="evidence-source">Fuente: ${escapeHtml(String(lastLocalData.source || "Base de datos"))}. La tabla conserva territorio, periodo y calidad del dato.</p>
    </section>
  `;
}

function updateLastAssistantView() {
  if (!lastAssistantBody || !messages) {
    return;
  }

  lastAssistantBody.innerHTML = getAssistantViewContent();
  messages.scrollIntoView({ block: "end", behavior: "smooth" });
}

function setActiveTab(view) {
  activeView = view;
  dataTabs.forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.view === view);
  });
  updateLastAssistantView();
}

function addMessage(content, sender) {
  const message = document.createElement("article");
  message.className = "message";

  const avatar = document.createElement("div");
  avatar.className = `avatar ${sender === "user" ? "user" : ""}`;
  avatar.textContent = sender === "user" ? "T" : "I+";

  const body = document.createElement("div");
  body.className = "message-content";

  if (sender === "assistant") {
    body.innerHTML = content;
  } else {
    const paragraph = document.createElement("p");
    paragraph.textContent = content;
    body.appendChild(paragraph);
  }

  message.append(avatar, body);
  messages.appendChild(message);
  messages.scrollIntoView({ block: "end", behavior: "smooth" });

  if (sender === "assistant") {
    lastAssistantBody = body;
  }

  return body;
}

function detectTopic(text) {
  const normalized = text.toLowerCase();
  const match = sampleAnswers.find((answer) =>
    answer.keywords.some((keyword) => normalized.includes(keyword))
  );

  return match || null;
}

function getLocalContext(topic) {
  const data = datasets[topic] || datasets.general;
  return {
    activeTopic: topic,
    dataset: data,
    availableSources: ["INE", "REE", "MITMA/MIVAU", "SEPE", "Idescat", "Open Data BCN"],
    uiViews: ["general", "tablas", "graficos", "coste"]
  };
}

function getConversationHistory() {
  return conversationHistory.slice(-8);
}

function rememberTurn(role, content) {
  const cleanContent = String(content || "").replace(/\s+/g, " ").trim();
  if (!cleanContent) {
    return;
  }
  conversationHistory.push({ role, content: cleanContent });
  conversationHistory = conversationHistory.slice(-10);
}

async function askLocalModel(text, topic) {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      message: text,
      context: getLocalContext(topic),
      history: getConversationHistory(),
      stream: false
    })
  });

  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = payload.detail ? ` Detalle: ${payload.detail}` : ` Estado HTTP: ${response.status}`;
    throw new Error(`${payload.error || "Error generando la respuesta."}${detail}`);
  }

  renderTraceLog(payload.trace);
  return payload.answer;
}

function parseStreamEvents(buffer) {
  const parts = buffer.split("\n\n");
  return {
    events: parts.slice(0, -1),
    rest: parts.at(-1) || ""
  };
}

function readEventPayload(eventText) {
  const eventName = eventText.match(/^event:\s*(.+)$/m)?.[1]?.trim() || "message";
  const dataLines = eventText
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.replace(/^data:\s?/, ""));

  if (!dataLines.length) {
    return { eventName, payload: {} };
  }

  return {
    eventName,
    payload: JSON.parse(dataLines.join("\n"))
  };
}

async function streamLocalModel(text, topic, onDelta, onMeta, onStatus) {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      message: text,
      context: getLocalContext(topic),
      history: getConversationHistory(),
      stream: true
    })
  });

  if (!response.ok || !response.body) {
    return askLocalModel(text, topic);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let fullText = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const parsed = parseStreamEvents(buffer);
    buffer = parsed.rest;

    for (const eventText of parsed.events) {
      const { eventName, payload } = readEventPayload(eventText);

      if (eventName === "delta") {
        fullText += payload.text || "";
        onDelta(fullText);
      }

      if (eventName === "meta") {
        onMeta(payload);
      }

      if (eventName === "status") {
        onStatus?.(payload);
      }

      if (eventName === "done") {
        renderTraceLog({
          ...(lastTrace || {}),
          finishReason: payload.finishReason || "unknown"
        });
        return fullText;
      }

      if (eventName === "error") {
        throw new Error(payload.detail ? `${payload.error} Detalle: ${payload.detail}` : payload.error);
      }
    }
  }

  return fullText;
}

async function sendMessage(text) {
  if (isSending || !form || !input || !messages || !welcomeState) {
    return;
  }

  const cleanText = text.trim();

  if (!cleanText) {
    return;
  }

  setActiveScreen("chatbot");

  const match = detectTopic(cleanText);
  activeTopic = match?.topic || "general";
  activeView = "general";
  lastUserQuestion = cleanText;

  welcomeState.style.display = "none";
  messages.classList.add("is-visible");
  addMessage(cleanText, "user");
  rememberTurn("user", cleanText);
  renderTraceLog({
    datasets: [
      {
        archivo: "Preparando respuesta...",
        tipo: "dato",
        score: "-",
        estado: "pendiente"
      }
    ]
  });
  lastAssistantText = renderTaskStatus("Pensando", "Preparando la consulta.");
  addMessage(lastAssistantText, "assistant");
  input.value = "";
  isSending = true;
  input.disabled = true;
  autoResize();
  dataTabs.forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.view === "general");
  });

  try {
    const answer = await streamLocalModel(
      cleanText,
      activeTopic,
      (partialText) => {
        lastAssistantText = formatAssistantText(partialText);
        if (lastAssistantBody && activeView === "general") {
          lastAssistantBody.innerHTML = lastAssistantText;
          messages.scrollIntoView({ block: "end", behavior: "smooth" });
        }
      },
      renderTraceLog,
      (status) => {
        if (lastAssistantBody && activeView === "general") {
          lastAssistantBody.innerHTML = renderTaskStatus(status.label, status.detail);
          messages.scrollIntoView({ block: "end", behavior: "smooth" });
        }
      }
    );
    lastAssistantText = formatAssistantText(answer);
    rememberTurn("assistant", answer);
  } catch (error) {
    lastLocalData = null;
    const errorMessage = error?.message || "No se pudo obtener una respuesta del proveedor configurado.";
    lastAssistantText = `
      <div class="model-error" role="alert">
        <strong>El modelo fallo</strong>
        <p>${escapeHtml(errorMessage)}</p>
      </div>
    `;
  } finally {
    isSending = false;
    input.disabled = false;
    if (lastAssistantBody) {
      lastAssistantBody.innerHTML = getAssistantViewContent(activeView);
      messages.scrollIntoView({ block: "end", behavior: "smooth" });
    }
    input.focus();
  }
}

form?.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(input.value);
});

input?.addEventListener("input", autoResize);

input?.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage(input.value);
  }
});

promptButtons.forEach((button) => {
  button.addEventListener("click", () => {
    sendMessage(button.dataset.prompt);
  });
});

dataTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    setActiveTab(tab.dataset.view);
  });
});

newChatButton?.addEventListener("click", () => {
  if (!messages || !welcomeState || !input) {
    return;
  }
  messages.innerHTML = "";
  messages.classList.remove("is-visible");
  welcomeState.style.display = "";
  input.value = "";
  activeTopic = "general";
  activeView = "general";
  lastAssistantBody = null;
  lastAssistantText = "";
  lastUserQuestion = "";
  lastTrace = null;
  lastLocalData = null;
  conversationHistory = [];
  dataTabs.forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.view === "general");
  });
  renderTraceLog({ datasets: [] });
  autoResize();
  input.focus();
});

screenTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    const target = tab.dataset.screen;
    if (target === "dashboard" && !dashboardScreen) {
      window.location.href = "dashboard.html";
      return;
    }
    if (target === "chatbot" && !chatbotScreen) {
      window.location.href = "chatbot.html";
      return;
    }
    setActiveScreen(target);
  });
});

openChatbotButton?.addEventListener("click", () => {
  if (!chatbotScreen) {
    window.location.href = "chatbot.html";
    return;
  }
  setActiveScreen("chatbot");
});
refreshDashboardButton?.addEventListener("click", loadDashboard);
clearSelectionButton?.addEventListener("click", clearDashboardSelection);

renderLastUpdateTime();
if (sourceChart || latestRows || cityUpdateGrid || indicatorCatalogGrid) {
  loadDashboard();
}
autoResize();

const initialPrompt = new URLSearchParams(window.location.search).get("prompt");
if (initialPrompt && form && input && messages) {
  sendMessage(initialPrompt);
}
