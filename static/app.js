const database = document.querySelector("#database");
const databaseLabel = document.querySelector("#database-label");
const schemaList = document.querySelector("#schema-list");
const DB_STORAGE_KEY = "nlq.database";
const schemaDetail = document.querySelector("#schema-detail");
const schemaModalTitle = document.querySelector("#schema-modal-title");
const schemaModalDesc = document.querySelector("#schema-modal-desc");
const schemaModal = document.querySelector("#schema-modal");
const historyList = document.querySelector("#history-list");
const form = document.querySelector("#ask-form");
const question = document.querySelector("#question");
const askButton = document.querySelector("#ask-button");
const newQuestion = document.querySelector("#new-question");
const status = document.querySelector("#status");
const answer = document.querySelector("#answer");
const title = document.querySelector("#title");
const summary = document.querySelector("#summary");
const pipeline = document.querySelector("#pipeline");
const reason = document.querySelector("#reason");
const assumptionsLabel = document.querySelector("#assumptions-label");
const assumptions = document.querySelector("#assumptions");
const error = document.querySelector("#error");
const errorTitle = document.querySelector("#error-title");
const errorDetail = document.querySelector("#error-detail");
const usageStats = document.querySelector("#usage-stats");
const usageByModel = document.querySelector("#usage-by-model");
const usageModel = document.querySelector("#usage-model");
const usageProvider = document.querySelector("#usage-provider");
const settingsModal = document.querySelector("#settings-modal");
const historyRetentionDays = document.querySelector("#history-retention-days");
const historyRetentionSave = document.querySelector("#history-retention-save");
const historyRetentionStatus = document.querySelector("#history-retention-status");
const usageAsksCanvas = document.querySelector("#usage-asks-chart");
const usageTokensCanvas = document.querySelector("#usage-tokens-chart");
const usageOutcomesCanvas = document.querySelector("#usage-outcomes-chart");
const usageChartsCanvas = document.querySelector("#usage-charts-chart");
const usageModelsCanvas = document.querySelector("#usage-models-chart");
const modelsList = document.querySelector("#models-list");
const modelsStatus = document.querySelector("#models-status");
const datasetsList = document.querySelector("#datasets-list");
const datasetMapping = document.querySelector("#dataset-mapping");
const mappingSummary = document.querySelector("#mapping-summary");
const mappingReview = document.querySelector("#mapping-review");
const mappingLinks = document.querySelector("#mapping-links");
const sidebar = document.querySelector("#sidebar");
const sqlLabel = document.querySelector("#sql-label");
const sql = document.querySelector("#sql");
const result = document.querySelector("#result");
const chartWrap = document.querySelector("#chart-wrap");
const chartCanvas = document.querySelector("#chart");
const viewBar = document.querySelector("#view-bar");
const showChart = document.querySelector("#show-chart");
const showTableButton = document.querySelector("#show-table");
const chartKind = document.querySelector("#chart-kind");
const how = document.querySelector("#how");
const howPanel = document.querySelector("#how-panel");
const exportMenu = document.querySelector("#export-menu");
const exportCsv = document.querySelector("#export-csv");
const exportPng = document.querySelector("#export-png");
const exportPngItem = document.querySelector("#export-png-item");
const refine = document.querySelector("#refine");
const fields = document.querySelector("#fields");
const filters = document.querySelector("#filters");
const addFilter = document.querySelector("#add-filter");
const refetchButton = document.querySelector("#refetch");
const sortColumn = document.querySelector("#sort-col");
const sortDir = document.querySelector("#sort-dir");
const ideas = document.querySelector("#ideas");
const ideasList = document.querySelector("#ideas-list");
const OPS = ["=", "!=", "<", ">", "<=", ">=", "like"];

const BAR = "#0c6b52";
const SOFT = "#9bb8ae";
const DANGER = "#8d2f2f";
let chart;
let usageCharts = [];
let current = null;
let selectedId = null;
let view = "chart";

const valueLabels = {
  id: "valueLabels",
  afterDatasetsDraw(drawing) {
    if (drawing.config.type !== "bar") {
      return;
    }
    const context = drawing.ctx;
    drawing.data.datasets.forEach((dataset, series) => {
      const meta = drawing.getDatasetMeta(series);
      meta.data.forEach((bar, index) => {
        const raw = dataset.data[index];
        context.save();
        context.fillStyle = "#1c1915";
        context.font = "13px Segoe UI, Helvetica Neue, sans-serif";
        context.textBaseline = "middle";
        context.textAlign = "left";
        context.fillText(formatNumber(raw), bar.x + 8, bar.y);
        context.restore();
      });
    });
  },
};

function clear(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function cell(text) {
  const item = document.createElement("td");
  item.textContent = text == null ? "" : String(text);
  return item;
}

function headingCell(text) {
  const item = document.createElement("th");
  item.textContent = text == null ? "" : String(text);
  return item;
}

function formatNumber(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return value == null ? "" : String(value);
  }
  const digits = Number.isInteger(value) ? 0 : 2;
  return value.toLocaleString("en-US", {minimumFractionDigits: digits, maximumFractionDigits: digits});
}

