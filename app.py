import csv
import json
import os
import traceback

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse
except ImportError:
    FastAPI = None
    Request = None
    HTMLResponse = None
    JSONResponse = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# A single library of known devices. Each device has:
# - watts: power draw
# - hours: daily runtime
# - duty: how often it is actually running during those hours
# - voltage: either "12v" or "ac"
# - category: a simple label to group similar devices
DEVICE_LIBRARY = {
    "fridge": {"watts": 45, "hours": 24, "duty": 0.4, "voltage": "12v", "category": "cooling"},
    "laptop": {"watts": 60, "hours": 2, "duty": 1.0, "voltage": "ac", "category": "charging"},
    "fan": {"watts": 20, "hours": 5, "duty": 0.7, "voltage": "12v", "category": "ventilation"},
    "lights": {"watts": 10, "hours": 5, "duty": 1.0, "voltage": "12v", "category": "lighting"},
    "bluetooth speaker charging": {"watts": 15, "hours": 2, "duty": 1.0, "voltage": "ac", "category": "charging"},
    "drone charging": {"watts": 80, "hours": 1.5, "duty": 1.0, "voltage": "ac", "category": "charging"},
    "phone charger": {"watts": 20, "hours": 2, "duty": 1.0, "voltage": "ac", "category": "charging"},
    "tablet charging": {"watts": 20, "hours": 3, "duty": 1.0, "voltage": "ac", "category": "charging"},
    "diesel heater": {"watts": 40, "hours": 8, "duty": 0.5, "voltage": "12v", "category": "ventilation"},
    "water pump": {"watts": 60, "hours": 0.5, "duty": 0.3, "voltage": "12v", "category": "water"},
    "maxxair fan": {"watts": 30, "hours": 8, "duty": 0.8, "voltage": "12v", "category": "ventilation"},
    "compressor fridge": {"watts": 50, "hours": 24, "duty": 0.35, "voltage": "12v", "category": "cooling"},
    "laptop charger": {"watts": 90, "hours": 2, "duty": 1.0, "voltage": "ac", "category": "charging"},
    "camera battery charger": {"watts": 25, "hours": 2, "duty": 1.0, "voltage": "ac", "category": "charging"},
    "starlink": {"watts": 60, "hours": 6, "duty": 1.0, "voltage": "ac", "category": "internet"},
    "tv": {"watts": 60, "hours": 3, "duty": 1.0, "voltage": "ac", "category": "entertainment"},
    "coffee machine": {"watts": 1200, "hours": 0.2, "duty": 1.0, "voltage": "ac", "category": "cooking"},
    "induction cooktop": {"watts": 1800, "hours": 0.5, "duty": 1.0, "voltage": "ac", "category": "cooking"},
    "microwave": {"watts": 1000, "hours": 0.25, "duty": 1.0, "voltage": "ac", "category": "cooking"},
}

INVERTER_EFFICIENCY = 0.9
CSV_FILE = "power_audit.csv"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_FALLBACK_MODEL = "gpt-4.1-mini"


def build_ai_prompt(user_profile):
    """Turn the user profile into a clear prompt string for a future AI step."""
    return (
        "Create a campervan/off-grid power audit.\n"
        f"Van size: {user_profile['van_size']}\n"
        f"Usage: {user_profile['usage']}\n"
        f"Adults: {user_profile['adults']}\n"
        f"Kids: {user_profile['kids']}\n"
        f"Loads description: {user_profile['loads_description']}\n"
        "Return a practical list of daily electrical loads with quantity, category, "
        "voltage type, watts, hours per day, duty cycle, source text, confidence, "
        "and assumption notes as valid JSON only."
    )


class OpenAIExtractionError(RuntimeError):
    """Error raised when the OpenAI extraction path fails."""

    def __init__(self, message, raw_response_text=""):
        super().__init__(message)
        self.raw_response_text = raw_response_text or ""


