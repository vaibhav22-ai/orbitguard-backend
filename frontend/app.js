const API_BASE = window.location.origin;
const state = { eventType: "flood", incidents: [] };

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const form = $("#eventForm");
const sourceInput = $("#source");
const maskPathInput = $("#maskPath");
const changePercentField = $(".forest-field");
const changePercentInput = $("#changePercent");
const analyzeButton = $("#analyzeButton");
const analyzeButtonText = $("#analyzeButtonText");
const emptyState = $("#emptyState");
const resultContent = $("#resultContent");
const errorState = $("#errorState");

function setStatus(label, online = true) {
  const status = $("#systemStatus");
  status.innerHTML = `<span class="status-dot"></span><span>${label}</span>`;
  const dot = status.querySelector(".status-dot");
  if (!online) {
    dot.style.background = "var(--danger)";
    dot.style.boxShadow = "0 0 12px rgba(255, 142, 120, 0.75)";
  }
}

async function refreshStatus() {
  try {
    const response = await fetch(`${API_BASE}/health`, { cache: "no-store" });
    if (!response.ok) throw new Error("Health check failed");
    const health = await response.json();
    setStatus("API ONLINE", true);
    $("#demoMode").textContent = health.demo_mode ? "DEMO MODE" : "LIVE MODE";
  } catch (error) {
    setStatus("API OFFLINE", false);
  }
}

function setEventType(eventType) {
  state.eventType = eventType;
  const isForest = eventType === "deforestation";
  $$(".segment").forEach((button) => {
    const active = button.dataset.eventType === eventType;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  sourceInput.value = isForest ? "ForestGuard" : "FloodGuard";
  maskPathInput.value = isForest ? "outputs/forest_mask.png" : "outputs/flood_mask.png";
  changePercentField.classList.toggle("is-hidden", !isForest);
  changePercentInput.required = isForest;
  analyzeButtonText.textContent = isForest ? "Run forest analysis" : "Run flood analysis";
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

function listMarkup(items) {
  return (items || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function metricMarkup(label, value, unit = "") {
  return `<div class="metric"><span class="metric-label">${label}</span><span class="metric-value">${escapeHtml(value)}<span class="metric-unit">${unit}</span></span></div>`;
}

function renderIncident(response) {
  const { detection, impact, risk, analysis, location } = response;
  emptyState.classList.add("is-hidden");
  errorState.classList.add("is-hidden");
  resultContent.classList.remove("is-hidden");
  $("#resultId").textContent = response.incident_id;
  $("#riskScore").textContent = risk.score;
  $("#riskLevel").textContent = risk.level;
  $("#riskPill").textContent = risk.level;
  $("#riskRing").style.setProperty("--score", risk.score);
  $("#summary").textContent = analysis.summary;
  $("#metricGrid").innerHTML = [
    metricMarkup("Population exposed", impact.population_exposed.toLocaleString()),
    metricMarkup("Roads affected", impact.roads_affected_km, "km"),
    metricMarkup("Hospitals nearby", impact.hospitals_nearby),
    metricMarkup("Buildings affected", impact.buildings_affected),
  ].join("");
  $("#priorityAreas").innerHTML = listMarkup(analysis.priority_areas);
  $("#recommendedActions").innerHTML = listMarkup(analysis.recommended_actions);
  $("#uncertainty").innerHTML = listMarkup(analysis.uncertainty);
  $("#analysisSource").textContent = `Source: ${analysis.analysis_source}`;
  $("#responseSources").textContent = `Evidence: ${(response.sources || []).join(" / ")}`;
  addIncident(response, location);
}

function addIncident(response, location) {
  state.incidents = [response, ...state.incidents.filter((item) => item.incident_id !== response.incident_id)].slice(0, 5);
  $("#incidentList").innerHTML = state.incidents.map((item) => `
    <div class="incident-row">
      <div class="incident-name"><span class="incident-marker"></span><div><strong>${escapeHtml(item.event_type === "deforestation" ? "Forest change" : "Flood event")}</strong><small>${escapeHtml(item.incident_id)}</small></div></div>
      <span class="incident-risk ${item.risk.level.toLowerCase()}">${escapeHtml(item.risk.level)}</span>
      <span class="incident-detail">${Number(location.latitude).toFixed(3)}, ${Number(location.longitude).toFixed(3)}</span>
      <span class="incident-arrow">&#8599;</span>
    </div>
  `).join("");
}

function showError(message) {
  resultContent.classList.add("is-hidden");
  emptyState.classList.add("is-hidden");
  errorState.classList.remove("is-hidden");
  errorState.textContent = message;
}

function eventPayload() {
  const data = new FormData(form);
  const payload = {
    event_type: state.eventType,
    latitude: Number(data.get("latitude")),
    longitude: Number(data.get("longitude")),
    affected_area_km2: Number(data.get("affected_area_km2")),
    confidence: Number(data.get("confidence")),
    source: data.get("source"),
    acquisition_date: data.get("acquisition_date") || null,
    mask_path: data.get("mask_path") || null,
  };
  if (state.eventType === "deforestation") payload.change_percent = Number(data.get("change_percent"));
  return payload;
}

async function analyze(event) {
  event.preventDefault();
  analyzeButton.disabled = true;
  analyzeButtonText.textContent = "Analyzing signal...";
  errorState.classList.add("is-hidden");
  try {
    const response = await fetch(`${API_BASE}/api/v1/${state.eventType === "flood" ? "flood" : "forest"}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(eventPayload()),
    });
    const body = await response.json();
    if (!response.ok) {
      const detail = Array.isArray(body.detail) ? body.detail.map((item) => item.msg).join("; ") : body.detail;
      throw new Error(detail || "The analysis could not be completed.");
    }
    renderIncident(body);
  } catch (error) {
    showError(`Analysis unavailable: ${error.message}`);
  } finally {
    analyzeButton.disabled = false;
    analyzeButtonText.textContent = state.eventType === "flood" ? "Run flood analysis" : "Run forest analysis";
  }
}

$$('[data-event-type]').forEach((button) => button.addEventListener("click", () => setEventType(button.dataset.eventType)));
form.addEventListener("submit", analyze);
$("#refreshStatus").addEventListener("click", refreshStatus);
refreshStatus();