function highlight(spec, columns, rows) {
  if (!spec || spec.type === "table" || !rows.length) {
    return "";
  }
  const xIndex = columns.indexOf(spec.x);
  const yName = (spec.y || [])[0];
  const yIndex = columns.indexOf(yName);
  if (xIndex < 0 || yIndex < 0) {
    return "";
  }
  let best = rows[0];
  rows.forEach((row) => {
    if (typeof row[yIndex] === "number" && row[yIndex] > best[yIndex]) {
      best = row;
    }
  });
  const label = best[xIndex] == null ? "" : String(best[xIndex]);
  if (typeof best[yIndex] !== "number") {
    return label;
  }
  return "The biggest is " + label + ", worth " + formatNumber(best[yIndex]) + ".";
}

function hideChart() {
  if (chart) {
    chart.destroy();
    chart = null;
  }
  chartWrap.hidden = true;
}

function renderChart(spec, columns, rows) {
  hideChart();
  if (!spec || spec.type === "table" || !rows.length || typeof globalThis.Chart !== "function") {
    return;
  }
  const xIndex = columns.indexOf(spec.x);
  const yIndexes = (spec.y || []).map((name) => columns.indexOf(name)).filter((index) => index >= 0);
  if (xIndex < 0 || !yIndexes.length) {
    return;
  }
  chartWrap.hidden = false;
  chartWrap.style.height = spec.type === "bar" ? Math.max(260, rows.length * 52) + "px" : "320px";
  const labels = rows.map((row) => row[xIndex] == null ? "" : String(row[xIndex]));
  const datasets = yIndexes.map((index, series) => {
    const color = series === 0 ? BAR : ["#c47b2b", "#3d5a80", "#8d2f2f", "#5e574c"][series % 4];
    return {
      label: spec.y[series],
      data: spec.type === "scatter"
        ? rows.map((row) => ({x: row[xIndex], y: row[index]}))
        : rows.map((row) => row[index]),
      backgroundColor: color,
      borderColor: color,
      borderRadius: 3,
      barThickness: 22,
    };
  });
  const horizontal = spec.type === "bar";
  chart = new globalThis.Chart(chartCanvas, {
    type: spec.type,
    data: spec.type === "scatter" ? {datasets} : {labels, datasets},
    plugins: [valueLabels],
    options: {
      indexAxis: horizontal ? "y" : "x",
      responsive: true,
      maintainAspectRatio: false,
      layout: {padding: {right: horizontal ? 78 : 8}},
      plugins: {legend: {display: datasets.length > 1 || spec.type === "pie"}},
      scales: spec.type === "pie" || spec.type === "scatter" ? {} : {
        x: {display: !horizontal, grid: {display: false}, border: {display: false}},
        y: {grid: {display: false}, border: {display: false}},
      },
    },
  });
}

function renderTable(headers, rows) {
  clear(result);
  if (!headers.length) {
    return;
  }
  const table = document.createElement("table");
  table.className = "table table-sm";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  headers.forEach((header) => headRow.appendChild(headingCell(header)));
  head.appendChild(headRow);
  const body = document.createElement("tbody");
  rows.forEach((row) => {
    const line = document.createElement("tr");
    row.forEach((value) => line.appendChild(cell(typeof value === "number" ? formatNumber(value) : value)));
    body.appendChild(line);
  });
  table.appendChild(head);
  table.appendChild(body);
  result.appendChild(table);
}

function renderSchemaColumns(columns) {
  const headers = ["name", "type", "key", "comment"];
  const rows = columns.map((column) => [column.name, column.type, column.key, column.comment]);
  const table = document.createElement("table");
  table.className = "table table-sm";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  headers.forEach((header) => headRow.appendChild(headingCell(header)));
  head.appendChild(headRow);
  const body = document.createElement("tbody");
  rows.forEach((row) => {
    const line = document.createElement("tr");
    row.forEach((value) => line.appendChild(cell(value)));
    body.appendChild(line);
  });
  table.appendChild(head);
  table.appendChild(body);
  schemaDetail.appendChild(table);
}

function chartExportable() {
  if (!current || current.answer_type === "schema") {
    return false;
  }
  const type = (chartKind && chartKind.value) || (current.chart && current.chart.type) || "";
  return view === "chart" && ["bar", "line", "pie", "scatter"].includes(type) && rowsOf(current).length > 0;
}

function syncExportPng() {
  if (exportPngItem) {
    exportPngItem.hidden = !chartExportable();
  }
}

function paint() {
  if (!current) {
    return;
  }
  const data = current;
  const columns = data.columns || [];
  const rows = data.rows || [];
  const chartable = data.answer_type !== "schema" && data.chart && data.chart.type !== "table" && rows.length;
  viewBar.hidden = !canRefine();
  showChart.parentElement.hidden = !(data.answer_type !== "schema" && data.chart && data.chart.type !== "table");
  showChart.classList.toggle("is-on", view === "chart");
  showTableButton.classList.toggle("is-on", view === "table");
  chartKind.parentElement.hidden = view !== "chart" || showChart.parentElement.hidden;
  if (data.answer_type === "schema") {
    hideChart();
    result.hidden = false;
    renderTable(
      ["table", "name", "type", "key", "comment"],
      columns.map((column) => [column.table, column.name, column.type, column.key, column.comment])
    );
    syncExportPng();
    return;
  }
  if (view === "chart" && chartable) {
    clear(result);
    result.hidden = true;
    renderChart({...data.chart, type: chartKind.value}, columns, rows);
    syncExportPng();
    return;
  }
  hideChart();
  result.hidden = false;
  renderTable(columns, rows);
  syncExportPng();
}