def get_audit_schema():
    """Return the JSON schema used for the OpenAI structured response."""
    return {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "category": {"type": "string"},
                        "quantity": {"type": "number"},
                        "include": {"type": "boolean"},
                        "voltage": {"type": "string"},
                        "watts": {"type": "number"},
                        "hours": {"type": "number"},
                        "duty": {"type": "number"},
                        "daily_wh": {"type": "number"},
                        "source_text": {"type": "string"},
                        "confidence": {"type": "number"},
                        "assumption_note": {"type": "string"},
                    },
                    "required": [
                        "name",
                        "category",
                        "quantity",
                        "include",
                        "voltage",
                        "watts",
                        "hours",
                        "duty",
                        "daily_wh",
                        "source_text",
                        "confidence",
                        "assumption_note",
                    ],
                    "additionalProperties": False,
                },
            },
            "context_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "note": {"type": "string"},
                    },
                    "required": ["text", "note"],
                    "additionalProperties": False,
                },
            },
            "uncertain_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "note": {"type": "string"},
                    },
                    "required": ["text", "note"],
                    "additionalProperties": False,
                },
            },
            "excluded_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["text", "reason"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["rows", "context_items", "uncertain_items", "excluded_items"],
        "additionalProperties": False,
    }


def extract_response_text(response):
    """Read plain text from a Responses API result with fallback paths."""
    output_text = getattr(response, "output_text", "") or ""
    if output_text:
        return output_text.strip()

    output_items = getattr(response, "output", []) or []
    for item in output_items:
        content_items = getattr(item, "content", []) or []
        for content_item in content_items:
            text = getattr(content_item, "text", "") or ""
            if text:
                return text.strip()

        item_text = getattr(item, "text", "") or ""
        if item_text:
            return item_text.strip()

    return ""


def serialize_response_debug(response):
    """Serialize the response for terminal logging and UI error visibility."""
    if response is None:
        return ""

    try:
        return response.model_dump_json(indent=2)
    except Exception:
        return str(response)


def normalize_ai_result(ai_result):
    """Normalize the structured result so the existing table and totals flow stays stable."""
    normalized_rows = []

    for row in ai_result.get("rows", []):
        voltage_value = str(row.get("voltage", "")).strip().lower()
        if voltage_value in {"12v", "12 v", "dc", "12 volt", "12 volts"}:
            normalized_voltage = "12v"
        elif voltage_value in {"ac", "230v", "230 v", "240v", "240 v", "120v", "120 v", "mains"}:
            normalized_voltage = "ac"
        else:
            normalized_voltage = voltage_value

        normalized_row = {
            "name": str(row.get("name", "")).strip(),
            "category": str(row.get("category", "")).strip(),
            "quantity": float(row.get("quantity", 1)),
            "include": bool(row.get("include", True)),
            "voltage": normalized_voltage,
            "watts": float(row.get("watts", 0)),
            "hours": float(row.get("hours", 0)),
            "duty": float(row.get("duty", 1)),
            "daily_wh": float(row.get("daily_wh", 0)),
            "source_text": str(row.get("source_text", "")).strip(),
            "confidence": float(row.get("confidence", 0)),
            "assumption_note": str(row.get("assumption_note", "")).strip(),
        }

        recalculated_daily_wh = (
            normalized_row["quantity"]
            * normalized_row["watts"]
            * normalized_row["hours"]
            * normalized_row["duty"]
        )
        normalized_row["daily_wh"] = round(recalculated_daily_wh, 2)
        normalized_rows.append(normalized_row)

    return {
        "rows": normalized_rows,
        "context_items": ai_result.get("context_items", []),
        "uncertain_items": ai_result.get("uncertain_items", []),
        "excluded_items": ai_result.get("excluded_items", []),
    }


