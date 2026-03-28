import re

from config import (
    DUTY_FRACTION_MAX,
    DUTY_PERCENT_SCALE,
    FRIDGE_DEFAULT_HOURS_PER_DAY,
    FRIDGE_SUBTYPE_PROFILES,
    INDUCTION_DEFAULT_WATTS,
    INDUCTION_MAX_HOURS_PER_DAY,
    INDUCTION_MIN_HOURS_PER_DAY,
    MIN_DEVICE_WATTS,
)


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


def is_likely_fridge_row(row):
    """Return True when the row text strongly suggests a fridge-like device."""
    fridge_text = " ".join(
        str(row.get(key, "")).strip().lower()
        for key in ("name", "source_text", "assumption_note")
    )
    return any(keyword in fridge_text for keyword in ("fridge", "refrigerator", "freezer"))


def detect_fridge_subtype(row):
    """Map fridge wording to a small controlled subtype set."""
    fridge_text = " ".join(
        str(row.get(key, "")).strip().lower()
        for key in ("name", "source_text", "assumption_note")
    )

    if any(keyword in fridge_text for keyword in ("3-way", "3 way", "three-way", "three way", "absorption")):
        return "absorption_3_way"
    if any(keyword in fridge_text for keyword in ("chest", "portable", "coolbox", "cool box")):
        return "portable_chest_compressor"
    if any(keyword in fridge_text for keyword in ("front opening", "front-opening", "galley")):
        return "front_opening_compressor"
    if any(keyword in fridge_text for keyword in ("upright", "tall", "large")):
        return "upright_large_compressor"
    return "generic_compressor"


def extract_explicit_watts(row):
    """Read a user-provided watt figure from the raw row text when available."""
    fridge_text = " ".join(
        str(row.get(key, "")).strip().lower()
        for key in ("source_text", "name")
    )
    watt_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:w|watt|watts)\b", fridge_text)
    if not watt_match:
        return None

    try:
        watts_value = float(watt_match.group(1))
    except (TypeError, ValueError):
        return None

    if watts_value <= 0:
        return None

    return watts_value


def extract_explicit_runtime_hours(row):
    """Read a user-provided runtime figure from the raw row text when available."""
    device_text = " ".join(
        str(row.get(key, "")).strip().lower()
        for key in ("source_text", "name")
    )
    hours_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)\b", device_text)
    if hours_match:
        try:
            hours_value = float(hours_match.group(1))
        except (TypeError, ValueError):
            hours_value = None
        if hours_value is not None and hours_value >= 0:
            return hours_value

    minutes_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:m|min|mins|minute|minutes)\b", device_text)
    if not minutes_match:
        return None

    try:
        minutes_value = float(minutes_match.group(1))
    except (TypeError, ValueError):
        return None

    if minutes_value < 0:
        return None

    return minutes_value / 60.0


def build_fridge_assumption_note(normalized_row, profile, explicit_watts):
    """Describe the final fridge values actually used in the normalized row."""
    duty_percentage = round(float(normalized_row["duty"]), 0)
    watts_value = round(float(normalized_row["watts"]), 1)
    min_duty = int(profile["min_duty_fraction"] * 100)
    max_duty = int(profile["max_duty_fraction"] * 100)

    if min_duty == max_duty:
        duty_text = f"duty treated as {min_duty}%."
    else:
        duty_text = f"duty constrained to {min_duty}-{max_duty}% and resolved to {int(duty_percentage)}%."

    watt_basis_text = "explicit user wattage preserved" if explicit_watts is not None else "profile wattage applied"

    return (
        f"[m] Fridge profile: {profile['label']}. "
        f"Final values used: {watts_value} W ({watt_basis_text}), "
        f"{int(normalized_row['hours'])} h/day availability, {duty_text} "
        "Hours represent full-day fridge availability; duty controls compressor runtime."
    )


def is_likely_induction_row(row):
    """Return True when the row text strongly suggests an induction cooking device."""
    induction_text = " ".join(
        str(row.get(key, "")).strip().lower()
        for key in ("name", "source_text", "assumption_note")
    )
    return any(
        keyword in induction_text
        for keyword in ("induction", "induction hob", "induction cooktop", "induction cooker")
    )


def build_induction_context_summary(user_profile, modifiers):
    """Summarize which structured context inputs influenced induction assumptions."""
    user_profile = user_profile or {}
    adults = int(user_profile.get("adults", 0) or 0)
    kids = int(user_profile.get("kids", 0) or 0)
    summary_parts = [f"{adults} adults", f"{kids} kids"]

    usage = str(user_profile.get("usage", "")).strip()
    if usage:
        summary_parts.append(f"usage={usage}")

    van_size = str(user_profile.get("van_size", "")).strip()
    if van_size:
        summary_parts.append(f"van={van_size}")

    if modifiers:
        summary_parts.append(", ".join(modifiers))

    return "; ".join(summary_parts)


