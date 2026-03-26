import csv
import json
import os
import time
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


INVERTER_EFFICIENCY = 0.9
CSV_FILE = "power_audit.csv"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
OPENAI_FALLBACK_MODEL = "gpt-4.1-mini"


def log_timing(stage, start_time, **details):
    """Print a simple elapsed-time log line for request instrumentation."""
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    detail_parts = [f"{key}={value}" for key, value in details.items()]
    detail_text = f" | {' '.join(detail_parts)}" if detail_parts else ""
    print(f"TIMING: {stage} | elapsed_ms={elapsed_ms:.1f}{detail_text}")


def format_user_profile(user_profile):
    """Format the user profile into a stable block of text for the prompt and UI."""
    return (
        f"Van size: {user_profile['van_size']}\n"
        f"Usage: {user_profile['usage']}\n"
        f"Adults: {user_profile['adults']}\n"
        f"Kids: {user_profile['kids']}\n"
        f"Lifestyle / van use context: {user_profile['use_case_notes']}\n"
        f"Electrical devices: {user_profile['loads_description']}\n"
    )


def build_audit_prompt(user_profile):
    """Turn the user profile into a readable prompt string for the UI."""
    return (
        "Create a campervan/off-grid power audit.\n"
        "\nInputs:\n"
        f"- Van size: {user_profile['van_size']}\n"
        f"- Usage: {user_profile['usage']}\n"
        f"- Adults: {user_profile['adults']}\n"
        f"- Kids: {user_profile['kids']}\n"
        f"- Lifestyle context: {user_profile['use_case_notes']}\n"
        f"- Electrical devices: {user_profile['loads_description']}\n"
        "\nRules:\n"
        "- Build rows only from devices explicitly mentioned in Electrical devices\n"
        "- Every row must map directly to a device explicitly mentioned in Electrical devices\n"
        "- Never create rows from Lifestyle context alone\n"
        "- Lifestyle context may only affect hours, duty, assumption_note, and review_items\n"
        "- If Lifestyle context suggests a device that is not listed, do not add it as a row; add it only to review_items\n"
        "- If inputs conflict, prefer Electrical devices\n"
        "- source_text must come only from Electrical devices\n"
        "- source_text must be a raw exact extract from Electrical devices\n"
        "- Do not reword, summarise, or interpret source_text\n"
        "- name may be cleaned, but source_text must stay raw\n"
        "- If a device is ambiguous, keep the user's wording as the row basis rather than converting it into a different device type\n"
        "\nReturn valid JSON only with:\n"
        "- rows: name, category, quantity, include, voltage, watts, hours, duty, daily_wh, source_text, confidence, assumption_note\n"
        "- review_items: type, text, note"
    )


def build_openai_input(user_profile):
    """Build the compact input block sent to the OpenAI API."""
    return (
        f"Van size: {user_profile['van_size']}\n"
        f"Usage: {user_profile['usage']}\n"
        f"Adults: {user_profile['adults']}\n"
        f"Kids: {user_profile['kids']}\n"
        f"Lifestyle context: {user_profile['use_case_notes']}\n"
        f"Electrical devices: {user_profile['loads_description']}"
    )


