# Van Energy Budget

AI-assisted tool that converts plain-language descriptions of van electrical devices into a structured energy budget model.

## What the app does

- Collects a few inputs in the browser: van size, usage, adults, kids, and a free-text load description.
- Calls a FastAPI `POST /generate` endpoint.
- Uses AI to interpret messy user input into a structured device table.
- Normalizes the returned rows into the shape the UI expects.
- Runs deterministic calculations for spending, income, and energy balance totals.
- Loads solar irradiance data from NASA POWER for the selected location.
- Writes the generated energy budget to `power_audit.csv`.
- Returns JSON for the single-page UI, where users can edit the generated device table.

## Architecture

The project is intentionally minimal and currently lives in a single file: [`app.py`](/Users/ianganderton/Development/ogm/app.py).

Architecture summary:

- AI interprets user input into a structured device table.
- Deterministic calculations model energy flows and totals.
- Solar irradiance data comes from NASA POWER.
- Users can edit the generated device table in the browser.

High-level flow:

1. `GET /` returns one HTML page with embedded CSS and JavaScript.
2. The browser posts the form payload to `POST /generate`.
3. `build_user_profile()` normalizes the payload.
4. `build_audit_result()` orchestrates OpenAI extraction, normalization, totals, and CSV export.
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

## OpenAI Integration

The app uses the OpenAI Python SDK `OpenAI` client and the Responses API.

- The request is built in `build_openai_request()`.
- The app asks for JSON output using a JSON schema.
- `extract_audit_with_openai()` tries the configured `OPENAI_MODEL` first.
- If that model is different from the hardcoded fallback, it retries with `gpt-4.1-mini`.
- The raw response text is kept and returned so the UI can surface debugging and review details when needed.

This path is the current working integration and is intentionally preserved in this cleanup pass.