def resolve_induction_default_hours(row, user_profile=None):
    """Use structured context to derive a realistic induction runtime default."""
    user_profile = user_profile or {}
    adults = max(0, int(user_profile.get("adults", 0) or 0))
    kids = max(0, int(user_profile.get("kids", 0) or 0))
    usage = str(user_profile.get("usage", "")).strip().lower()
    van_size = str(user_profile.get("van_size", "")).strip().lower()
    context_text = " ".join(
        [
            str(user_profile.get("use_case_notes", "")).strip().lower(),
            str(row.get("source_text", "")).strip().lower(),
            str(row.get("name", "")).strip().lower(),
        ]
    )

    # Base daily active cooking runtime in minutes, influenced by household size.
    runtime_minutes = 15 + max(adults - 1, 0) * 8 + kids * 5
    modifiers = []

    if usage == "weekend":
        runtime_minutes *= 0.8
        modifiers.append("weekend use")
    elif usage == "full time":
        runtime_minutes *= 1.15
        modifiers.append("full-time use")

    if van_size == "small":
        runtime_minutes *= 0.9
        modifiers.append("small van")
    elif van_size == "xl":
        runtime_minutes *= 1.1
        modifiers.append("XL van")

    if any(phrase in context_text for phrase in ("mostly cook on gas", "mainly cook on gas", "cook on gas")):
        runtime_minutes *= 0.4
        modifiers.append("mostly gas cooking")

    if "occasionally" in context_text:
        runtime_minutes *= 0.5
        modifiers.append("occasional use")
    elif "rarely" in context_text:
        runtime_minutes *= 0.35
        modifiers.append("rare use")
    elif any(phrase in context_text for phrase in ("daily", "every day", "regularly")):
        runtime_minutes *= 1.15
        modifiers.append("regular use")

    resolved_hours = min(
        max(runtime_minutes / 60.0, INDUCTION_MIN_HOURS_PER_DAY),
        INDUCTION_MAX_HOURS_PER_DAY,
    )
    return resolved_hours, modifiers


def build_induction_assumption_note(normalized_row, explicit_watts, explicit_hours, context_summary):
    """Describe the final induction values actually used in the normalized row."""
    watts_value = round(float(normalized_row["watts"]), 1)
    hours_value = round(float(normalized_row["hours"]), 2)
    watt_basis_text = "explicit user wattage preserved" if explicit_watts is not None else "model wattage applied"
    hour_basis_text = "explicit user runtime preserved" if explicit_hours is not None else "context-based runtime applied"

    return (
        f"[m] Induction load. Final values used: {watts_value} W ({watt_basis_text}), "
        f"{hours_value} h/day active cooking runtime ({hour_basis_text}), duty treated as 100%. "
        f"Context used: {context_summary}. Induction is treated as a high-power intermittent cooking load, "
        "so hours represent active cooking time rather than all-day availability."
    )


def normalize_induction_row(row, normalized_row, user_profile=None):
    """Apply deterministic induction defaults and guardrails before Wh calculation."""
    explicit_watts = extract_explicit_watts(row)
    explicit_hours = extract_explicit_runtime_hours(row)
    resolved_hours, modifiers = resolve_induction_default_hours(row, user_profile=user_profile)

    normalized_row["watts"] = explicit_watts or INDUCTION_DEFAULT_WATTS
    normalized_row["hours"] = min(
        max(clamp_hours_per_day(explicit_hours if explicit_hours is not None else resolved_hours), INDUCTION_MIN_HOURS_PER_DAY),
        INDUCTION_MAX_HOURS_PER_DAY,
    )
    normalized_row["duty"] = DUTY_PERCENT_SCALE
    normalized_row["assumption_note"] = build_induction_assumption_note(
        normalized_row,
        explicit_watts,
        explicit_hours,
        build_induction_context_summary(user_profile, modifiers),
    )

    return normalized_row


def normalize_fridge_row(row, normalized_row):
    """Apply deterministic fridge defaults and guardrails before Wh calculation."""
    subtype_key = detect_fridge_subtype(row)
    profile = FRIDGE_SUBTYPE_PROFILES[subtype_key]
    duty_fraction = normalize_duty_fraction(row.get("duty", profile["default_duty_fraction"]))
    controlled_duty_fraction = min(
        max(duty_fraction, profile["min_duty_fraction"]),
        profile["max_duty_fraction"],
    )

    explicit_watts = extract_explicit_watts(row)
    normalized_row["watts"] = explicit_watts or profile["watts"]
    normalized_row["hours"] = FRIDGE_DEFAULT_HOURS_PER_DAY
    normalized_row["duty"] = controlled_duty_fraction * DUTY_PERCENT_SCALE
    normalized_row["assumption_note"] = build_fridge_assumption_note(
        normalized_row,
        profile,
        explicit_watts,
    )

    return normalized_row


def normalize_ai_result(ai_result, user_profile=None):
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

        if is_likely_fridge_row(row):
            normalized_row = normalize_fridge_row(row, normalized_row)
        elif is_likely_induction_row(row):
            normalized_row = normalize_induction_row(row, normalized_row, user_profile=user_profile)

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