def build_openai_request(model_name, user_profile):
    """Build a single Responses API request body for the configured model."""
    request = {
        "model": model_name,
        "instructions": (
            "You extract structured JSON data for a campervan power audit. "
            "Return JSON only. Do not wrap it in markdown. "
            "Keep it concise but complete. "
            "Prefer common campervan defaults. "
            "Use only '12v' or 'ac' for the voltage field. "
            "Every numeric field must be realistic and greater than zero where applicable."
        ),
        "input": (
            "Create a campervan/off-grid power audit.\n"
            "Use only the most likely daily loads mentioned or clearly implied.\n"
            "Keep rows compact and assumption notes short.\n\n"
            f"Van size: {user_profile['van_size']}\n"
            f"Usage: {user_profile['usage']}\n"
            f"Adults: {user_profile['adults']}\n"
            f"Kids: {user_profile['kids']}\n"
            f"Loads description: {user_profile['loads_description']}\n"
        ),
        "max_output_tokens": 1800,
        "parallel_tool_calls": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "campervan_power_audit",
                "schema": get_audit_schema(),
                "strict": True,
            },
            "verbosity": "medium",
        },
    }

    if model_name.startswith("gpt-5"):
        request["text"]["verbosity"] = "low"
        request["reasoning"] = {"effort": "low"}

    return request


def extract_audit_with_openai(user_profile):
    """Call OpenAI Responses API and return structured audit data."""
    if OpenAI is None:
        raise OpenAIExtractionError("The OpenAI Python SDK is not installed in this environment.")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise OpenAIExtractionError("OPENAI_API_KEY is missing. Add it to your environment and try again.")

    client = OpenAI(api_key=api_key, timeout=20.0)
    models_to_try = [OPENAI_MODEL]
    if OPENAI_FALLBACK_MODEL not in models_to_try:
        models_to_try.append(OPENAI_FALLBACK_MODEL)

    last_error = None

    for model_name in models_to_try:
        response = None
        try:
            response = client.responses.create(**build_openai_request(model_name, user_profile))
        except Exception as error:
            error_text = str(error)
            if "timed out" in error_text.lower():
                last_error = OpenAIExtractionError(
                    "OpenAI request timed out before the model returned JSON. "
                    f"Current model: {model_name}. Try again or use a faster model via OPENAI_MODEL."
                )
            else:
                last_error = OpenAIExtractionError(f"OpenAI request failed with model {model_name}: {error}")

            if model_name != models_to_try[-1]:
                print(f"OPENAI RETRY: model {model_name} failed, trying {models_to_try[-1]}")
                continue
            raise last_error from error

        raw_text = extract_response_text(response)
        print(f"OPENAI RAW RESPONSE TEXT [{model_name}]:", raw_text)

        if not raw_text:
            response_debug = serialize_response_debug(response)
            print(f"OPENAI FULL RESPONSE [{model_name}]:", response_debug)
            response_error = getattr(response, "error", None)
            response_status = getattr(response, "status", None)
            incomplete_details = getattr(response, "incomplete_details", None)
            error_message = f"OpenAI returned an empty response with model {model_name}."
            if response_status:
                error_message = f"{error_message} Status: {response_status}."
            if incomplete_details:
                error_message = f"{error_message} Incomplete details: {incomplete_details}."
            if response_error:
                error_message = f"{error_message} {response_error}"
            last_error = OpenAIExtractionError(error_message, raw_response_text=response_debug)
            if model_name != models_to_try[-1]:
                print(f"OPENAI RETRY: model {model_name} returned no text, trying {models_to_try[-1]}")
                continue
            raise last_error

        try:
            parsed_result = json.loads(raw_text)
            normalized_result = normalize_ai_result(parsed_result)
            normalized_result["raw_response_text"] = raw_text
            return normalized_result
        except json.JSONDecodeError as error:
            last_error = OpenAIExtractionError(
                f"OpenAI returned invalid JSON with model {model_name}: {error}",
                raw_response_text=raw_text,
            )
            if model_name != models_to_try[-1]:
                print(f"OPENAI RETRY: model {model_name} returned truncated JSON, trying {models_to_try[-1]}")
                continue
            raise last_error from error

    if last_error is not None:
        raise last_error
    raise OpenAIExtractionError("OpenAI extraction failed before a response could be parsed.")


