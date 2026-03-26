import csv

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse
except ImportError:
    FastAPI = None
    Request = None
    HTMLResponse = None
    JSONResponse = None


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
        "voltage type, watts, hours per day, and duty cycle."
    )


def make_audit_row(device_key, quantity=1):
    """Build one audit row using the same structure used by the table and CSV."""
    data = DEVICE_LIBRARY[device_key]
    daily_wh = data["watts"] * data["hours"] * data["duty"] * quantity

    return {
        "name": device_key,
        "category": data["category"],
        "quantity": quantity,
        "include": True,
        "voltage": data["voltage"],
        "watts": data["watts"],
        "hours": data["hours"],
        "duty": data["duty"],
        "daily_wh": daily_wh,
        "source_text": "",
        "confidence": 0.75,
        "assumption_note": "Mocked default load based on a typical campervan setup.",
    }


def split_load_descriptions(loads_description):
    """Split the messy load description into smaller parts we can review."""
    parts = []

    for line in str(loads_description).splitlines():
        for part in line.split(","):
            cleaned_part = part.strip()
            if cleaned_part:
                parts.append(cleaned_part)

    return parts


def parse_quantity_from_text(text):
    """Read a simple leading quantity like '6 led lights'."""
    parts = text.strip().split(maxsplit=1)

    if parts and parts[0].isdigit():
        quantity = int(parts[0])
        remaining_text = parts[1] if len(parts) > 1 else ""
        return quantity, remaining_text.strip()

    return 1, text.strip()


def infer_quantity_from_phrase(text, default_quantity, user_profile):
    """Use a few simple phrase-based guesses for vague quantities."""
    text_lower = text.lower()
    adults = int(user_profile.get("adults", 0) or 0)
    kids = int(user_profile.get("kids", 0) or 0)

    if "lots of lights" in text_lower or "a lot of lights" in text_lower:
        return 6, "Assumed quantity 6 because the phrase suggests several lights."

    if "some lights" in text_lower:
        return 4, "Assumed quantity 4 because the phrase suggests a few interior lights."

    if "outside strip light" in text_lower or "strip light" in text_lower:
        return 4, "Assumed quantity 4 to cover a few inside lights plus one outside strip light."

    if "kids charging ipads" in text_lower:
        return 2, "Assumed quantity 2 because 'kids' suggests more than one tablet."

    if "fans in summer" in text_lower:
        return 2, "Assumed quantity 2 because the phrase suggests multiple fans in hot weather."

    if "charge phones every day" in text_lower or "charging phones every day" in text_lower:
        people_count = adults + kids
        if people_count > 0:
            return people_count, (
                "Assumed quantity " + str(people_count) +
                " based on the number of adults and kids in the profile."
            )
        return 2, "Assumed quantity 2 because the phrase suggests more than one daily phone charge."

    return default_quantity, ""