function stringColumns(columns) {
  if (!columns || !columns.length || typeof columns[0] !== "string") {
    return [];
  }
  return columns.slice();
}

function fillSelect(select, names, blank) {
  clear(select);
  if (blank) {
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = blank;
    select.appendChild(empty);
  }
  names.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    select.appendChild(option);
  });
}

function buildRefine(names) {
  clear(fields);
  names.forEach((name) => {
    const label = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = name;
    box.checked = true;
    label.appendChild(box);
    label.appendChild(document.createTextNode(name));
    fields.appendChild(label);
  });
  clear(filters);
  addCondition(names);
  fillSelect(sortColumn, names, "None");
}

function addCondition(names) {
  const row = document.createElement("div");
  row.className = "condition";
  const column = document.createElement("select");
  column.className = "form-select form-select-sm cond-col";
  fillSelect(column, names, "Column");
  const op = document.createElement("select");
  op.className = "form-select form-select-sm cond-op";
  OPS.forEach((item) => {
    const option = document.createElement("option");
    option.value = item;
    option.textContent = item;
    op.appendChild(option);
  });
  const value = document.createElement("input");
  value.className = "form-control form-control-sm cond-value";
  value.type = "text";
  value.placeholder = "Value";
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "remove-condition";
  remove.setAttribute("aria-label", "Remove condition");
  remove.textContent = "×";
  remove.addEventListener("click", () => row.remove());
  row.appendChild(column);
  row.appendChild(op);
  row.appendChild(value);
  row.appendChild(remove);
  filters.appendChild(row);
}

function viewSpec() {
  const columns = [];
  fields.querySelectorAll("input").forEach((box) => {
    if (box.checked) {
      columns.push(box.value);
    }
  });
  const chosen = [];
  filters.querySelectorAll(".condition").forEach((row) => {
    const column = row.querySelector(".cond-col").value;
    const op = row.querySelector(".cond-op").value;
    const value = row.querySelector(".cond-value").value;
    if (column && value !== "") {
      chosen.push({col: column, op: op, value: value});
    }
  });
  const sort = sortColumn.value ? [{col: sortColumn.value, dir: sortDir.value}] : [];
  return {columns: columns, filters: chosen, sort: sort, page: 1, page_size: 1000};
}