def build_user_profile(payload):
    """Normalize the request payload into the shape used by the app."""
    return {
        "van_size": payload.get("van_size", "medium"),
        "usage": payload.get("usage", "weekend"),
        "adults": payload.get("adults", 2),
        "kids": payload.get("kids", 0),
        "use_case_notes": payload.get("use_case_notes", ""),
        "loads_description": payload.get("loads_description", ""),
    }


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
            "review_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "text": {"type": "string"},
                        "note": {"type": "string"},
                    },
                    "required": ["type", "text", "note"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["rows", "review_items"],
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

    normalized_review_items = []

    for item in ai_result.get("review_items", []):
        normalized_review_items.append(
            {
                "type": str(item.get("type", "")).strip() or "review",
                "text": str(item.get("text", "")).strip(),
                "note": str(item.get("note", "")).strip(),
            }
        )

    for item in ai_result.get("context_items", []):
        normalized_review_items.append(
            {
                "type": "context",
                "text": str(item.get("text", "")).strip(),
                "note": str(item.get("note", "")).strip(),
            }
        )

    for item in ai_result.get("uncertain_items", []):
        normalized_review_items.append(
            {
                "type": "uncertain",
                "text": str(item.get("text", "")).strip(),
                "note": str(item.get("note", "")).strip(),
            }
        )

    for item in ai_result.get("excluded_items", []):
        normalized_review_items.append(
            {
                "type": "excluded",
                "text": str(item.get("text", "")).strip(),
                "note": str(item.get("reason", "")).strip(),
            }
        )

    return {
        "rows": normalized_rows,
        "review_items": normalized_review_items,
    }


def build_openai_request(model_name, user_profile):
    """Build a single Responses API request body for the configured model."""
    request = {
        "model": model_name,
        "instructions": (
            "Return valid JSON only for a campervan power audit. "
            "Prefer common campervan defaults. "
            "Use only '12v' or 'ac' for voltage. "
            "Numeric fields must be realistic and greater than zero where applicable. "
            "Build rows only from devices explicitly mentioned in Electrical devices. "
            "Every row must map directly to a device explicitly mentioned there. "
            "Never create rows from Lifestyle context alone. "
            "Lifestyle context may only affect hours, duty, assumption_note, and review_items. "
            "If Lifestyle context suggests a device that is not listed, add it only to review_items. "
            "If inputs conflict, prefer Electrical devices. "
            "source_text must come only from Electrical devices and must be a raw exact extract. "
            "Do not reword, summarise, or interpret source_text. "
            "name may be cleaned, but source_text must stay raw. "
            "If a device is ambiguous, keep the user's wording as the row basis rather than converting it into a different device type. "
            "Use review_items for assumptions, ambiguities, likely mistakes, missing loads, and excluded or ignored inputs. "
            "Each review_items entry must have type, text, and note."
        ),
        "input": build_openai_input(user_profile),
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


def extract_audit_with_openai(user_profile, request_start_time=None):
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
            openai_call_start = time.perf_counter()
            log_timing("OpenAI API call start", request_start_time or openai_call_start, model=model_name)
            response = client.responses.create(**build_openai_request(model_name, user_profile))
            log_timing("OpenAI API call end", request_start_time or openai_call_start, model=model_name)
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
            log_timing("JSON parse / normalisation complete", request_start_time or openai_call_start, model=model_name)
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


def build_audit_result(user_profile, request_start_time=None):
    """Build the audit result and reuse the existing totals/export logic."""
    request_start = request_start_time or time.perf_counter()
    prompt = build_audit_prompt(user_profile)
    openai_input = build_openai_input(user_profile)
    log_timing(
        "prompt build complete",
        request_start,
        model=OPENAI_MODEL,
        prompt_length_chars=len(prompt),
        api_input_length_chars=len(openai_input),
    )
    ai_result = extract_audit_with_openai(user_profile, request_start_time=request_start)
    rows = ai_result["rows"]
    review_items = ai_result["review_items"]
    included_rows = [row for row in rows if row.get("include", True)]
    dc_total, ac_total, overall_total = calculate_totals(included_rows)
    log_timing("totals calculation complete", request_start)
    export_csv(rows, overall_total)

    return {
        "prompt": prompt,
        "raw_ai_response": ai_result["raw_response_text"],
        "rows": rows,
        "review_items": review_items,
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
        <p class="helper-text">Describe the kind of trips, how often you travel, whether you stay off-grid or at campgrounds, whether you work from the van, what seasons you use it in, and anything else that affects power use.</p>
        <!-- TEMP TEST DATA - REMOVE LATER -->
        <textarea id="use_case_notes" placeholder="Weekend trips most months, a few longer holidays, usually 2–3 nights off-grid, some winter trips, fridge always on, mostly cook on gas, sometimes stay at campgrounds, charge phones and camera gear, and occasionally work from the van on a laptop.">Weekend trips most months, a few longer holidays, usually 2–3 nights off-grid, some winter trips, fridge always on, mostly cook on gas, sometimes stay at campgrounds, charge phones and camera gear, and occasionally work from the van on a laptop.</textarea>
      </div>

      <div style="margin-top: 16px;">
        <label for="loads_description">What electrical devices will you use?</label>
        <p class="helper-text">List the electrical items you expect to run or charge in the van. Use normal language. Include anything regular or occasional, even if you are unsure of the wattage.</p>
        <!-- TEMP TEST DATA - REMOVE LATER -->
        <textarea id="loads_description" placeholder="12V fridge, diesel heater fan, roof fan, LED lights, 2 phones, laptop, camera battery charger, drone batteries, water pump, electric blanket, induction hob used occasionally.">12V fridge, diesel heater fan, roof fan, LED lights, 2 phones, laptop, camera battery charger, drone batteries, water pump, electric blanket, induction hob used occasionally.</textarea>
      </div>

      <div style="margin-top: 16px;">
        <button id="generate_button" type="button">Generate Solar + Audit</button>
      </div>

      <div id="status" class="status"></div>
    </div>

    <div id="results" class="results">
      <div class="panel">
        <h2>Solar Audit</h2>
        <div id="solar_error" class="solar-error" style="display:none"></div>
        <div id="solar_results" style="display:none">
          <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline">
            <div>
              <div style="font-weight:900;font-size:18px">Average daily solar hours by month</div>
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
    const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const NASA_KEYS = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
    const generateButton = document.getElementById("generate_button");
    const results = document.getElementById("results");
    const statusBox = document.getElementById("status");
    const promptBox = document.getElementById("prompt_box");
    const rawResponseBox = document.getElementById("raw_response_box");
    const tableContainer = document.getElementById("table_container");
    const totalsBox = document.getElementById("totals");
    const reviewItemsContainer = document.getElementById("uncertain_container");
    const recalculateButton = document.getElementById("recalculate_button");
    const solarErrorBox = document.getElementById("solar_error");
    const solarResults = document.getElementById("solar_results");
    const solarName = document.getElementById("solar_name");
    const solarLat = document.getElementById("solar_lat");
    const solarLon = document.getElementById("solar_lon");
    const solarSource = document.getElementById("solar_source");
    const solarTableBody = document.getElementById("solar_tbody");
    const solarCanvas = document.getElementById("solar_chart");
    const solarCtx = solarCanvas.getContext("2d");
    const inverterEfficiency = 0.9;
    let generateTimerId = null;

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
      statusBox.textContent = `Generating solar data and audit... ${formatElapsedSeconds(startTime)}s`;
      generateTimerId = window.setInterval(() => {
        statusBox.textContent = `Generating solar data and audit... ${formatElapsedSeconds(startTime)}s`;
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
        "?parameters=ALLSKY_SFC_SW_DWN",
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
      const param = data?.properties?.parameter?.ALLSKY_SFC_SW_DWN;
      if (!param) {
        throw new Error("Solar data returned in an unexpected format.");
      }

      return { data, param };
    }

    function buildSolarRows(param) {
      return NASA_KEYS.map((key, index) => {
        const value = Number(param[key]);
        return {
          month: MONTHS[index],
          solarHours: Number.isFinite(value) ? round(value, 2) : null
        };
      });
    }

    function renderSolarTable(rows) {
      const monthCells = rows.map((row) => `<th>${row.month}</th>`).join("");
      const valueCells = rows.map((row) => `<td>${row.solarHours ?? "—"}${row.solarHours == null ? "" : " h/day"}</td>`).join("");

      solarTableBody.innerHTML = `
        <tr>
          <th>Month</th>
          ${monthCells}
        </tr>
        <tr>
          <td>Solar hours</td>
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
      solarCtx.fillText("Average Daily Solar Hours", 24, 20);

      solarCtx.fillStyle = "#475569";
      solarCtx.font = "14px system-ui";
      solarCtx.fillText(displayLocation, 24, 50);

      const pad = { l: 90, r: 26, t: 85, b: 90 };
      const plotWidth = width - pad.l - pad.r;
      const plotHeight = height - pad.t - pad.b;
      const values = rows.map((row) => (typeof row.solarHours === "number" ? row.solarHours : 0));
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
        solarCtx.fillText(round(t * yMax, 1) + " h", pad.l - 10, y);
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
        const value = typeof rows[i].solarHours === "number" ? rows[i].solarHours : 0;
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

      solarName.textContent = displayName;
      solarLat.textContent = round(lat, 4);
      solarLon.textContent = round(lon, 4);
      solarSource.textContent = data?.properties?.sources?.length
        ? ("Source: " + data.properties.sources.join(", "))
        : "Source: NASA POWER";

      renderSolarTable(rows);
      drawSolarChart(rows, displayName);
      solarResults.style.display = "block";
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
      const startTime = performance.now();
      startGenerateTimer(startTime);
      results.classList.add("visible");

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
        const elapsed = formatElapsedSeconds(startTime);
        statusBox.textContent = errorResult.error
          ? `Audit failed after ${elapsed}s: ${errorResult.error}`
          : `Audit failed after ${elapsed}s`;
        rawResponseBox.textContent = errorResult.raw_ai_response || "";
        return;
      }

      clearGenerateTimer();
      const elapsed = formatElapsedSeconds(startTime);
      const result = await response.json();
      promptBox.textContent = result.prompt;
      rawResponseBox.textContent = result.raw_ai_response || "";
      renderTable(result.rows);
      renderTotals(result.totals);
      renderReviewItems(result.review_items);
      statusBox.textContent = `Solar data and draft audit generated in ${elapsed}s`;
    }

    generateButton.addEventListener("click", generateAudit);

    recalculateButton.addEventListener("click", () => {
      const rows = readRowsFromTable();
      const recalculated = recalculateRows(rows);
      renderTable(recalculated.rows);
      renderTotals(recalculated.totals);
      statusBox.textContent = "Totals recalculated from the edited table.";
    });

    drawSolarChart(MONTHS.map((month) => ({ month, solarHours: 0 })), "Selected location");
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
        request_start = time.perf_counter()
        log_timing("request received", request_start)
        try:
            payload = await request.json()
            user_profile = build_user_profile(payload)
            result = build_audit_result(user_profile, request_start_time=request_start)
            log_timing("response ready", request_start, total_duration_ms=f"{(time.perf_counter() - request_start) * 1000:.1f}")
            log_timing("total request duration", request_start)
            return JSONResponse(result)
        except Exception as e:
            print("OPENAI ERROR:", e)
            log_timing("response ready", request_start, total_duration_ms=f"{(time.perf_counter() - request_start) * 1000:.1f}", status="error")
            log_timing("total request duration", request_start, status="error")
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
