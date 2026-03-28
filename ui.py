import json

from config import (
    DCDC_CHARGING_EFFICIENCY,
    DCDC_CHARGING_VOLTAGE,
    DUTY_FRACTION_MAX,
    DUTY_PERCENT_SCALE,
    INVERTER_EFFICIENCY,
    MONTH_DAYS,
    OPENAI_MODEL,
    SOLAR_SYSTEM_EFFICIENCY,
)

def build_page_html():
    """Return one simple HTML page for the local app."""
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Van Energy Budget</title>
  <style>
    :root {
      --bg: #f5efe3;
      --panel: #fffaf2;
      --line: #d9cbb1;
      --text: #2e2418;
      --accent: #1f6f5f;
      --accent-soft: #d8ece6;
      --solar-accent: #f59e0b;
      --error-bg: #fef2f2;
      --error-text: #7f1d1d;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, #fff8ea 0, transparent 35%),
        linear-gradient(180deg, #efe4d0 0%, var(--bg) 100%);
    }

    .page {
      max-width: 1100px;
      margin: 0 auto;
      padding: 32px 20px 60px;
    }

    .hero {
      margin-bottom: 24px;
    }

    h1 {
      margin: 0 0 8px;
      font-size: clamp(2rem, 4vw, 3.5rem);
      line-height: 1;
    }

    p {
      margin: 0;
      font-size: 1rem;
      line-height: 1.5;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 20px;
      box-shadow: 0 16px 40px rgba(46, 36, 24, 0.08);
      margin-top: 24px;
    }

    .form-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 16px;
    }

    label {
      display: block;
      font-weight: 700;
      margin-bottom: 6px;
    }

    input, select, textarea, button {
      width: 100%;
      font: inherit;
      border-radius: 12px;
      border: 1px solid var(--line);
      padding: 12px 14px;
      background: white;
      color: var(--text);
    }

    textarea {
      min-height: 140px;
      resize: vertical;
    }

    button {
      border: none;
      background: var(--accent);
      color: white;
      font-weight: 700;
      cursor: pointer;
    }

    button:hover {
      filter: brightness(1.05);
    }

    .results {
      margin-top: 24px;
      display: none;
    }

    .results.visible {
      display: block;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 16px;
      background: white;
    }

    th, td {
      border: 1px solid var(--line);
      padding: 10px;
      text-align: left;
      vertical-align: top;
    }

    th {
      background: #f2e8d6;
    }

    td[contenteditable="true"] {
      background: #fffdf8;
    }

    .totals {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-top: 18px;
    }

    .total-card {
      background: white;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
    }

    .status {
      margin-top: 12px;
      min-height: 24px;
    }

    .helper-text {
      margin-top: 6px;
      color: #5e5141;
      font-size: 0.95rem;
    }

    .table-actions {
      margin-top: 16px;
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }

    .assumptions-section {
      margin-top: 18px;
      padding: 16px;
      background: #f7f1e5;
      border: 1px solid var(--line);
      border-radius: 14px;
    }

    .assumptions-section h2 {
      margin: 0 0 8px;
      font-size: 1.1rem;
    }

    .assumption-line {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
      line-height: 1.6;
    }

    .inline-input {
      width: 96px;
      min-width: 96px;
      display: inline-block;
      background: white;
    }

    .review-list {
      margin-top: 16px;
      padding-left: 18px;
    }

    .review-list li {
      margin-bottom: 8px;
    }

    .solar-error {
      border: 1px solid rgba(220, 38, 38, 0.25);
      background: var(--error-bg);
      padding: 12px;
      border-radius: 14px;
      color: var(--error-text);
      margin-bottom: 16px;
    }

    .solar-meta {
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      margin-top: 10px;
      font-size: 14px;
      color: #5e5141;
    }

    .chart-wrap {
      height: 420px;
      margin-top: 12px;
      background: white;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 8px;
    }

    canvas {
      width: 100%;
      height: 100%;
      display: block;
    }

    .solar-table-wrap {
      overflow-x: auto;
      margin-top: 16px;
    }

    .solar-table {
      min-width: 980px;
    }

    .solar-table th:first-child,
    .solar-table td:first-child {
      font-weight: 700;
      min-width: 140px;
      background: #f7f1e5;
    }

    .balance-helper {
      margin-top: 4px;
    }

    .balance-chart-wrap {
      height: 360px;
      margin-top: 14px;
      background: white;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 8px;
    }

    .footnotes-panel {
      margin-top: 24px;
      background: rgba(255, 250, 242, 0.75);
      border-style: dashed;
    }

    .footnotes-panel.hidden {
      display: none;
    }

    .footnotes-panel h2 {
      margin: 0 0 10px;
      font-size: 1rem;
    }

    .footnotes-list {
      margin: 0;
      padding-left: 18px;
      color: #4b4032;
      font-size: 0.95rem;
      line-height: 1.6;
    }

    .footnotes-list li + li {
      margin-top: 8px;
    }
  </style>