function csvCell(value) {
  const text = value == null ? "" : String(value);
  if (/[",\n]/.test(text)) {
    return '"' + text.replaceAll('"', '""') + '"';
  }
  return text;
}

function downloadBlob(blob, filename) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

function exportName() {
  return (current && current.title ? current.title : "nlq").replace(/[^\w.-]+/g, "_");
}

function exportRows() {
  if (!current || !current.rows || !current.rows.length) {
    return;
  }
  const columns = current.columns || [];
  const lines = [columns.map(csvCell).join(",")];
  current.rows.forEach((row) => lines.push(row.map(csvCell).join(",")));
  downloadBlob(new Blob([lines.join("\n")], {type: "text/csv"}), exportName() + ".csv");
}

function exportChartPng() {
  if (!chartExportable() || !chart) {
    return;
  }
  if (!chart || chartWrap.hidden) {
    status.textContent = "Switch to Chart to save a PNG.";
    return;
  }
  const link = document.createElement("a");
  link.href = chart.toBase64Image("image/png", 1);
  link.download = exportName() + ".png";
  link.click();
}

function showError(data) {
  const nice = data.error_title
    ? {title: data.error_title, detail: data.error || ""}
    : friendlyError(data.error);
  if (!nice) {
    error.hidden = true;
    errorTitle.textContent = "";
    errorDetail.textContent = "";
    return;
  }
  error.hidden = false;
  errorTitle.textContent = nice.title;
  errorDetail.textContent = nice.detail;
}

function friendlyError(raw) {
  if (!raw) {
    return null;
  }
  const text = String(raw);
  const lower = text.toLowerCase();
  if (text.includes("503") || lower.includes("high demand") || lower.includes("unavailable")) {
    return {
      title: "Model is busy",
      detail: "The language model is under high demand right now. Wait a moment and ask again.",
    };
  }
  if (text.includes("401") || lower.includes("api key")) {
    return {
      title: "API key problem",
      detail: "Check the active provider key in your .env file, then restart the server.",
    };
  }
  if (text.includes("404") && lower.includes("model")) {
    return {
      title: "Model not found",
      detail: "The configured model name is not available. Update the model in .env.",
    };
  }
  if (lower.includes("timeout") || lower.includes("exceeded")) {
    return {
      title: "Query timed out",
      detail: "The SQL ran too long. Narrow the question or add a tighter filter.",
    };
  }
  return {title: "Something went wrong", detail: text.slice(0, 240)};
}

function closeSidebar() {
  if (!sidebar || !window.bootstrap || !bootstrap.Offcanvas) {
    return;
  }
  if (window.matchMedia("(min-width: 992px)").matches) {
    return;
  }
  const panel = bootstrap.Offcanvas.getInstance(sidebar);
  if (panel) {
    panel.hide();
  }
}

function pipelineNote(data) {
  const parts = [];
  const pick = data.pick || "skipped";
  const repair = Number(data.repair || 0);
  if (pick === "ok") {
    parts.push("Picked a table subset for a large schema.");
  } else if (pick === "failed") {
    parts.push("Table pick failed; used the full schema.");
  }
  if (repair > 0) {
    const word = repair === 1 ? "retry" : "retries";
    if (data.error) {
      parts.push(
        "SQL still failed after " +
          repair +
          " repair " +
          word +
          " (generated again after database errors)."
      );
    } else {
      parts.push(
        "SQL fixed after " +
          repair +
          " repair " +
          word +
          " (regenerated after the database rejected an earlier query)."
      );
    }
  }
  return parts.join(" ");
}

function showPipeline(data) {
  if (!pipeline) {
    return;
  }
  const note = pipelineNote(data);
  clear(pipeline);
  if (!note) {
    pipeline.hidden = true;
    return;
  }
  pipeline.hidden = false;
  const repair = Number(data.repair || 0);
  if (repair > 0) {
    const badge = document.createElement("span");
    badge.className = "badge pipeline-badge me-2";
    badge.textContent = data.error ? "Repair failed" : "Repaired ×" + repair;
    pipeline.appendChild(badge);
  }
  pipeline.appendChild(document.createTextNode(note));
}

function showAnswer(data, options) {
  const previousColumns = current && current.sourceColumns;
  current = data;
  answer.hidden = false;
  title.textContent = data.title || "";
  summary.textContent = data.error ? "" : highlight(data.chart, data.columns || [], data.rows || []);
  showPipeline(data);
  showError(data);
  clear(assumptions);
  const notes = data.assumptions || [];
  assumptionsLabel.hidden = notes.length === 0;
  notes.forEach((item) => {
    const line = document.createElement("li");
    line.textContent = item;
    assumptions.appendChild(line);
  });
  reason.textContent = data.reason || "";
  sqlLabel.hidden = !data.sql;
  sql.textContent = data.sql || "";
  const hasHow = Boolean(data.sql || notes.length || data.reason || Number(data.repair || 0) > 0);
  how.hidden = !hasHow;
  howPanel.hidden = true;
  const chartable = data.answer_type !== "schema" && data.chart && data.chart.type !== "table";
  const keep = options && options.keepRefine;
  if (!keep) {
    view = chartable ? "chart" : "table";
    if (chartable && ["bar", "line", "pie", "scatter"].includes(data.chart.type)) {
      chartKind.value = data.chart.type;
    }
  }
  const names = stringColumns(data.columns);
  const keptColumns = keep ? (data.sourceColumns || previousColumns) : null;
  if (keptColumns && keptColumns.length) {
    current.sourceColumns = keptColumns;
  } else {
    current.sourceColumns = names;
    buildRefine(names);
  }
  refine.hidden = !canRefine();
  exportMenu.hidden = !rowsOf(data).length;
  ideas.hidden = true;
  paint();
  syncExportPng();
  closeSidebar();
}

function canRefine() {
  return Boolean(
    current && current.answer_type !== "schema" && current.id && (current.sourceColumns || []).length
  );
}

function rowsOf(data) {
  return data.rows || [];
}

function resetQuestion() {
  question.value = "";
  current = null;
  selectedId = null;
  answer.hidden = true;
  exportMenu.hidden = true;
  status.textContent = "";
  if (pipeline) {
    clear(pipeline);
    pipeline.hidden = true;
  }
  loadHistory();
  showIdeas();
  question.focus();
}

function ideasEmpty(message) {
  const empty = document.createElement("li");
  empty.className = "text-muted small";
  empty.textContent = message;
  ideasList.appendChild(empty);
}

async function showIdeas() {
  clear(ideasList);
  ideas.hidden = false;
  answer.hidden = true;
  if (!database.value) {
    ideasEmpty("Select a dataset in Settings first.");
    return;
  }
  const response = await fetch("/recommendations?database=" + encodeURIComponent(database.value));
  if (!response.ok) {
    ideasEmpty(
      "No recommendations yet. Add recommendations/" +
        database.value +
        ".json, or open this page once with a working LLM so they can be generated."
    );
    return;
  }
  const items = await response.json();
  if (!Array.isArray(items) || !items.length) {
    ideasEmpty(
      "No recommendations yet. They load from recommendations/" +
        database.value +
        ".json, or are generated on first visit when the LLM is configured."
    );
    return;
  }
  items.forEach((item) => {
    const line = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = item.question;
    button.addEventListener("click", () => tryRecommendation(item));
    line.appendChild(button);
    ideasList.appendChild(line);
  });
  closeSidebar();
}

async function tryRecommendation(item) {
  question.value = item.question;
  askButton.disabled = true;
  status.textContent = "Running…";
  try {
    const response = await fetch("/try", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        question: item.question,
        sql: item.sql,
        database: database.value,
      }),
    });
    const data = await response.json();
    selectedId = data.id;
    showAnswer(data);
    status.textContent = "";
    loadHistory();
  } catch (exc) {
    status.textContent = "";
    showAnswer({title: "", error: "The request failed.", assumptions: [], sql: null, columns: [], rows: []});
  } finally {
    askButton.disabled = false;
  }
}