def calculate_totals(devices):
    """Calculate 12V, AC, and overall daily energy totals."""
    dc_total = 0
    ac_total = 0

    for device in devices:
        if device["voltage"] == "12v":
            dc_total += device["daily_wh"]
        elif device["voltage"] == "ac":
            ac_total += device["daily_wh"] / INVERTER_EFFICIENCY

    overall_total = dc_total + ac_total
    return dc_total, ac_total, overall_total


def export_csv(devices, overall_total):
    """Save the device list and total to a CSV file."""
    with open(CSV_FILE, "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "Device",
                "Category",
                "Quantity",
                "Include",
                "Voltage Type",
                "Watts",
                "Hours",
                "Duty Cycle",
                "Daily Wh",
                "Assumption Note",
            ]
        )

        for device in devices:
            writer.writerow(
                [
                    device["name"],
                    device["category"],
                    device["quantity"],
                    device.get("include", True),
                    device["voltage"],
                    device["watts"],
                    device["hours"],
                    device["duty"],
                    device["daily_wh"],
                    device.get("assumption_note", ""),
                ]
            )

        writer.writerow([])
        writer.writerow(["Total", "", "", "", "", "", "", "", overall_total, ""])


def build_audit_result(user_profile):
    """Build the audit result and reuse the existing totals/export logic."""
    prompt = build_ai_prompt(user_profile)
    ai_result = extract_audit_with_openai(user_profile)
    rows = ai_result["rows"]
    context_items = ai_result["context_items"]
    uncertain_items = ai_result["uncertain_items"]
    excluded_items = ai_result["excluded_items"]
    included_rows = [row for row in rows if row.get("include", True)]
    dc_total, ac_total, overall_total = calculate_totals(included_rows)
    export_csv(rows, overall_total)

    return {
        "prompt": prompt,
        "raw_ai_response": ai_result["raw_response_text"],
        "rows": rows,
        "context_items": context_items,
        "uncertain_items": uncertain_items,
        "excluded_items": excluded_items,
        "totals": {
            "dc_total": round(dc_total, 2),
            "ac_total": round(ac_total, 2),
            "overall_total": round(overall_total, 2),
        },
    }


