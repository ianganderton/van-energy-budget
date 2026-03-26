# Van Power Audit MVP

This is a small FastAPI app that generates a draft campervan/off-grid power audit from a short user profile. The app sends the profile to the OpenAI Responses API, normalizes the structured result, renders the draft in a browser-editable table, and shows calculated daily energy totals.

## What the app does

- Collects a few inputs in the browser: van size, usage, adults, kids, and a free-text load description.
- Calls a FastAPI `POST /generate` endpoint.
- Builds a structured OpenAI request for a campervan power audit.
- Normalizes the returned rows into the shape the UI expects.
- Calculates DC, AC, and overall daily totals.
- Writes the generated audit to `power_audit.csv`.
- Returns JSON for the current single-page UI to render.

## Current architecture

The project is intentionally minimal and currently lives in a single file: [`app.py`](/Users/ianganderton/Development/ogm/app.py).

High-level flow:

1. `GET /` returns one HTML page with embedded CSS and JavaScript.
2. The browser posts the form payload to `POST /generate`.
3. `build_user_profile()` normalizes the payload.
4. `build_audit_result()` orchestrates prompt display, OpenAI extraction, normalization, totals, and CSV export.
5. The frontend renders the returned rows and lets the user recalculate totals after editing the table in the browser.

Key backend helpers:

- `build_openai_request()` builds the Responses API request body.
- `extract_audit_with_openai()` calls OpenAI and handles fallback/error cases.
- `normalize_ai_result()` converts model output into the app's stable row structure.
- `calculate_totals()` and `export_csv()` preserve the current totals/export behavior.

## Run locally

Install dependencies:

```bash
pip install fastapi uvicorn openai
```

Set environment variables:

```bash
export OPENAI_API_KEY="your_api_key_here"
export OPENAI_MODEL="gpt-4.1-mini"
```

Run the app:

```bash
python app.py
```

Then open `http://127.0.0.1:8000` in your browser.

## Required environment variables

- `OPENAI_API_KEY`: required for the OpenAI request path.
- `OPENAI_MODEL`: optional override for the primary model. Defaults to `gpt-4.1-mini`.

## Current OpenAI integration path

The app uses the OpenAI Python SDK `OpenAI` client and the Responses API.

- The request is built in `build_openai_request()`.
- The app asks for JSON output using a JSON schema.
- `extract_audit_with_openai()` tries the configured `OPENAI_MODEL` first.
- If that model is different from the hardcoded fallback, it retries with `gpt-4.1-mini`.
- The raw response text is kept and returned so the current UI can display it for debugging/review.

This path is the current working integration and is intentionally preserved in this cleanup pass.