function statsRow(n, label, value) {
  const row = document.createElement("tr");
  const index = document.createElement("td");
  index.textContent = String(n);
  const metric = document.createElement("td");
  metric.textContent = label;
  const amount = document.createElement("td");
  amount.className = "text-end";
  amount.textContent = String(value);
  row.appendChild(index);
  row.appendChild(metric);
  row.appendChild(amount);
  usageStats.appendChild(row);
}

function destroyUsageCharts() {
  usageCharts.forEach((item) => item.destroy());
  usageCharts = [];
}

function makeUsageChart(canvas, config) {
  if (!canvas || typeof Chart === "undefined") {
    return;
  }
  usageCharts.push(new Chart(canvas, config));
}

function renderUsageCharts(data) {
  destroyUsageCharts();
  const days = (data.asks_by_day || []).map((item) => item.day);
  const models = data.by_model || [];
  makeUsageChart(usageModelsCanvas, {
    type: "bar",
    data: {
      labels: models.map((item) => item.model),
      datasets: [
        {label: "Ok", data: models.map((item) => item.ok), backgroundColor: BAR},
        {label: "Error", data: models.map((item) => item.error), backgroundColor: DANGER},
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {legend: {position: "bottom"}},
      scales: {x: {stacked: true}, y: {stacked: true, beginAtZero: true, ticks: {precision: 0}}},
    },
  });
  makeUsageChart(usageAsksCanvas, {
    type: "bar",
    data: {
      labels: days,
      datasets: [
        {label: "Ok", data: (data.asks_by_day || []).map((item) => item.ok), backgroundColor: BAR},
        {label: "Error", data: (data.asks_by_day || []).map((item) => item.error), backgroundColor: DANGER},
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {legend: {position: "bottom"}},
      scales: {x: {stacked: true}, y: {stacked: true, beginAtZero: true, ticks: {precision: 0}}},
    },
  });
  makeUsageChart(usageTokensCanvas, {
    type: "line",
    data: {
      labels: (data.tokens_by_day || []).map((item) => item.day),
      datasets: [
        {
          label: "Tokens in",
          data: (data.tokens_by_day || []).map((item) => item.tokens_in),
          borderColor: BAR,
          backgroundColor: BAR,
          tension: 0.25,
        },
        {
          label: "Tokens out",
          data: (data.tokens_by_day || []).map((item) => item.tokens_out),
          borderColor: SOFT,
          backgroundColor: SOFT,
          tension: 0.25,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {legend: {position: "bottom"}},
      scales: {y: {beginAtZero: true}},
    },
  });
  makeUsageChart(usageOutcomesCanvas, {
    type: "doughnut",
    data: {
      labels: ["Ok", "Failed"],
      datasets: [{
        data: [data.outcomes?.ok || 0, data.outcomes?.error || 0],
        backgroundColor: [BAR, DANGER],
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {legend: {position: "bottom"}},
    },
  });
  makeUsageChart(usageChartsCanvas, {
    type: "doughnut",
    data: {
      labels: ["Charts ok", "Chart failures"],
      datasets: [{
        data: [data.charts?.ok || 0, data.charts?.failed || 0],
        backgroundColor: [BAR, DANGER],
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {legend: {position: "bottom"}},
    },
  });
}

function renderByModel(rows) {
  clear(usageByModel);
  if (!rows.length) {
    const empty = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.textContent = "No model usage yet.";
    empty.appendChild(cell);
    usageByModel.appendChild(empty);
    return;
  }
  rows.forEach((item) => {
    const row = document.createElement("tr");
    const values = [
      item.model,
      item.asks,
      item.ok,
      item.error,
      (item.tokens_in || 0) + (item.tokens_out || 0),
    ];
    values.forEach((value, index) => {
      const cell = document.createElement("td");
      if (index > 0) {
        cell.className = "text-end";
      }
      cell.textContent = String(value);
      row.appendChild(cell);
    });
    usageByModel.appendChild(row);
  });
}

async function loadUsage() {
  clear(usageStats);
  clear(usageByModel);
  const response = await fetch("/usage");
  if (!response.ok) {
    usageModel.textContent = "Unavailable";
    usageProvider.textContent = "";
    statsRow(1, "Status", "Unavailable");
    destroyUsageCharts();
    return;
  }
  const data = await response.json();
  usageModel.textContent = data.model || "—";
  usageProvider.textContent = data.provider ? "Provider: " + data.provider : "";
  (data.stats || []).forEach((item) => statsRow(item.n, item.label, item.value));
  renderByModel(data.by_model || []);
  renderUsageCharts(data);
}

async function loadModels() {
  clear(modelsList);
  modelsStatus.textContent = "";
  const response = await fetch("/models");
  if (!response.ok) {
    modelsStatus.textContent = "Could not load models.";
    return;
  }
  const items = await response.json();
  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "model-card" + (item.active ? " is-on" : "");
    const copy = document.createElement("div");
    const title = document.createElement("div");
    title.className = "fw-semibold";
    title.textContent = item.label;
    const note = document.createElement("div");
    note.className = "small text-muted";
    note.textContent = (item.model || "No model set") + (item.configured ? "" : " · not configured");
    copy.appendChild(title);
    copy.appendChild(note);
    const action = document.createElement("button");
    action.type = "button";
    action.className = "btn btn-sm " + (item.active ? "btn-accent" : "btn-outline-secondary");
    action.textContent = item.active ? "Active" : "Use";
    action.disabled = item.active || !item.configured;
    action.addEventListener("click", async () => {
      modelsStatus.textContent = "Switching…";
      const result = await fetch("/settings/model", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({provider: item.id}),
      });
      const body = await result.json();
      if (!result.ok) {
        modelsStatus.textContent = typeof body.detail === "string" ? body.detail : "Could not switch model.";
        return;
      }
      modelsStatus.textContent = "Using " + (body.model || body.id);
      loadModels();
      loadUsage();
    });
    card.appendChild(copy);
    card.appendChild(action);
    modelsList.appendChild(card);
  });
}

async function loadSettingsDatasets() {
  clear(datasetsList);
  const response = await fetch("/databases");
  const items = response.ok ? await response.json() : [];
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "text-muted small";
    empty.textContent = "No datasets found.";
    datasetsList.appendChild(empty);
    datasetMapping.hidden = true;
    return;
  }
  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "dataset-card" + (item.id === database.value ? " is-on" : "");
    const copy = document.createElement("div");
    const titleEl = document.createElement("div");
    titleEl.className = "fw-semibold";
    const icon = document.createElement("i");
    icon.className = "bi bi-database me-1";
    icon.setAttribute("aria-hidden", "true");
    titleEl.appendChild(icon);
    titleEl.appendChild(document.createTextNode(item.label || item.id));
    const note = document.createElement("div");
    note.className = "small text-muted";
    note.textContent = item.id + " · " + (item.tables || 0) + " tables · " + (item.path || "");
    copy.appendChild(titleEl);
    copy.appendChild(note);
    const action = document.createElement("button");
    action.type = "button";
    action.className = "btn btn-sm " + (item.id === database.value ? "btn-accent" : "btn-outline-secondary");
    action.textContent = item.id === database.value ? "Selected" : "Select";
    action.disabled = item.id === database.value;
    action.addEventListener("click", () => {
      setDatabase(item.id, item.label || item.id);
      loadSettingsDatasets();
    });
    card.appendChild(copy);
    card.appendChild(action);
    datasetsList.appendChild(card);
  });
  await loadDatasetMapping(database.value);
}

function statusBadge(status) {
  const badge = document.createElement("span");
  const kind = status || "guessed";
  badge.className = "badge mapping-badge mapping-badge-" + kind;
  const icon = document.createElement("i");
  icon.className = "bi me-1";
  icon.setAttribute("aria-hidden", "true");
  if (kind === "declared") icon.classList.add("bi-bookmark-check");
  else if (kind === "confirmed") icon.classList.add("bi-check-circle");
  else if (kind === "rejected") icon.classList.add("bi-x-circle");
  else icon.classList.add("bi-question-circle");
  badge.appendChild(icon);
  badge.appendChild(document.createTextNode(kind));
  return badge;
}

async function loadDatasetMapping(datasetId) {
  clear(mappingLinks);
  clear(mappingReview);
  mappingReview.hidden = true;
  if (!datasetId) {
    datasetMapping.hidden = true;
    return;
  }
  const response = await fetch("/datasets/" + encodeURIComponent(datasetId) + "/mapping");
  if (!response.ok) {
    datasetMapping.hidden = true;
    return;
  }
  const data = await response.json();
  datasetMapping.hidden = false;
  const links = data.links || [];
  mappingSummary.textContent =
    (data.label || datasetId) +
    " · " +
    (data.tables || []).length +
    " tables · " +
    links.length +
    " links" +
    (data.generated_at ? " · profiled " + data.generated_at : "");

  const review = links.filter((link) => link.needs_review);
  if (review.length) {
    mappingReview.hidden = false;
    const heading = document.createElement("div");
    heading.className = "small fw-semibold mb-2";
    const warn = document.createElement("i");
    warn.className = "bi bi-exclamation-triangle me-1";
    warn.setAttribute("aria-hidden", "true");
    heading.appendChild(warn);
    heading.appendChild(document.createTextNode("Review uncertain links"));
    mappingReview.appendChild(heading);
    review.forEach((link) => {
      const row = document.createElement("div");
      row.className = "mapping-review-row";
      const text = document.createElement("div");
      text.className = "small";
      text.textContent = (link.foreign_key || "") + " → " + (link.primary_key || "");
      const actions = document.createElement("div");
      actions.className = "btn-group btn-group-sm";
      actions.appendChild(linkActionButton(datasetId, link, "confirmed", "Confirm", "bi-check-lg"));
      actions.appendChild(linkActionButton(datasetId, link, "rejected", "Reject", "bi-x-lg"));
      const skip = document.createElement("button");
      skip.type = "button";
      skip.className = "btn btn-outline-secondary";
      skip.textContent = "Not now";
      skip.addEventListener("click", () => row.remove());
      actions.appendChild(skip);
      row.appendChild(text);
      row.appendChild(actions);
      mappingReview.appendChild(row);
    });
  }

  if (!links.length) {
    const empty = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "text-muted small";
    cell.textContent = "No links yet.";
    empty.appendChild(cell);
    mappingLinks.appendChild(empty);
    return;
  }

  links.forEach((link) => {
    const row = document.createElement("tr");
    const fk = document.createElement("td");
    fk.textContent = link.foreign_key || "";
    const pk = document.createElement("td");
    pk.textContent = link.primary_key || "";
    const status = document.createElement("td");
    status.appendChild(statusBadge(link.status));
    if (link.needs_review) {
      const flag = document.createElement("span");
      flag.className = "badge text-bg-warning ms-1";
      flag.textContent = "review";
      status.appendChild(flag);
    }
    const conf = document.createElement("td");
    conf.textContent = link.confidence == null ? "" : String(link.confidence);
    const reasonCell = document.createElement("td");
    reasonCell.className = "small text-muted";
    reasonCell.textContent = link.reason || "";
    const actions = document.createElement("td");
    const group = document.createElement("div");
    group.className = "btn-group btn-group-sm";
    appendLinkActions(group, datasetId, link);
    actions.appendChild(group);
    row.appendChild(fk);
    row.appendChild(pk);
    row.appendChild(status);
    row.appendChild(conf);
    row.appendChild(reasonCell);
    row.appendChild(actions);
    mappingLinks.appendChild(row);
  });
}

function appendLinkActions(group, datasetId, link) {
  const status = link.status || "guessed";
  // Engine FKs need no Confirm/Reject. reason "declared" covers migrated confirmed rows.
  if (status === "declared" || link.reason === "declared") {
    return;
  }
  // guessed / rejected → Confirm. confirmed → Reject only. rejected → Confirm only.
  if (status !== "confirmed") {
    group.appendChild(linkActionButton(datasetId, link, "confirmed", "Confirm", "bi-check-lg"));
  }
  if (status !== "rejected") {
    group.appendChild(linkActionButton(datasetId, link, "rejected", "Reject", "bi-x-lg"));
  }
}

function linkActionButton(datasetId, link, status, label, iconName) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "btn " + (status === "confirmed" ? "btn-outline-success" : "btn-outline-danger");
  const icon = document.createElement("i");
  icon.className = "bi " + iconName + " me-1";
  icon.setAttribute("aria-hidden", "true");
  button.appendChild(icon);
  button.appendChild(document.createTextNode(label));
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      const response = await fetch("/datasets/" + encodeURIComponent(datasetId) + "/links", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          primary_key: link.primary_key,
          foreign_key: link.foreign_key,
          status,
        }),
      });
      if (!response.ok) {
        let detail = "Could not update link in hints/" + datasetId + ".json";
        try {
          const body = await response.json();
          if (body && body.detail) detail = String(body.detail);
        } catch (exc) {
          /* keep default */
        }
        mappingSummary.textContent = detail;
        return;
      }
      await loadDatasetMapping(datasetId);
    } catch (exc) {
      mappingSummary.textContent = "Could not update link in hints/" + datasetId + ".json";
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

function setDatabase(id, label) {
  database.value = id || "";
  databaseLabel.textContent = label || id || "No dataset";
  try {
    if (id) localStorage.setItem(DB_STORAGE_KEY, id);
  } catch (exc) {
    /* ignore */
  }
  database.dispatchEvent(new Event("change"));
}

async function loadDatabases() {
  const response = await fetch("/databases");
  const items = response.ok ? await response.json() : [];
  let preferred = "";
  try {
    preferred = localStorage.getItem(DB_STORAGE_KEY) || "";
  } catch (exc) {
    preferred = "";
  }
  if (!preferred) preferred = database.value;
  if (!items.length) {
    setDatabase("ecommerce", "Online shop");
    return;
  }
  const match = items.find((item) => item.id === preferred) || items[0];
  setDatabase(match.id, match.label || match.id);
}

async function loadSchema() {
  clear(schemaList);
  if (!database.value) {
    const empty = document.createElement("li");
    empty.className = "text-muted small";
    empty.textContent = "Select a dataset in Settings.";
    schemaList.appendChild(empty);
    return;
  }
  const response = await fetch("/schema?database=" + encodeURIComponent(database.value));
  let tables = [];
  try {
    tables = await response.json();
  } catch (exc) {
    tables = null;
  }
  if (!response.ok || !Array.isArray(tables)) {
    const empty = document.createElement("li");
    empty.className = "text-muted small";
    empty.textContent = "Could not load schema for " + database.value + ".";
    schemaList.appendChild(empty);
    return;
  }
  if (!tables.length) {
    const empty = document.createElement("li");
    empty.className = "text-muted small";
    empty.textContent = "No tables in this dataset.";
    schemaList.appendChild(empty);
    return;
  }
  tables.forEach((table) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = table.name;
    button.addEventListener("click", () => showTable(table.name));
    item.appendChild(button);
    if (table.description) {
      const note = document.createElement("span");
      note.textContent = table.description;
      item.appendChild(note);
    }
    schemaList.appendChild(item);
  });
}