def build_page_html():
    """Return one simple HTML page for the local app."""
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Van Power Audit</title>
  <style>
    :root {
      --bg: #f5efe3;
      --panel: #fffaf2;
      --line: #d9cbb1;
      --text: #2e2418;
      --accent: #1f6f5f;
      --accent-soft: #d8ece6;
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

    .prompt-box {
      white-space: pre-wrap;
      background: var(--accent-soft);
      border-radius: 12px;
      padding: 14px;
      margin-bottom: 18px;
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

    .table-actions {
      margin-top: 16px;
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }

    .review-list {
      margin-top: 16px;
      padding-left: 18px;
    }

    .review-list li {
      margin-bottom: 8px;
    }

    .json-box {
      white-space: pre-wrap;
      word-break: break-word;
      background: white;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
      overflow-x: auto;
      margin-bottom: 18px;
    }
  </style>
</head>
<body>
  <div class="page">
    <div class="hero">
      <h1>Van Power Audit</h1>
      <p>Fill in a few details, generate an AI draft audit, and tweak the table directly in your browser.</p>
    </div>

    <div class="panel">
      <div class="form-grid">
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
        <label for="loads_description">Messy Load Description</label>
        <textarea id="loads_description" placeholder="Example: remote work, starlink, cooking, heater, camera charging"></textarea>
      </div>

      <div style="margin-top: 16px;">
        <button id="generate_button" type="button">Generate Audit</button>
      </div>

      <div id="status" class="status"></div>
    </div>

    <div id="results" class="results">
      <div class="panel">
        <h2>AI Prompt</h2>
        <div id="prompt_box" class="prompt-box"></div>

        <h2>Raw AI Response</h2>
        <pre id="raw_response_box" class="json-box"></pre>

        <h2>Draft Audit Table</h2>
        <div id="table_container"></div>
        <div class="table-actions">
          <button id="recalculate_button" type="button">Recalculate</button>
        </div>

        <div id="totals" class="totals"></div>

        <h2>Review Items</h2>
        <div id="uncertain_container"></div>
      </div>
    </div>
  </div>

  <script>
    const button = document.getElementById("generate_button");
    const results = document.getElementById("results");
    const statusBox = document.getElementById("status");
    const promptBox = document.getElementById("prompt_box");
    const rawResponseBox = document.getElementById("raw_response_box");
    const tableContainer = document.getElementById("table_container");
    const totalsBox = document.getElementById("totals");
    const uncertainContainer = document.getElementById("uncertain_container");
    const recalculateButton = document.getElementById("recalculate_button");
    const inverterEfficiency = 0.9;

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }

    function renderTable(rows) {
      const header = `
        <tr>
          <th>include</th>
          <th>device</th>
          <th>category</th>
          <th>qty</th>
          <th>voltage</th>
          <th>watts</th>
          <th>hours</th>
          <th>duty</th>
          <th>daily_wh</th>
          <th>source_text</th>
          <th>confidence</th>
          <th>assumption_note</th>
        </tr>
      `;

      const body = rows.map((row) => `
        <tr data-source-text="${escapeHtml(row.source_text || "")}" data-confidence="${escapeHtml(row.confidence ?? "")}">
          <td><input type="checkbox" ${row.include !== false ? "checked" : ""}></td>
          <td contenteditable="true">${escapeHtml(row.name)}</td>
          <td contenteditable="true">${escapeHtml(row.category)}</td>
          <td contenteditable="true">${escapeHtml(row.quantity)}</td>
          <td contenteditable="true">${escapeHtml(row.voltage)}</td>
          <td contenteditable="true">${escapeHtml(row.watts)}</td>
          <td contenteditable="true">${escapeHtml(row.hours)}</td>
          <td contenteditable="true">${escapeHtml(row.duty)}</td>
          <td contenteditable="true">${escapeHtml(row.daily_wh)}</td>
          <td contenteditable="true">${escapeHtml(row.source_text || "")}</td>
          <td contenteditable="true">${escapeHtml(row.confidence ?? "")}</td>
          <td contenteditable="true">${escapeHtml(row.assumption_note || "")}</td>
        </tr>
      `).join("");

      tableContainer.innerHTML = `<table>${header}${body}</table>`;
    }

    function renderReviewItems(contextItems, uncertainItems, excludedItems) {
      const sections = [];

      if (contextItems && contextItems.length > 0) {
        const html = contextItems.map((item) => `
          <li><strong>${escapeHtml(item.text)}</strong> - ${escapeHtml(item.note)}</li>
        `).join("");
        sections.push(`<h3>Context Items</h3><ul class="review-list">${html}</ul>`);
      }

      if (uncertainItems && uncertainItems.length > 0) {
        const html = uncertainItems.map((item) => `
          <li><strong>${escapeHtml(item.text)}</strong> - ${escapeHtml(item.note)}</li>
        `).join("");
        sections.push(`<h3>Uncertain Items</h3><ul class="review-list">${html}</ul>`);
      }

      if (excludedItems && excludedItems.length > 0) {
        const html = excludedItems.map((item) => `
          <li><strong>${escapeHtml(item.text)}</strong> - ${escapeHtml(item.reason)}</li>
        `).join("");
        sections.push(`<h3>Excluded Items</h3><ul class="review-list">${html}</ul>`);
      }

      if (sections.length === 0) {
        uncertainContainer.innerHTML = "<p>No review items right now.</p>";
        return;
      }

      uncertainContainer.innerHTML = sections.join("");
    }

    function toNumber(value, fallback = 0) {
      const number = Number(value);
      if (Number.isFinite(number)) {
        return number;
      }
      return fallback;
    }

    function readRowsFromTable() {
      const rows = [];
      const tableRows = tableContainer.querySelectorAll("table tr");

      for (let index = 1; index < tableRows.length; index += 1) {
        const cells = tableRows[index].querySelectorAll("td");
        if (cells.length !== 12) {
          continue;
        }

        rows.push({
          include: cells[0].querySelector('input[type="checkbox"]').checked,
          name: cells[1].textContent.trim(),
          category: cells[2].textContent.trim(),
          quantity: toNumber(cells[3].textContent.trim(), 1),
          voltage: cells[4].textContent.trim().toLowerCase(),
          watts: toNumber(cells[5].textContent.trim()),
          hours: toNumber(cells[6].textContent.trim()),
          duty: toNumber(cells[7].textContent.trim(), 1),
          daily_wh: toNumber(cells[8].textContent.trim()),
          source_text: cells[9].textContent.trim(),
          confidence: toNumber(cells[10].textContent.trim(), 0),
          assumption_note: cells[11].textContent.trim()
        });
      }

      return rows;
    }

    function recalculateRows(rows) {
      let dcTotal = 0;
      let acTotal = 0;

      const updatedRows = rows.map((row) => {
        const dailyWh = row.quantity * row.watts * row.hours * row.duty;

        if (!row.include) {
          return {
            ...row,
            daily_wh: Number(dailyWh.toFixed(2))
          };
        }

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
        <div class="total-card"><strong>12V Total</strong><div>${totals.dc_total} Wh/day</div></div>
        <div class="total-card"><strong>AC Total</strong><div>${totals.ac_total} Wh/day</div></div>
        <div class="total-card"><strong>Overall Total</strong><div>${totals.overall_total} Wh/day</div></div>
      `;
    }

    async function generateAudit() {
      statusBox.textContent = "Generating audit...";

      const payload = {
        van_size: document.getElementById("van_size").value,
        usage: document.getElementById("usage").value,
        adults: Number(document.getElementById("adults").value || 0),
        kids: Number(document.getElementById("kids").value || 0),
        loads_description: document.getElementById("loads_description").value
      };

      const response = await fetch("/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errorResult = await response.json();
        statusBox.textContent = errorResult.error || "OpenAI request failed.";
        rawResponseBox.textContent = errorResult.raw_ai_response || "";
        results.classList.add("visible");
        return;
      }

      const result = await response.json();
      promptBox.textContent = result.prompt;
      rawResponseBox.textContent = result.raw_ai_response || "";
      renderTable(result.rows);
      renderTotals(result.totals);
      renderReviewItems(result.context_items, result.uncertain_items, result.excluded_items);
      results.classList.add("visible");
      statusBox.textContent = "Draft audit generated. The table below is editable in the browser.";
    }

    button.addEventListener("click", generateAudit);

    recalculateButton.addEventListener("click", () => {
      const rows = readRowsFromTable();
      const recalculated = recalculateRows(rows);
      renderTable(recalculated.rows);
      renderTotals(recalculated.totals);
      statusBox.textContent = "Totals recalculated from the edited table.";
    });
  </script>
</body>
</html>
"""


if FastAPI is not None:
    app = FastAPI(title="Van Power Audit")

    @app.get("/", response_class=HTMLResponse)
    async def home():
        return HTMLResponse(build_page_html())


    @app.post("/generate")
    async def generate(request: Request):
        try:
            payload = await request.json()

            user_profile = {
                "van_size": payload.get("van_size", "medium"),
                "usage": payload.get("usage", "weekend"),
                "adults": payload.get("adults", 2),
                "kids": payload.get("kids", 0),
                "loads_description": payload.get("loads_description", ""),
            }

            result = build_audit_result(user_profile)
            return JSONResponse(result)
        except Exception as e:
            print("OPENAI ERROR:", e)
            traceback.print_exc()
            return JSONResponse(
                {
                    "error": str(e),
                    "raw_ai_response": getattr(e, "raw_response_text", ""),
                },
                status_code=500,
            )

else:
    app = None


if __name__ == "__main__":
    if app is None:
        raise SystemExit("FastAPI and uvicorn are not installed. Install them with: pip install fastapi uvicorn")

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