</head>
<body>
  <div class="page">
    <div class="hero">
      <h1>Van Energy Budget</h1>
      <p>Fill in a few details, generate an energy budget, and tweak the table directly in your browser.</p>
    </div>

    <div class="panel">
      <div class="form-grid">
        <div>
          <label for="location">Location</label>
          <input id="location" type="text" value="Rotorua, New Zealand" placeholder="e.g. Rotorua, New Zealand">
        </div>

        <div>
          <label for="van_size">Van Size</label>
          <select id="van_size">
            <option value="small">small</option>
            <option value="medium" selected>medium</option>
            <option value="large">large</option>
            <option value="XL">XL</option>
          </select>
        </div>

        <div>
          <label for="usage">Usage</label>
          <select id="usage">
            <option value="weekend">weekend</option>
            <option value="weeks">weeks</option>
            <option value="full time">full time</option>
          </select>
        </div>

        <div>
          <label for="adults">Adults</label>
          <input id="adults" type="number" min="0" value="2">
        </div>

        <div>
          <label for="kids">Kids</label>
          <input id="kids" type="number" min="0" value="0">
        </div>
      </div>

      <div>
        <label for="use_case_notes">How will you use the van in real life?</label>
        <p class="helper-text">Describe the kind of trips, how often you travel, whether you stay off-grid or at campgrounds, whether you work from the van, what seasons you use it in, and anything else that affects your energy budget.</p>
        <textarea id="use_case_notes" placeholder="Weekend trips most months, a few longer holidays, usually 2–3 nights off-grid, some winter trips, fridge always on, mostly cook on gas, sometimes stay at campgrounds, charge phones and camera gear, and occasionally work from the van on a laptop.">Weekend trips most months, a few longer holidays, usually 2–3 nights off-grid, some winter trips, fridge always on, mostly cook on gas, sometimes stay at campgrounds, charge phones and camera gear, and occasionally work from the van on a laptop.</textarea>
      </div>

      <div style="margin-top: 16px;">
        <label for="loads_description">What electrical devices will you use?</label>
        <p class="helper-text">List the electrical items you expect to run or charge in the van. These become your energy spending loads in the model. Use normal language and include anything regular or occasional, even if you are unsure of the wattage.</p>
        <textarea id="loads_description" placeholder="12V fridge, diesel heater fan, roof fan, LED lights, 2 phones, laptop, camera battery charger, drone batteries, water pump, electric blanket, induction hob used occasionally.">12V fridge, diesel heater fan, roof fan, LED lights, 2 phones, laptop, camera battery charger, drone batteries, water pump, electric blanket, induction hob used occasionally.</textarea>
      </div>

      <div style="margin-top: 16px;">
        <button id="generate_button" type="button">Generate Energy Budget</button>
      </div>

      <div id="status" class="status"></div>
    </div>

    <div id="results" class="results">
      <div class="panel">
        <h2>Energy Income</h2>
        <div id="solar_error" class="solar-error" style="display:none"></div>
        <div id="solar_results" style="display:none">
          <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline">
            <div>
              <div style="font-weight:900;font-size:18px">Average daily solar irradiance by month</div>
              <div id="solar_name" style="font-size:13px;margin-top:4px;color:#5e5141">—</div>
            </div>
            <div id="solar_source" style="font-size:12px;color:#5e5141">—</div>
          </div>

          <div class="solar-meta">
            <div>Latitude: <span id="solar_lat">—</span></div>
            <div>Longitude: <span id="solar_lon">—</span></div>
          </div>

          <div class="chart-wrap">
            <canvas id="solar_chart" width="1200" height="700"></canvas>
          </div>

          <div class="solar-table-wrap">
            <table class="solar-table">
              <tbody id="solar_tbody"></tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="panel">
        <h2>Energy Spending</h2>
        <div id="table_container"></div>
        <div class="table-actions">
          <button id="recalculate_button" type="button">Recalculate</button>
        </div>

        <div id="totals" class="totals"></div>

        <h2>Things to Review</h2>
        <div id="uncertain_container"></div>

        <div class="assumptions-section">
          <h2>System Assumptions</h2>
          <p class="helper-text">These are editable starting assumptions for the energy budget model.</p>
          <div class="assumption-line">
            <input id="solar_watts" class="inline-input" type="number" min="0" step="10">
            <span>W solar panels</span>
          </div>
          <div class="assumption-line">
            <input id="dcdc_amps" class="inline-input" type="number" min="0" step="5">
            <span>A DC-DC with</span>
            <input id="drive_minutes" class="inline-input" type="number" min="0" step="5">
            <span>min driving per day</span>
          </div>
        </div>

        <div class="assumptions-section">
          <h2>Calculation Assumptions</h2>
          <div class="assumption-line">
            <span>Solar system efficiency: <strong id="solar_efficiency_display"></strong></span>
          </div>
          <div class="assumption-line">
            <span>Inverter efficiency: <strong id="inverter_efficiency_display"></strong></span>
          </div>
          <div class="assumption-line">
            <span>DC-DC charging voltage: <strong id="dcdc_voltage_display"></strong></span>
          </div>
          <div class="assumption-line">
            <span>DC-DC charging efficiency: <strong id="dcdc_efficiency_display"></strong></span>
          </div>
        </div>

        <h2>Monthly Energy Balance</h2>
        <p class="helper-text balance-helper">See how energy spending, energy income, and battery storage are likely to behave through the year, including when the system stays balanced and when it may gradually run flat.</p>
        <div class="balance-chart-wrap">
          <canvas id="balance_chart" width="1200" height="600"></canvas>
        </div>
        <div class="solar-table-wrap">
          <table class="solar-table">
            <tbody id="balance_tbody"></tbody>
          </table>
        </div>

      </div>
    </div>

    <div id="footnotes_panel" class="panel footnotes-panel hidden">
      <h2>How This Energy Budget Works</h2>
      <ul class="footnotes-list">
        <li>This is a decision-support model for understanding off-grid system behaviour over time. It is not a formal electrical design, certification, or sign-off tool.</li>
        <li>The model treats energy spending as your loads and appliance use, energy income as solar generation and DC-DC charging, and the battery as energy storage between the two.</li>
        <li>The first device table is an AI-generated draft built from your plain-language inputs. The AI may estimate device names, wattage, hours of use, duty %, and whether a load is treated as 12V or AC.</li>
        <li>The table should be reviewed and edited before trusting the totals. The results depend heavily on the values in that table because they drive the energy spending side of the model.</li>
        <li>Daily energy spending comes from the device table. For each row, daily Wh is based on quantity × watts × hours × duty %.</li>
        <li>AC loads include inverter losses, using the current inverter efficiency assumption of <strong id="footnote_inverter_efficiency"></strong>.</li>
        <li>The model uses NASA POWER solar irradiance data (kWh/m²/day) for the selected location. In the current model, that irradiance value is used directly as the solar input and then combined with your panel size and the solar system efficiency assumption of <strong id="footnote_solar_efficiency"></strong>.</li>
        <li>Energy income from DC-DC charging is estimated from charger amps, charging voltage, driving time, and charging efficiency. The current charging voltage assumption is <strong id="footnote_dcdc_voltage"></strong> and the current charging efficiency assumption is <strong id="footnote_dcdc_efficiency"></strong>.</li>
        <li>The energy balance compares estimated daily income against estimated daily spending across the year. This helps show when battery storage is likely to stay balanced and when the system may gradually run flat.</li>
        <li id="footnote_ai_model_line">The draft table currently uses the AI model <strong id="footnote_ai_model"></strong>.</li>
      </ul>
    </div>
  </div>

  <script>
    const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const NASA_KEYS = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
    const NASA_SOLAR_IRRADIANCE_PARAMETER = "ALLSKY_SFC_SW_DWN";
    const openAiModel = __OPENAI_MODEL__;
    const generateButton = document.getElementById("generate_button");
    const results = document.getElementById("results");
    const statusBox = document.getElementById("status");
    const vanSizeSelect = document.getElementById("van_size");
    const tableContainer = document.getElementById("table_container");
    const totalsBox = document.getElementById("totals");
    const reviewItemsContainer = document.getElementById("uncertain_container");
    const recalculateButton = document.getElementById("recalculate_button");
    const solarWattsInput = document.getElementById("solar_watts");
    const dcdcAmpsInput = document.getElementById("dcdc_amps");
    const driveMinutesInput = document.getElementById("drive_minutes");
    const solarEfficiencyDisplay = document.getElementById("solar_efficiency_display");
    const inverterEfficiencyDisplay = document.getElementById("inverter_efficiency_display");
    const dcdcVoltageDisplay = document.getElementById("dcdc_voltage_display");
    const dcdcEfficiencyDisplay = document.getElementById("dcdc_efficiency_display");
    const solarErrorBox = document.getElementById("solar_error");
    const solarResults = document.getElementById("solar_results");
    const solarName = document.getElementById("solar_name");
    const solarLat = document.getElementById("solar_lat");
    const solarLon = document.getElementById("solar_lon");
    const solarSource = document.getElementById("solar_source");
    const solarTableBody = document.getElementById("solar_tbody");
    const balanceTableBody = document.getElementById("balance_tbody");
    const footnoteSolarEfficiency = document.getElementById("footnote_solar_efficiency");
    const footnoteInverterEfficiency = document.getElementById("footnote_inverter_efficiency");
    const footnoteDcdcVoltage = document.getElementById("footnote_dcdc_voltage");
    const footnoteDcdcEfficiency = document.getElementById("footnote_dcdc_efficiency");
    const footnoteAiModel = document.getElementById("footnote_ai_model");
    const footnoteAiModelLine = document.getElementById("footnote_ai_model_line");
    const footnotesPanel = document.getElementById("footnotes_panel");
    const solarCanvas = document.getElementById("solar_chart");
    const solarCtx = solarCanvas.getContext("2d");
    const balanceCanvas = document.getElementById("balance_chart");
    const balanceCtx = balanceCanvas.getContext("2d");
    const inverterEfficiency = __INVERTER_EFFICIENCY__;
    const solarSystemEfficiency = __SOLAR_SYSTEM_EFFICIENCY__;
    const dcdcChargingVoltage = __DCDC_CHARGING_VOLTAGE__;
    const dcdcChargingEfficiency = __DCDC_CHARGING_EFFICIENCY__;
    const monthDays = __MONTH_DAYS__;
    const dutyFractionMax = __DUTY_FRACTION_MAX__;
    const dutyPercentScale = __DUTY_PERCENT_SCALE__;
    const dcVoltageAliases = new Set(["12v", "12 v", "dc", "12 volt", "12 volts"]);
    const acVoltageAliases = new Set(["ac", "230v", "230 v", "240v", "240 v", "120v", "120 v", "mains"]);
    const assumptionDefaults = {
      small: { solarWatts: 200, dcdcAmps: 30, driveMinutes: 60 },
      medium: { solarWatts: 400, dcdcAmps: 30, driveMinutes: 60 },
      large: { solarWatts: 600, dcdcAmps: 50, driveMinutes: 60 },
      xl: { solarWatts: 1000, dcdcAmps: 100, driveMinutes: 60 }
    };
    let currentSolarRows = [];
    let currentAuditTotals = null;
    let generateTimerId = null;

    function formatPercentage(value) {
      return `${round(value * 100, 0)}%`;
    }

    function getVanSizeDefaults(vanSize) {
      return assumptionDefaults[String(vanSize || "").trim().toLowerCase()] || assumptionDefaults.medium;
    }

    function applyAssumptionDefaults() {
      const defaults = getVanSizeDefaults(vanSizeSelect.value);
      solarWattsInput.value = defaults.solarWatts;
      dcdcAmpsInput.value = defaults.dcdcAmps;
      driveMinutesInput.value = defaults.driveMinutes;
      updateMonthlyBalanceChart();
    }

    function formatElapsedSeconds(startTime) {
      return ((performance.now() - startTime) / 1000).toFixed(1);
    }

    function clearGenerateTimer() {
      if (generateTimerId !== null) {
        clearInterval(generateTimerId);
        generateTimerId = null;
      }
    }

    function startGenerateTimer(startTime) {
      clearGenerateTimer();
      statusBox.textContent = `Generating energy budget... ${formatElapsedSeconds(startTime)}s`;
      generateTimerId = window.setInterval(() => {
        statusBox.textContent = `Generating energy budget... ${formatElapsedSeconds(startTime)}s`;
      }, 100);
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }

    function renderTable(rows) {
      const header = `
        <tr>
          <th>device</th>
          <th>qty</th>
          <th>voltage</th>
          <th>watts</th>
          <th>hours</th>
          <th>duty (%)</th>
          <th>daily_wh</th>
          <th>source_text</th>
          <th>assumption_note</th>
        </tr>
      `;

      const body = rows.map((row) => `
        <tr data-source-text="${escapeHtml(row.source_text || "")}">
          <td contenteditable="true">${escapeHtml(row.name)}</td>
          <td contenteditable="true">${escapeHtml(row.quantity)}</td>
          <td contenteditable="true">${escapeHtml(row.voltage)}</td>
          <td contenteditable="true">${escapeHtml(row.watts)}</td>
          <td contenteditable="true">${escapeHtml(row.hours)}</td>
          <td contenteditable="true">${escapeHtml(row.duty)}</td>
          <td contenteditable="true">${escapeHtml(row.daily_wh)}</td>
          <td contenteditable="true">${escapeHtml(row.source_text || "")}</td>
          <td contenteditable="true">${escapeHtml(row.assumption_note || "")}</td>
        </tr>
      `).join("");

      tableContainer.innerHTML = `<table>${header}${body}</table>`;
    }

    function renderReviewItems(reviewItems) {
      if (!reviewItems || reviewItems.length === 0) {
        reviewItemsContainer.innerHTML = "<p>No review items right now.</p>";
        return;
      }

      const html = reviewItems.map((item) => `
        <li><strong>${escapeHtml(item.type || "review")}</strong>: <strong>${escapeHtml(item.text)}</strong> - ${escapeHtml(item.note)}</li>
      `).join("");

      reviewItemsContainer.innerHTML = `<ul class="review-list">${html}</ul>`;
    }

    function round(value, decimals = 2) {
      return Number.isFinite(+value)
        ? Math.round(+value * Math.pow(10, decimals)) / Math.pow(10, decimals)
        : null;
    }

    function clearSolarError() {
      solarErrorBox.style.display = "none";
      solarErrorBox.textContent = "";
    }

    function showSolarError(message) {
      solarErrorBox.style.display = "block";
      solarErrorBox.textContent = message;
    }

    async function geocode(query) {
      const url =
        "https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q=" +
        encodeURIComponent(query);

      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) {
        throw new Error("Location lookup failed.");
      }

      const data = await response.json();
      if (!Array.isArray(data) || !data.length) {
        throw new Error("No matching location found.");
      }

      return data[0];
    }

    async function fetchNasaSolar(lat, lon) {
      const url = [
        "https://power.larc.nasa.gov/api/temporal/climatology/point",
        "?parameters=" + NASA_SOLAR_IRRADIANCE_PARAMETER,
        "&community=RE",
        "&format=JSON",
        "&latitude=" + encodeURIComponent(lat),
        "&longitude=" + encodeURIComponent(lon),
      ].join("");

      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) {
        throw new Error("Solar data request failed.");
      }

      const data = await response.json();
      const param = data?.properties?.parameter?.[NASA_SOLAR_IRRADIANCE_PARAMETER];
      if (!param) {
        throw new Error("Solar data returned in an unexpected format.");
      }

      return { data, param };
    }

    function normalizeSolarIrradianceKwhM2Day(rawValue) {
      // The monthly model currently uses NASA POWER ALLSKY_SFC_SW_DWN irradiance
      // values directly as its solar input, preserving the existing app behaviour.
      const value = Number(rawValue);
      return Number.isFinite(value) ? round(value, 2) : null;
    }

    function buildSolarRows(param) {
      return NASA_KEYS.map((key, index) => {
        return {
          month: MONTHS[index],
          solarIrradianceKwhM2Day: normalizeSolarIrradianceKwhM2Day(param[key])
        };
      });
    }

    function renderSolarTable(rows) {
      const monthCells = rows.map((row) => `<th>${row.month}</th>`).join("");
      const valueCells = rows.map((row) => `<td>${row.solarIrradianceKwhM2Day ?? "—"}</td>`).join("");

      solarTableBody.innerHTML = `
        <tr>
          <th>Month</th>
          ${monthCells}
        </tr>
        <tr>
          <td>kWh/m²/day</td>
          ${valueCells}
        </tr>
      `;
    }

    function drawSolarChart(rows, displayLocation) {
      const width = solarCanvas.width;
      const height = solarCanvas.height;

      solarCtx.clearRect(0, 0, width, height);
      solarCtx.fillStyle = "#fff";
      solarCtx.fillRect(0, 0, width, height);

      solarCtx.fillStyle = "#0f172a";
      solarCtx.font = "bold 22px system-ui";
      solarCtx.textAlign = "left";
      solarCtx.textBaseline = "top";
      solarCtx.fillText("Average Daily Solar Irradiance", 24, 20);

      solarCtx.fillStyle = "#475569";
      solarCtx.font = "14px system-ui";
      solarCtx.fillText(displayLocation, 24, 50);

      const pad = { l: 90, r: 26, t: 85, b: 90 };
      const plotWidth = width - pad.l - pad.r;
      const plotHeight = height - pad.t - pad.b;
      const values = rows.map((row) => (
        typeof row.solarIrradianceKwhM2Day === "number" ? row.solarIrradianceKwhM2Day : 0
      ));
      const maxValue = Math.max(1, ...values);
      const yMax = Math.max(1, Math.ceil(maxValue * 1.1));

      solarCtx.strokeStyle = "#e2e8f0";
      solarCtx.lineWidth = 1;
      solarCtx.fillStyle = "#64748b";
      solarCtx.font = "14px system-ui";

      for (let i = 0; i <= 5; i += 1) {
        const t = i / 5;
        const y = pad.t + plotHeight - (t * plotHeight);

        solarCtx.beginPath();
        solarCtx.moveTo(pad.l, y);
        solarCtx.lineTo(pad.l + plotWidth, y);
        solarCtx.stroke();

        solarCtx.textAlign = "right";
        solarCtx.textBaseline = "middle";
        solarCtx.fillText(round(t * yMax, 1) + " kWh/m²/day", pad.l - 10, y);
      }

      solarCtx.strokeStyle = "#cbd5e1";
      solarCtx.lineWidth = 2;
      solarCtx.beginPath();
      solarCtx.moveTo(pad.l, pad.t);
      solarCtx.lineTo(pad.l, pad.t + plotHeight);
      solarCtx.lineTo(pad.l + plotWidth, pad.t + plotHeight);
      solarCtx.stroke();

      const gap = 10;
      const barWidth = (plotWidth - gap * (rows.length - 1)) / rows.length;

      function getSolarBarColor(value) {
        if (value <= 0) {
          return "#0f172a";
        }
        if (value <= 1.5) {
          return "#64748b";
        }
        if (value <= 2.5) {
          return "#3b82f6";
        }
        if (value <= 4.0) {
          return "#22c55e";
        }
        if (value <= 5.5) {
          return "#f59e0b";
        }
        return "#dc2626";
      }

      for (let i = 0; i < rows.length; i += 1) {
        const value = typeof rows[i].solarIrradianceKwhM2Day === "number"
          ? rows[i].solarIrradianceKwhM2Day
          : 0;
        const barHeight = (value / yMax) * plotHeight;
        const x = pad.l + i * (barWidth + gap);
        const y = pad.t + plotHeight - barHeight;
        const radius = Math.min(10, barWidth / 2, barHeight / 2);

        solarCtx.fillStyle = getSolarBarColor(value);
        solarCtx.beginPath();
        solarCtx.moveTo(x + radius, y);
        solarCtx.arcTo(x + barWidth, y, x + barWidth, y + barHeight, radius);
        solarCtx.arcTo(x + barWidth, y + barHeight, x, y + barHeight, radius);
        solarCtx.arcTo(x, y + barHeight, x, y, radius);
        solarCtx.arcTo(x, y, x + barWidth, y, radius);
        solarCtx.closePath();
        solarCtx.fill();

        solarCtx.fillStyle = "#0f172a";
        solarCtx.font = "14px system-ui";
        solarCtx.textAlign = "center";
        solarCtx.textBaseline = "top";
        solarCtx.fillText(rows[i].month, x + barWidth / 2, pad.t + plotHeight + 12);

        solarCtx.fillStyle = "#334155";
        solarCtx.font = "12px system-ui";
        solarCtx.textBaseline = "bottom";
        solarCtx.fillText(value ? String(value) : "0", x + barWidth / 2, y - 6);
      }
    }

    async function loadSolarData(locationValue) {
      clearSolarError();
      solarResults.style.display = "none";

      const place = await geocode(locationValue);
      const lat = +place.lat;
      const lon = +place.lon;
      const { data, param } = await fetchNasaSolar(lat, lon);
      const rows = buildSolarRows(param);
      const displayName = place.display_name || locationValue;
      currentSolarRows = rows;

      solarName.textContent = displayName;
      solarLat.textContent = round(lat, 4);
      solarLon.textContent = round(lon, 4);
      solarSource.textContent = data?.properties?.sources?.length
        ? ("Source: " + data.properties.sources.join(", "))
        : "Source: NASA POWER";

      renderSolarTable(rows);
      drawSolarChart(rows, displayName);
      updateMonthlyBalanceChart();
      solarResults.style.display = "block";
    }

    function toNumber(value, fallback = 0) {
      const number = Number(value);
      if (Number.isFinite(number)) {
        return number;
      }
      return fallback;
    }

    function calculateDailyWh(quantity, watts, hours, dutyPercentage) {
      return quantity * watts * hours * (dutyPercentage / 100);
    }

    function calculateDcdcDailyWh(dcdcAmps, driveMinutesPerDay) {
      return (
        dcdcAmps
        * dcdcChargingVoltage
        * (driveMinutesPerDay / 60)
        * dcdcChargingEfficiency
      );
    }

    function calculateSolarDailyWh(solarWatts, solarIrradianceKwhM2Day) {
      return solarWatts * solarIrradianceKwhM2Day * solarSystemEfficiency;
    }

    function calculateTotalChargeDailyWh(solarDailyWh, dcdcDailyWh) {
      return solarDailyWh + dcdcDailyWh;
    }

    function calculateDailyBalanceWh(totalChargeDailyWh, overallDailyLoad) {
      return totalChargeDailyWh - overallDailyLoad;
    }

    function calculateMonthlyBalanceWh(dailyBalanceWh, daysInMonth) {
      return dailyBalanceWh * daysInMonth;
    }

    function normalizeDutyPercentage(rawValue) {
      let dutyValue = toNumber(rawValue, dutyPercentScale);

      if (dutyValue <= dutyFractionMax) {
        dutyValue *= dutyPercentScale;
      }

      return Math.max(dutyValue, 0);
    }

    function normalizeVoltageCategory(rawValue) {
      const voltageValue = String(rawValue || "").trim().toLowerCase();

      if (dcVoltageAliases.has(voltageValue)) {
        return "12v";
      }

      if (acVoltageAliases.has(voltageValue)) {
        return "ac";
      }

      return voltageValue;
    }

    function readRowsFromTable() {
      const rows = [];
      const tableRows = tableContainer.querySelectorAll("table tr");

      for (let index = 1; index < tableRows.length; index += 1) {
        const cells = tableRows[index].querySelectorAll("td");
        if (cells.length !== 9) {
          continue;
        }

        rows.push({
          name: cells[0].textContent.trim(),
          quantity: toNumber(cells[1].textContent.trim(), 1),
          voltage: normalizeVoltageCategory(cells[2].textContent.trim()),
          watts: toNumber(cells[3].textContent.trim()),
          hours: toNumber(cells[4].textContent.trim()),
          duty: normalizeDutyPercentage(cells[5].textContent.trim()),
          daily_wh: toNumber(cells[6].textContent.trim()),
          source_text: cells[7].textContent.trim(),
          assumption_note: cells[8].textContent.trim()
        });
      }

      return rows;
    }

    function recalculateRows(rows) {
      let dcTotal = 0;
      let acTotal = 0;

      const updatedRows = rows.map((row) => {
        const dailyWh = calculateDailyWh(row.quantity, row.watts, row.hours, row.duty);

        if (row.voltage === "12v") {
          dcTotal += dailyWh;
        } else if (row.voltage === "ac") {
          acTotal += dailyWh / inverterEfficiency;
        }

        return {
          ...row,
          daily_wh: Number(dailyWh.toFixed(2))
        };
      });

      updatedRows.sort((left, right) => right.daily_wh - left.daily_wh);

      return {
        rows: updatedRows,
        totals: {
          dc_total: Number(dcTotal.toFixed(2)),
          ac_total: Number(acTotal.toFixed(2)),
          overall_total: Number((dcTotal + acTotal).toFixed(2))
        }
      };
    }

    function renderTotals(totals) {
      totalsBox.innerHTML = `
        <div class="total-card"><strong>12V Energy Spending</strong><div>${totals.dc_total} Wh/day</div></div>
        <div class="total-card"><strong>AC Energy Spending</strong><div>${totals.ac_total} Wh/day</div></div>
        <div class="total-card"><strong>Total Energy Spending</strong><div>${totals.overall_total} Wh/day</div></div>
      `;
    }

    function getSystemAssumptions() {
      return {
        solarWatts: Math.max(0, toNumber(solarWattsInput.value)),
        dcdcAmps: Math.max(0, toNumber(dcdcAmpsInput.value)),
        driveMinutesPerDay: Math.max(0, toNumber(driveMinutesInput.value))
      };
    }

    function buildMonthlyEnergyData(monthlySolarRows, totals, assumptions) {
      if (!monthlySolarRows || monthlySolarRows.length !== 12 || !totals) {
        return MONTHS.map((month) => ({
          month,
          powerUseDailyWh: 0,
          solarGeneratedDailyWh: 0,
          dcdcContributionDailyWh: 0,
          totalChargeDailyWh: 0,
          dailyBalanceWh: 0,
          monthlyBalanceWh: 0
        }));
      }

      const overallDailyLoad = Math.max(0, toNumber(totals.overall_total));
      const dcdcDailyWh = calculateDcdcDailyWh(
        assumptions.dcdcAmps,
        assumptions.driveMinutesPerDay
      );

      return monthlySolarRows.map((row, index) => {
        const solarIrradianceKwhM2Day = Math.max(0, toNumber(row.solarIrradianceKwhM2Day));
        const solarDailyWh = calculateSolarDailyWh(
          assumptions.solarWatts,
          solarIrradianceKwhM2Day
        );
        const totalChargeDailyWh = calculateTotalChargeDailyWh(solarDailyWh, dcdcDailyWh);
        const dailyBalanceWh = calculateDailyBalanceWh(totalChargeDailyWh, overallDailyLoad);
        const monthlyBalanceWh = calculateMonthlyBalanceWh(dailyBalanceWh, monthDays[index]);

        return {
          month: row.month || MONTHS[index],
          powerUseDailyWh: round(overallDailyLoad, 2),
          solarGeneratedDailyWh: round(solarDailyWh, 2),
          dcdcContributionDailyWh: round(dcdcDailyWh, 2),
          totalChargeDailyWh: round(totalChargeDailyWh, 2),
          dailyBalanceWh: round(dailyBalanceWh, 2),
          monthlyBalanceWh: round(monthlyBalanceWh, 2)
        };
      });
    }

    function drawMonthlyBalanceChart(monthlyData) {
      const width = balanceCanvas.width;
      const height = balanceCanvas.height;
      const values = monthlyData.map((row) => toNumber(row.dailyBalanceWh));
      const maxMagnitude = Math.max(1, ...values.map((value) => Math.abs(value)));
      const pad = { l: 90, r: 28, t: 38, b: 90 };
      const plotWidth = width - pad.l - pad.r;
      const plotHeight = height - pad.t - pad.b;
      const centerY = pad.t + plotHeight / 2;
      const gap = 10;
      const barWidth = (plotWidth - gap * (monthlyData.length - 1)) / monthlyData.length;

      balanceCtx.clearRect(0, 0, width, height);
      balanceCtx.fillStyle = "#fff";
      balanceCtx.fillRect(0, 0, width, height);

      balanceCtx.fillStyle = "#0f172a";
      balanceCtx.font = "bold 22px system-ui";
      balanceCtx.textAlign = "left";
      balanceCtx.textBaseline = "top";
      balanceCtx.fillText("Daily Surplus / Shortfall", 24, 18);

      balanceCtx.strokeStyle = "#cbd5e1";
      balanceCtx.lineWidth = 2;
      balanceCtx.beginPath();
      balanceCtx.moveTo(pad.l, centerY);
      balanceCtx.lineTo(pad.l + plotWidth, centerY);
      balanceCtx.stroke();

      balanceCtx.fillStyle = "#475569";
      balanceCtx.font = "13px system-ui";
      balanceCtx.textAlign = "right";
      balanceCtx.textBaseline = "middle";
      balanceCtx.fillText("0", pad.l - 12, centerY);

      for (let i = 0; i < 4; i += 1) {
        const ratio = (i + 1) / 4;
        const upperY = centerY - plotHeight * 0.5 * ratio;
        const lowerY = centerY + plotHeight * 0.5 * ratio;
        const labelValue = round(maxMagnitude * ratio, 0);

        balanceCtx.strokeStyle = "#e2e8f0";
        balanceCtx.lineWidth = 1;
        balanceCtx.beginPath();
        balanceCtx.moveTo(pad.l, upperY);
        balanceCtx.lineTo(pad.l + plotWidth, upperY);
        balanceCtx.moveTo(pad.l, lowerY);
        balanceCtx.lineTo(pad.l + plotWidth, lowerY);
        balanceCtx.stroke();

        balanceCtx.fillStyle = "#64748b";
        balanceCtx.fillText(String(labelValue), pad.l - 12, upperY);
        balanceCtx.fillText(String(-labelValue), pad.l - 12, lowerY);
      }

      for (let i = 0; i < monthlyData.length; i += 1) {
        const value = toNumber(monthlyData[i].dailyBalanceWh);
        const scaledHeight = (Math.abs(value) / maxMagnitude) * (plotHeight / 2 - 18);
        const x = pad.l + i * (barWidth + gap);
        const y = value >= 0 ? centerY - scaledHeight : centerY;
        const radius = Math.min(10, barWidth / 2, scaledHeight / 2 || 0);

        balanceCtx.fillStyle = value >= 0 ? "#22c55e" : "#dc2626";
        balanceCtx.beginPath();
        balanceCtx.moveTo(x + radius, y);
        balanceCtx.arcTo(x + barWidth, y, x + barWidth, y + scaledHeight, radius);
        balanceCtx.arcTo(x + barWidth, y + scaledHeight, x, y + scaledHeight, radius);
        balanceCtx.arcTo(x, y + scaledHeight, x, y, radius);
        balanceCtx.arcTo(x, y, x + barWidth, y, radius);
        balanceCtx.closePath();
        balanceCtx.fill();

        balanceCtx.fillStyle = "#0f172a";
        balanceCtx.font = "14px system-ui";
        balanceCtx.textAlign = "center";
        balanceCtx.textBaseline = "top";
        balanceCtx.fillText(monthlyData[i].month, x + barWidth / 2, pad.t + plotHeight + 12);

        balanceCtx.fillStyle = value >= 0 ? "#166534" : "#991b1b";
        balanceCtx.font = "12px system-ui";
        balanceCtx.textBaseline = value >= 0 ? "bottom" : "top";
        balanceCtx.fillText(
          String(round(value, 0)),
          x + barWidth / 2,
          value >= 0 ? y - 6 : y + scaledHeight + 6
        );
      }
    }

    function renderMonthlyCalculationTable(monthlyData) {
      const monthCells = monthlyData.map((row) => `<th>${row.month}</th>`).join("");

      function renderValueRow(label, key) {
        const valueCells = monthlyData.map((row) => `<td>${round(row[key], 0)}</td>`).join("");
        return `
          <tr>
            <td>${label}</td>
            ${valueCells}
          </tr>
        `;
      }

      balanceTableBody.innerHTML = `
        <tr>
          <th>Metric</th>
          ${monthCells}
        </tr>
        ${renderValueRow("Energy spending (avg daily Wh)", "powerUseDailyWh")}
        ${renderValueRow("Energy income: solar generation (avg daily Wh)", "solarGeneratedDailyWh")}
        ${renderValueRow("Energy income: DC-DC charging (avg daily Wh)", "dcdcContributionDailyWh")}
        ${renderValueRow("Total energy income (avg daily Wh)", "totalChargeDailyWh")}
        ${renderValueRow("Daily surplus / shortfall (Wh)", "dailyBalanceWh")}
      `;
    }

    function updateMonthlyBalanceChart() {
      const monthlyData = buildMonthlyEnergyData(
        currentSolarRows,
        currentAuditTotals,
        getSystemAssumptions()
      );
      drawMonthlyBalanceChart(monthlyData);
      renderMonthlyCalculationTable(monthlyData);
    }

    async function generateAudit() {
      const startTime = performance.now();
      footnotesPanel.classList.remove("hidden");
      startGenerateTimer(startTime);

      const payload = {
        location: document.getElementById("location").value,
        van_size: document.getElementById("van_size").value,
        usage: document.getElementById("usage").value,
        adults: Number(document.getElementById("adults").value || 0),
        kids: Number(document.getElementById("kids").value || 0),
        use_case_notes: document.getElementById("use_case_notes").value,
        loads_description: document.getElementById("loads_description").value
      };

      const solarPromise = loadSolarData(payload.location).catch((error) => {
        showSolarError(error?.message || "Solar data lookup failed.");
      });

      const response = await fetch("/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      await solarPromise;

      if (!response.ok) {
        clearGenerateTimer();
        const errorResult = await response.json();
        statusBox.textContent = errorResult.error
          ? `Energy budget generation failed after ${formatElapsedSeconds(startTime)}s: ${errorResult.error}`
          : `Energy budget generation failed after ${formatElapsedSeconds(startTime)}s`;
        return;
      }

      clearGenerateTimer();
      const result = await response.json();
      currentAuditTotals = result.totals;
      results.classList.add("visible");
      renderTable(result.rows);
      renderTotals(result.totals);
      renderReviewItems(result.review_items);
      updateMonthlyBalanceChart();
      statusBox.textContent = `Energy budget generated in ${formatElapsedSeconds(startTime)}s`;
    }

    generateButton.addEventListener("click", generateAudit);
    vanSizeSelect.addEventListener("change", applyAssumptionDefaults);
    solarWattsInput.addEventListener("input", updateMonthlyBalanceChart);
    dcdcAmpsInput.addEventListener("input", updateMonthlyBalanceChart);
    driveMinutesInput.addEventListener("input", updateMonthlyBalanceChart);

    recalculateButton.addEventListener("click", () => {
      const rows = readRowsFromTable();
      const recalculated = recalculateRows(rows);
      currentAuditTotals = recalculated.totals;
      renderTable(recalculated.rows);
      renderTotals(recalculated.totals);
      updateMonthlyBalanceChart();
      statusBox.textContent = "Energy budget totals recalculated from the edited table.";
    });

    applyAssumptionDefaults();
    solarEfficiencyDisplay.textContent = formatPercentage(solarSystemEfficiency);
    inverterEfficiencyDisplay.textContent = formatPercentage(inverterEfficiency);
    dcdcVoltageDisplay.textContent = `${round(dcdcChargingVoltage, 1)} V`;
    dcdcEfficiencyDisplay.textContent = formatPercentage(dcdcChargingEfficiency);
    footnoteSolarEfficiency.textContent = formatPercentage(solarSystemEfficiency);
    footnoteInverterEfficiency.textContent = formatPercentage(inverterEfficiency);
    footnoteDcdcVoltage.textContent = `${round(dcdcChargingVoltage, 1)} V`;
    footnoteDcdcEfficiency.textContent = formatPercentage(dcdcChargingEfficiency);
    if (openAiModel) {
      footnoteAiModel.textContent = openAiModel;
    } else {
      footnoteAiModelLine.style.display = "none";
    }
    const emptyMonthlyData = buildMonthlyEnergyData([], null, getSystemAssumptions());
    drawMonthlyBalanceChart(emptyMonthlyData);
    renderMonthlyCalculationTable(emptyMonthlyData);
    drawSolarChart(
      MONTHS.map((month) => ({ month, solarIrradianceKwhM2Day: 0 })),
      "Selected location"
    );
  </script>
</body>
</html>
""".replace("__INVERTER_EFFICIENCY__", json.dumps(INVERTER_EFFICIENCY)).replace(
        "__SOLAR_SYSTEM_EFFICIENCY__", json.dumps(SOLAR_SYSTEM_EFFICIENCY)
    ).replace(
        "__DCDC_CHARGING_VOLTAGE__", json.dumps(DCDC_CHARGING_VOLTAGE)
    ).replace(
        "__DCDC_CHARGING_EFFICIENCY__", json.dumps(DCDC_CHARGING_EFFICIENCY)
    ).replace(
        "__MONTH_DAYS__", json.dumps(MONTH_DAYS)
    ).replace(
        "__DUTY_FRACTION_MAX__", json.dumps(DUTY_FRACTION_MAX)
    ).replace(
        "__DUTY_PERCENT_SCALE__", json.dumps(DUTY_PERCENT_SCALE)
    ).replace(
        "__OPENAI_MODEL__", json.dumps(OPENAI_MODEL)
    )