function openSchemaModal() {
  if (window.bootstrap && bootstrap.Modal) {
    bootstrap.Modal.getOrCreateInstance(schemaModal).show();
    return;
  }
  schemaModal.classList.add("show");
  schemaModal.style.display = "block";
  schemaModal.removeAttribute("aria-hidden");
}

async function showTable(name) {
  clear(schemaDetail);
  schemaModalTitle.textContent = name;
  schemaModalDesc.textContent = "Loading…";
  openSchemaModal();
  const response = await fetch(
    "/schema/" + encodeURIComponent(name) + "?database=" + encodeURIComponent(database.value)
  );
  if (!response.ok) {
    schemaModalDesc.textContent = "Could not load " + name;
    return;
  }
  const table = await response.json();
  schemaModalTitle.textContent = table.name;
  schemaModalDesc.textContent = table.description || "";
  renderSchemaColumns(table.columns);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  askButton.disabled = true;
  status.textContent = "Asking…";
  try {
    const response = await fetch("/ask", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question: question.value, database: database.value}),
    });
    const data = await response.json();
    selectedId = data.id;
    showAnswer(data);
    status.textContent = "";
    loadHistory();
  } catch (exc) {
    status.textContent = "";
    showAnswer({title: "", error: "The request failed.", assumptions: [], sql: null, columns: [], rows: []});
  } finally {
    askButton.disabled = false;
  }
});

