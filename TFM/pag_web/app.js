const form = document.querySelector("#chatForm");
const input = document.querySelector("#chatInput");
const messages = document.querySelector("#messages");
const welcomeState = document.querySelector("#welcomeState");
const promptButtons = document.querySelectorAll("[data-prompt]");
const newChatButton = document.querySelector(".new-chat");
const dataTabs = document.querySelectorAll("[data-view]");
const lastUpdateTime = document.querySelector("#lastUpdateTime");

let activeTopic = "general";
let activeView = "general";
let lastAssistantBody = null;
let lastAssistantText = "";
let lastUserQuestion = "";

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
    title: "Empleo en Barcelona",
    summary: "Lectura de paro, empleo y actividad economica con fuentes disponibles y pendientes.",
    source: "INE EPA / SEPE / Idescat",
    confidence: "Media",
    table: [
      ["Tasa de paro", "Proxy Catalunya", "INE EPA", "OK"],
      ["Tasa de empleo", "Proxy Catalunya", "INE EPA", "OK"],
      ["Paro registrado", "Municipal", "SEPE", "Manual"],
      ["VAB servicios", "73.729,4", "Idescat", "OK"]
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
    title: "Acceso a salud",
    summary: "Vista de equipamientos, poblacion y cobertura territorial para responder preguntas de bienestar.",
    source: "Open Data BCN / Idescat",
    confidence: "Media",
    table: [
      ["Equipamientos salud", "Por distrito", "Open Data BCN", "Pendiente"],
      ["Poblacion", "1.713.247", "Idescat", "2025"],
      ["Crecimiento poblacion", "15,91", "Idescat", "2024"],
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
    source: "Informe de ejecucion local",
    confidence: "Variable",
    table: [
      ["INE", "IPC / EPA", "CSV / JSON", "OK"],
      ["Idescat", "Indicadores BCN", "CSV / JSON", "OK"],
      ["REE", "Precio / demanda", "CSV", "OK"],
      ["SEPE", "Paro registrado", "XLSX", "Manual"]
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
    topic: "empleo",
    keywords: ["empleo", "trabajo", "paro", "desempleo", "laboral"],
    html: `
      <p>Hay que leerlo como una combinacion de mercado laboral y presion economica, no como una unica causa.</p>
      <p>ISEU miraria si el empleo disponible esta creciendo al mismo ritmo que la poblacion activa, si los sectores fuertes absorben perfiles nuevos y si el coste de vida reduce el margen real de quien busca trabajo.</p>
      <div class="answer-panel">
        <div class="metric-row"><span>Tasa de paro / empleo</span><strong>INE EPA, proxy Catalunya</strong></div>
        <div class="metric-row"><span>Paro registrado municipal</span><strong>SEPE, pendiente manual</strong></div>
        <div class="metric-row"><span>Servicios y comercio</span><strong>Idescat Barcelona</strong></div>
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
        <div class="metric-row"><span>Equipamientos de salud</span><strong>Open Data BCN</strong></div>
        <div class="metric-row"><span>Poblacion de referencia</span><strong>Idescat / BCN</strong></div>
        <div class="metric-row"><span>Lectura ISEU</span><strong>Cobertura + presion demografica</strong></div>
      </div>
      <p>El panel lateral queda filtrado para sanidad, con datos listos para sustituir por scrapers reales.</p>
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
        <div class="metric-row"><span>Fuentes mas solidas</span><strong>INE, Idescat, REE</strong></div>
        <div class="metric-row"><span>Fuentes manuales</span><strong>SEPE, Seguridad Social</strong></div>
        <div class="metric-row"><span>Regla de respuesta</span><strong>Fuente + fecha + territorio + confianza</strong></div>
      </div>
      <p>Asi el usuario entiende de donde sale cada conclusion y donde hay incertidumbre.</p>
    `
  }
];

function autoResize() {
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

function getDataset() {
  return datasets[activeTopic] || datasets.general;
}

function renderSummary(data) {
  return `
    <div class="summary-metrics">
      <div><span>Fuente</span><strong>${data.source}</strong></div>
      <div><span>Confianza</span><strong>${data.confidence}</strong></div>
      <div><span>Variables</span><strong>${data.table.length}</strong></div>
    </div>
    <div class="mini-table">
      ${data.table.slice(0, 3).map(([variable, value, source]) => `
        <div><span>${variable}</span><strong>${value} · ${source}</strong></div>
      `).join("")}
    </div>
  `;
}

function renderDataTable(data) {
  return `
    <div class="data-table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>Variable</th>
            <th>Valor</th>
            <th>Fuente</th>
            <th>Estado</th>
          </tr>
        </thead>
        <tbody>
          ${data.table.map(([variable, value, source, status]) => `
            <tr>
              <td>${variable}</td>
              <td>${value}</td>
              <td>${source}</td>
              <td><span class="status-pill">${status}</span></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderChart(data) {
  return `
    <div class="chart-card" aria-label="Grafico de ${data.title}">
      ${data.chart.map(([label, value]) => `
        <div class="bar-row">
          <div class="bar-meta">
            <span>${label}</span>
            <strong>${value}</strong>
          </div>
          <div class="bar-track">
            <div class="bar-fill" style="width: ${value}%"></div>
          </div>
        </div>
      `).join("")}
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
      <p>La tabla se asocia a la pregunta porque agrupa las variables que ayudan a explicar ese tema: valor observado, fuente y estado de disponibilidad. Estos valores son de maqueta; luego entraran aqui los datos reales de scrapers y APIs.</p>
    `;
  }

  if (view === "graficos") {
    return `
      <p>${requestSummary}</p>
      <p>He generado un grafico rapido para <strong>${data.title}</strong>.</p>
      ${renderChart(data)}
      <p>El grafico resume la misma seleccion de variables en forma visual para comparar intensidad, confianza y presion del pilar detectado.</p>
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

  return lastAssistantText || `
    <p>Haz una pregunta y puedo transformar la respuesta en tabla o grafico desde el panel lateral.</p>
    ${renderSummary(data)}
  `;
}

function updateLastAssistantView() {
  if (!lastAssistantBody) {
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

function getFallbackAnswer() {
  return `
    <p>Puedo orientar la respuesta como lectura ISEU: detectar pilar, buscar variables disponibles y separar dato directo de proxy.</p>
    <div class="answer-panel">
      <div class="metric-row"><span>Pilar detectado</span><strong>General</strong></div>
      <div class="metric-row"><span>Fuentes candidatas</span><strong>INE, Idescat, Open Data BCN</strong></div>
      <div class="metric-row"><span>Siguiente paso</span><strong>Conectar API local</strong></div>
    </div>
    <p>Tambien he dejado listo el panel lateral para tabla o grafico con datos mock.</p>
  `;
}

function sendMessage(text) {
  const cleanText = text.trim();

  if (!cleanText) {
    return;
  }

  const match = detectTopic(cleanText);
  activeTopic = match?.topic || "general";
  activeView = "general";
  lastUserQuestion = cleanText;

  welcomeState.style.display = "none";
  messages.classList.add("is-visible");
  addMessage(cleanText, "user");
  lastAssistantText = `
    <p>Analizando la consulta...</p>
    ${renderSummary(getDataset())}
  `;
  addMessage(lastAssistantText, "assistant");
  input.value = "";
  autoResize();
  dataTabs.forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.view === "general");
  });

  window.setTimeout(() => {
    lastAssistantText = match?.html || getFallbackAnswer();
    if (lastAssistantBody) {
      lastAssistantBody.innerHTML = getAssistantViewContent(activeView);
      messages.scrollIntoView({ block: "end", behavior: "smooth" });
    }
  }, 360);
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(input.value);
});

input.addEventListener("input", autoResize);

input.addEventListener("keydown", (event) => {
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
  messages.innerHTML = "";
  messages.classList.remove("is-visible");
  welcomeState.style.display = "";
  input.value = "";
  activeTopic = "general";
  activeView = "general";
  lastAssistantBody = null;
  lastAssistantText = "";
  lastUserQuestion = "";
  dataTabs.forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.view === "general");
  });
  autoResize();
  input.focus();
});

renderLastUpdateTime();
autoResize();
