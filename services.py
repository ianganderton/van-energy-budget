import csv
import time

from ai import build_audit_prompt, build_openai_input, extract_audit_with_openai
from config import CSV_FILE, INVERTER_EFFICIENCY, MAX_AI_INPUT_FIELD_LENGTH, OPENAI_MODEL
from utils import log_timing


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


def validate_ai_input_lengths(user_profile):
    """Reject oversized free-text inputs before they reach the AI request path."""
    protected_fields = {
        "use_case_notes": "Lifestyle context",
        "loads_description": "Electrical devices",
    }

    for field_name, label in protected_fields.items():
        field_value = str(user_profile.get(field_name, ""))
        if len(field_value) > MAX_AI_INPUT_FIELD_LENGTH:
            raise ValueError(
                f"{label} is too long. Maximum length is {MAX_AI_INPUT_FIELD_LENGTH} characters."
            )


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
                "Quantity",
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
                    device["quantity"],
                    device["voltage"],
                    device["watts"],
                    device["hours"],
                    device["duty"],
                    device["daily_wh"],
                    device.get("assumption_note", ""),
                ]
            )

        writer.writerow([])
        writer.writerow(["Total", "", "", "", "", "", "", overall_total, ""])


def build_audit_result(user_profile, request_start_time=None):
    """Build the energy budget result and reuse the existing totals/export logic."""
    request_start = request_start_time or time.perf_counter()
    validate_ai_input_lengths(user_profile)
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
    dc_total, ac_total, overall_total = calculate_totals(rows)
    totals = {
        "dc_total": round(dc_total, 2),
        "ac_total": round(ac_total, 2),
        "overall_total": round(overall_total, 2),
    }
    log_timing("totals calculation complete", request_start)
    export_csv(rows, overall_total)

    return {
        "rows": rows,
        "review_items": review_items,
        "totals": totals,
    }