async function loadHistory() {
  clear(historyList);
  const response = await fetch("/history");
  const reports = await response.json();
  if (!reports.length) {
    const empty = document.createElement("li");
    empty.textContent = "No questions yet.";
    historyList.appendChild(empty);
    return;
  }
  reports.forEach((report) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = report.title || report.question;
    if (report.id === selectedId) {
      button.classList.add("is-on");
    }
    button.addEventListener("click", () => openReport(report.id));
    item.appendChild(button);
    historyList.appendChild(item);
  });
}

async function openReport(id) {
  const response = await fetch("/reports/" + encodeURIComponent(id));
  if (!response.ok) {
    status.textContent = "";
    showAnswer({title: "", error: "Could not open that report.", assumptions: [], sql: null, columns: [], rows: []});
    return;
  }
  const report = await response.json();
  selectedId = id;
  question.value = report.question || "";
  showAnswer(report);
  status.textContent = "";
  loadHistory();
}

showChart.addEventListener("click", () => {
  view = "chart";
  paint();
});

showTableButton.addEventListener("click", () => {
  view = "table";
  paint();
});

chartKind.addEventListener("change", () => {
  view = "chart";
  paint();
});

how.addEventListener("click", () => {
  howPanel.hidden = !howPanel.hidden;
});

addFilter.addEventListener("click", () => {
  addCondition((current && current.sourceColumns) || []);
});

