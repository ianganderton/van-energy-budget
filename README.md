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

The project is intentionally minimal and split into a few focused modules.

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
pip install -r requirements.txt
```

Set environment variables:

```bash
export OPENAI_API_KEY="your_api_key_here"
export OPENAI_MODEL="gpt-4.1-mini"
```

Run the app in local development mode:

```bash
uvicorn app:app --reload
```

Then open `http://127.0.0.1:8000` in your browser.

## Required environment variables

- `OPENAI_API_KEY`: required for the OpenAI request path.
- `OPENAI_MODEL`: optional override for the primary model. Defaults to `gpt-4.1-mini`.

Deployment note:

- Keep `OPENAI_API_KEY` in the deployment environment or secret store rather than hardcoding it in source or committing it to the repository.
- Non-secret defaults remain in [`config.py`](/Users/ianganderton/Development/ogm/config.py).

## Production-style runtime

Run the app with a standard ASGI server command:

```bash
uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}
```

This works well for deployment platforms that provide the port through an environment variable.

## Health check

The app exposes a lightweight health endpoint:

```http
GET /health
```

Expected response:

```json
{ "status": "ok" }
```

The health check does not trigger AI calls, solar API calls, or other expensive work.

## Deployment

This project is compatible with standard ASGI deployment platforms such as:

- Render
- Railway
- Fly.io

It is deployment-friendly because it:

- exposes a standard FastAPI ASGI app as `app:app`
- reads configuration from environment variables
- keeps secrets out of source control
- provides a simple `GET /health` endpoint for platform health checks

## OpenAI Integration

The app uses the OpenAI Python SDK `OpenAI` client and the Responses API.

- The request is built in `build_openai_request()`.
- The app asks for JSON output using a JSON schema.
- `extract_audit_with_openai()` tries the configured `OPENAI_MODEL` first.
- If that model is different from the hardcoded fallback, it retries with `gpt-4.1-mini`.
- The raw response text is kept and returned so the UI can surface debugging and review details when needed.

This path is the current working integration and is intentionally preserved in this cleanup pass.