def extract_audit_rows(user_profile):
    """Mock the structured rows an AI tool might return later."""
    rows_by_device = {}
    context_items = []
    uncertain_items = []
    excluded_items = []
    usage_text = str(user_profile["usage"]).lower()

    high_power_review_keywords = [
        "ryobi",
        "tool",
        "tools",
        "water blaster",
        "pressure washer",
        "grinder",
        "drill",
        "saw",
    ]

    mapping_rules = [
        {
            "keywords": ["iphone", "phone charger", "phone", "usb charger"],
            "device_key": "phone charger",
            "assumption": "Mapped to phone charger and assumed a small personal charging load.",
            "confidence": 0.95,
        },
        {
            "keywords": ["laptop", "macbook", "notebook computer"],
            "device_key": "laptop charger",
            "assumption": "Mapped to laptop charger and assumed charging rather than full laptop runtime.",
            "confidence": 0.9,
        },
        {
            "keywords": ["bluetooth speaker", "portable speaker"],
            "device_key": "bluetooth speaker charging",
            "assumption": "Mapped to bluetooth speaker charging and assumed occasional USB charging.",
            "confidence": 0.88,
        },
        {
            "keywords": ["drone and batteries", "drone batteries", "drone battery", "drone"],
            "device_key": "drone charging",
            "assumption": "Mapped to drone charging and assumed battery charging after use.",
            "confidence": 0.87,
        },
        {
            "keywords": ["led lights", "led light", "lights", "light strip"],
            "device_key": "lights",
            "assumption": "Mapped to lights and assumed standard campervan LED lighting.",
            "confidence": 0.94,
        },
        {
            "keywords": ["ipad", "ipads", "tablet"],
            "device_key": "tablet charging",
            "assumption": "Mapped to tablet charging and assumed evening charging for personal devices.",
            "confidence": 0.89,
        },
        {
            "keywords": ["starlink", "satellite internet"],
            "device_key": "starlink",
            "assumption": "Mapped directly to Starlink internet equipment.",
            "confidence": 0.98,
        },
        {
            "keywords": ["camera charger", "camera battery", "camera gear"],
            "device_key": "camera battery charger",
            "assumption": "Mapped to camera battery charger and assumed regular battery charging.",
            "confidence": 0.86,
        },
        {
            "keywords": ["diesel heater", "heater"],
            "device_key": "diesel heater",
            "assumption": "Mapped to diesel heater and assumed a normal overnight duty cycle.",
            "confidence": 0.82,
        },
        {
            "keywords": ["water pump", "sink pump", "pump"],
            "device_key": "water pump",
            "assumption": "Mapped to water pump and assumed short daily use.",
            "confidence": 0.84,
        },
        {
            "keywords": ["maxxair fan", "maxxfan", "roof fan"],
            "device_key": "maxxair fan",
            "assumption": "Mapped to roof ventilation fan and assumed a typical daily runtime.",
            "confidence": 0.9,
        },
        {
            "keywords": ["fans", "fan", "summer ventilation"],
            "device_key": "fan",
            "assumption": "Mapped to fan ventilation and assumed use during warmer weather.",
            "confidence": 0.76,
        },
        {
            "keywords": ["fridge", "compressor fridge"],
            "device_key": "compressor fridge",
            "assumption": "Mapped to compressor fridge and assumed a standard 12V duty cycle.",
            "confidence": 0.91,
        },
        {
            "keywords": ["tv", "television"],
            "device_key": "tv",
            "assumption": "Mapped to TV use and assumed a few evening viewing hours.",
            "confidence": 0.9,
        },
        {
            "keywords": ["coffee machine", "espresso machine", "coffee maker"],
            "device_key": "coffee machine",
            "assumption": "Mapped to coffee machine use and assumed short morning runs.",
            "confidence": 0.85,
        },
        {
            "keywords": ["induction cooktop", "induction stove", "cooktop"],
            "device_key": "induction cooktop",
            "assumption": "Mapped to induction cooktop and assumed short cooking sessions.",
            "confidence": 0.89,
        },
        {
            "keywords": ["microwave"],
            "device_key": "microwave",
            "assumption": "Mapped to microwave and assumed short heating use.",
            "confidence": 0.96,
        },
    ]

    if "remote" in usage_text or "work" in usage_text:
        row = make_audit_row("laptop charger")
        row["source_text"] = str(user_profile["usage"])
        row["confidence"] = 0.67
        row["assumption_note"] = (
            "Mapped from usage '" + str(user_profile["usage"]) +
            "' and assumed remote work means at least one laptop charger."
        )
        rows_by_device[row["name"]] = row

    for part in split_load_descriptions(user_profile["loads_description"]):
        quantity, cleaned_part = parse_quantity_from_text(part)
        part_lower = cleaned_part.lower()

        if (
            ("trip" in part_lower and "light" not in part_lower)
            or ("trips" in part_lower and "light" not in part_lower)
            or ("new zealand" in part_lower and "light" not in part_lower)
            or ("mountain bike" in part_lower and "light" not in part_lower)
            or "family of four" in part_lower
            or "bigger motorhome" in part_lower
            or ("motorhome" in part_lower and "light" not in part_lower)
            or "transit van setup" in part_lower
            or "van setup" in part_lower
            or "camper setup" in part_lower
            or "vehicle setup" in part_lower
            or "plug into mains" in part_lower
            or "plugged into mains" in part_lower
            or "shore power" in part_lower
        ):
            context_items.append(
                {
                    "text": part,
                    "note": "Useful living or trip context, but not treated as a direct electrical load.",
                }
            )
            continue

        if any(keyword in part_lower for keyword in high_power_review_keywords):
            excluded_items.append(
                {
                    "text": part,
                    "reason": "Looks like an occasional tool or high-power load, so it was excluded from the draft audit.",
                }
            )
            continue

        matched_rule = None
        for rule in mapping_rules:
            if any(keyword in part_lower for keyword in rule["keywords"]):
                matched_rule = rule
                break

        if matched_rule is None:
            uncertain_items.append(
                {
                    "text": part,
                    "note": "This load was mentioned, but it was not confidently mapped to a known device yet.",
                }
            )
            continue

        device_key = matched_rule["device_key"]
        quantity, quantity_note = infer_quantity_from_phrase(cleaned_part, quantity, user_profile)
        row = rows_by_device.get(device_key)

        if row is None:
            row = make_audit_row(device_key, quantity)
            row["source_text"] = part
            row["confidence"] = matched_rule["confidence"]
            row["assumption_note"] = (
                "Mapped from '" + part + "'. " + matched_rule["assumption"]
            )
            if quantity_note:
                row["assumption_note"] += " " + quantity_note
            rows_by_device[device_key] = row
        else:
            row["quantity"] += quantity
            row["daily_wh"] = row["watts"] * row["hours"] * row["duty"] * row["quantity"]
            row["source_text"] += "; " + part
            row["confidence"] = min(row["confidence"], matched_rule["confidence"])
            row["assumption_note"] += " Also matched '" + part + "'."
            if quantity_note:
                row["assumption_note"] += " " + quantity_note

    rows = list(rows_by_device.values())
    return rows, context_items, uncertain_items, excluded_items


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
    """Build the mocked audit result and reuse the existing totals/export logic."""
    prompt = build_ai_prompt(user_profile)
    rows, context_items, uncertain_items, excluded_items = extract_audit_rows(user_profile)
    included_rows = [row for row in rows if row.get("include", True)]
    dc_total, ac_total, overall_total = calculate_totals(included_rows)
    export_csv(rows, overall_total)

    raw_ai_response = {
        "rows": rows,
        "context_items": context_items,
        "uncertain_items": uncertain_items,
        "excluded_items": excluded_items,
        "note": "This is mocked structured output that stands in for a future AI response.",
    }

    return {
        "prompt": prompt,
        "raw_ai_response": raw_ai_response,
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
      <p>Fill in a few details, generate a mocked AI draft audit, and tweak the table directly in your browser.</p>
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
      statusBox.textContent = "Generating mocked audit...";

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
        statusBox.textContent = "Something went wrong while generating the audit.";
        return;
      }

      const result = await response.json();
      promptBox.textContent = result.prompt;
      rawResponseBox.textContent = JSON.stringify(result.raw_ai_response, null, 2);
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

else:
    app = None


if __name__ == "__main__":
    if app is None:
        raise SystemExit("FastAPI and uvicorn are not installed. Install them with: pip install fastapi uvicorn")

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
