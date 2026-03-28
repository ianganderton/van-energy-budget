from config import DUTY_FRACTION_MAX, DUTY_PERCENT_SCALE, MIN_DEVICE_WATTS


def clamp_hours_per_day(raw_value):
    """Clamp average daily hours into the physically valid 0-24 range."""
    try:
        hours_value = float(raw_value)
    except (TypeError, ValueError):
        hours_value = 0.0

    return min(max(hours_value, 0.0), 24.0)


def normalize_duty_fraction(raw_value):
    """Normalize duty input into a 0-1 fraction before downstream calculations."""
    try:
        duty_value = float(raw_value)
    except (TypeError, ValueError):
        duty_value = DUTY_FRACTION_MAX

    if duty_value > DUTY_FRACTION_MAX:
        duty_value /= DUTY_PERCENT_SCALE

    return min(max(duty_value, 0.0), DUTY_FRACTION_MAX)


def normalize_positive_watts(raw_value):
    """Ensure watts is always a positive value for deterministic calculations."""
    try:
        watts_value = float(raw_value)
    except (TypeError, ValueError):
        watts_value = MIN_DEVICE_WATTS

    if watts_value <= 0:
        return MIN_DEVICE_WATTS

    return watts_value


def normalize_quantity(raw_value):
    """Ensure quantity is a whole-number count of at least one device."""
    try:
        quantity_value = float(raw_value)
    except (TypeError, ValueError):
        quantity_value = 1.0

    if quantity_value < 1:
        return 1

    return max(1, int(round(quantity_value)))


def _calculate_daily_wh(quantity, watts, hours, duty_percentage):
    """Calculate daily Wh from UI-style duty percentage values."""
    return quantity * watts * hours * (duty_percentage / 100.0)


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
            "quantity": normalize_quantity(row.get("quantity", 1)),
            "voltage": normalized_voltage,
            "watts": normalize_positive_watts(row.get("watts", 0)),
            "hours": clamp_hours_per_day(row.get("hours", 0)),
            "duty": normalize_duty_fraction(row.get("duty", 100)) * DUTY_PERCENT_SCALE,
            "daily_wh": float(row.get("daily_wh", 0)),
            "source_text": str(row.get("source_text", "")).strip(),
            "assumption_note": str(row.get("assumption_note", "")).strip(),
        }

        recalculated_daily_wh = _calculate_daily_wh(
            normalized_row["quantity"],
            normalized_row["watts"],
            normalized_row["hours"],
            normalized_row["duty"],
        )
        normalized_row["daily_wh"] = round(recalculated_daily_wh, 2)
        normalized_rows.append(normalized_row)

    normalized_rows.sort(key=lambda row: row.get("daily_wh", 0), reverse=True)

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