exportCsv.addEventListener("click", exportRows);
exportPng.addEventListener("click", exportChartPng);

refetchButton.addEventListener("click", async () => {
  if (!current || !current.id) {
    return;
  }
  const spec = viewSpec();
  if (!spec.columns.length) {
    error.textContent = "Choose at least one field.";
    return;
  }
  refetchButton.disabled = true;
  status.textContent = "Re-fetching…";
  const sourceColumns = current.sourceColumns;
  try {
    const response = await fetch("/reports/" + encodeURIComponent(current.id) + "/view", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(spec),
    });
    const data = await response.json();
    if (!response.ok) {
      error.textContent = typeof data.detail === "string" ? data.detail : "Could not re-fetch.";
      status.textContent = "";
      return;
    }
    data.sourceColumns = sourceColumns;
    showAnswer(data, {keepRefine: true});
    status.textContent = data.total == null ? "" : data.row_count + " of " + data.total;
  } catch (exc) {
    error.textContent = "The request failed.";
    status.textContent = "";
  } finally {
    refetchButton.disabled = false;
  }
});

newQuestion.addEventListener("click", resetQuestion);
database.addEventListener("change", () => {
  loadSchema();
  if (!current) {
    showIdeas();
  }
});

async function loadAppSettings() {
  if (!historyRetentionDays) {
    return;
  }
  const response = await fetch("/settings/app");
  if (!response.ok) {
    return;
  }
  const data = await response.json();
  historyRetentionDays.value = String(data.history_retention_days || 30);
  if (historyRetentionStatus) {
    historyRetentionStatus.textContent = "";
  }
}

if (historyRetentionSave) {
  historyRetentionSave.addEventListener("click", async () => {
    historyRetentionSave.disabled = true;
    if (historyRetentionStatus) {
      historyRetentionStatus.textContent = "Saving…";
    }
    try {
      const response = await fetch("/settings/app", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          history_retention_days: Number(historyRetentionDays.value || 30),
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        if (historyRetentionStatus) {
          historyRetentionStatus.textContent = data.detail || "Save failed.";
        }
        return;
      }
      historyRetentionDays.value = String(data.history_retention_days);
      const purged = data.purged || 0;
      if (historyRetentionStatus) {
        historyRetentionStatus.textContent =
          purged > 0 ? "Saved. Removed " + purged + " old reports." : "Saved.";
      }
      loadHistory();
    } catch (exc) {
      if (historyRetentionStatus) {
        historyRetentionStatus.textContent = "Save failed.";
      }
    } finally {
      historyRetentionSave.disabled = false;
    }
  });
}

settingsModal.addEventListener("show.bs.modal", () => {
  loadUsage();
  loadModels();
  loadSettingsDatasets();
  loadAppSettings();
});

async function boot() {
  await loadDatabases();
  loadSchema();
  loadHistory();
  showIdeas();
}

boot();
