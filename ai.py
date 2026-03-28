import json
import time

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from config import (
    OPENAI_CLIENT_TIMEOUT_SECONDS,
    OPENAI_FALLBACK_MODEL,
    OPENAI_MODEL,
    get_openai_api_key,
)
from normalization import normalize_ai_result
from utils import (
    OpenAIExtractionError,
    extract_response_text,
    log_timing,
    serialize_response_debug,
)


def build_audit_prompt(user_profile):
    """Turn the user profile into a readable prompt string for the UI."""
    return (
        "Create a campervan/off-grid energy budget device table.\n"
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
        "- duty must be returned as a percentage from 0 to 100\n"
        "- Treat device and appliance use as energy spending inputs for a deterministic energy budget model\n"
        "- Extract structured device-use information only; deterministic code performs the calculations\n"
        "- This is a decision-support model, not a formal electrical design tool\n"
        "\nReturn valid JSON only with:\n"
        "- rows: name, quantity, voltage, watts, hours, duty, daily_wh, source_text, assumption_note\n"
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


def get_openai_client():
    """Create an OpenAI client after validating required environment state."""
    if OpenAI is None:
        raise OpenAIExtractionError("The OpenAI Python SDK is not installed in this environment.")

    api_key = get_openai_api_key()
    if not api_key:
        raise OpenAIExtractionError("OPENAI_API_KEY is missing. Add it to your environment and try again.")

    return OpenAI(api_key=api_key, timeout=OPENAI_CLIENT_TIMEOUT_SECONDS)


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
                        "quantity": {"type": "number"},
                        "voltage": {"type": "string"},
                        "watts": {"type": "number"},
                        "hours": {"type": "number"},
                        "duty": {"type": "number"},
                        "daily_wh": {"type": "number"},
                        "source_text": {"type": "string"},
                        "assumption_note": {"type": "string"},
                    },
                    "required": [
                        "name",
                        "quantity",
                        "voltage",
                        "watts",
                        "hours",
                        "duty",
                        "daily_wh",
                        "source_text",
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


def build_openai_request(model_name, user_profile):
    """Build a single Responses API request body for the configured model."""
    request = {
        "model": model_name,
        "instructions": (
            "Return valid JSON only for a campervan energy budget device table. "
            "Treat loads and appliance use as energy spending inputs for a deterministic energy budget model. "
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
            "duty must be a percentage from 0 to 100. "
            "Extract structured device-use information only; deterministic code performs the calculations. "
            "This is a decision-support model, not a formal electrical design tool. "
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
    """Call OpenAI Responses API and return structured energy budget rows."""
    client = get_openai_client()
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
