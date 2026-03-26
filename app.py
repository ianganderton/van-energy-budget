import csv

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
    "phone charger": {"watts": 20, "hours": 2, "duty": 1.0, "voltage": "ac", "category": "charging"},
    "diesel heater": {"watts": 40, "hours": 8, "duty": 0.5, "voltage": "12v", "category": "ventilation"},
    "water pump": {"watts": 60, "hours": 0.5, "duty": 0.3, "voltage": "12v", "category": "water"},
    "maxxair fan": {"watts": 30, "hours": 8, "duty": 0.8, "voltage": "12v", "category": "ventilation"},
    "compressor fridge": {"watts": 50, "hours": 24, "duty": 0.35, "voltage": "12v", "category": "cooling"},
    "laptop charger": {"watts": 90, "hours": 2, "duty": 1.0, "voltage": "ac", "category": "charging"},
    "camera battery charger": {"watts": 25, "hours": 2, "duty": 1.0, "voltage": "ac", "category": "charging"},
    "starlink": {"watts": 60, "hours": 6, "duty": 1.0, "voltage": "ac", "category": "internet"},
    "induction cooktop": {"watts": 1800, "hours": 0.5, "duty": 1.0, "voltage": "ac", "category": "cooking"},
    "microwave": {"watts": 1000, "hours": 0.25, "duty": 1.0, "voltage": "ac", "category": "cooking"},
}

# Friendly names that should map back to the main device keys.
# We keep this simple: if the alias text appears inside the user's input,
# we treat it as a match.
DEVICE_ALIASES = {
    "fridge": ["small fridge", "12v fridge"],
    "phone charger": ["phone", "usb charger", "iphone charger", "android charger"],
    "diesel heater": ["heater", "parking heater", "air heater"],
    "water pump": ["pump", "sink pump", "fresh water pump"],
    "fan": ["roof fan"],
    "lights": ["led lights"],
    "maxxair fan": ["maxxfan", "maxxair", "ceiling fan"],
    "compressor fridge": ["12v compressor fridge", "van fridge", "cooler fridge"],
    "laptop charger": ["charger for laptop", "computer charger", "usb-c laptop charger"],
    "camera battery charger": ["camera charger", "battery charger", "camera batteries"],
    "starlink": ["internet", "satellite internet", "wifi dish"],
    "induction cooktop": ["cooktop", "induction stove", "induction hob"],
    "microwave": ["microwave oven"],
}

INVERTER_EFFICIENCY = 0.9
CSV_FILE = "power_audit.csv"


def parse_device_names(user_input):
    """Split a comma-separated or multi-line list into clean device names."""
    device_names = []

    for line in user_input.splitlines():
        for name in line.split(","):
            cleaned_name = name.strip().lower()
            if cleaned_name:
                device_names.append(cleaned_name)

    return device_names


def parse_quantity_and_name(raw_name):
    """Read an optional leading quantity like '2 phone chargers'."""
    parts = raw_name.split(maxsplit=1)

    if parts and parts[0].isdigit():
        quantity = int(parts[0])
        name = parts[1] if len(parts) > 1 else ""
        return quantity, name.strip()

    return 1, raw_name


def singularize_name(name):
    """Make a simple singular version for inputs like 'laptops'."""
    if name.endswith("s") and len(name) > 1:
        return name[:-1]

    return name


def resolve_device_name(name):
    """Return the main device key for an exact name or a simple alias match."""
    if name in DEVICE_LIBRARY:
        return name

    singular_name = singularize_name(name)
    if singular_name in DEVICE_LIBRARY:
        return singular_name

    for device_key, aliases in DEVICE_ALIASES.items():
        for alias in aliases:
            if alias in name or alias in singular_name:
                return device_key

    return None


def build_device_rows(device_names):
    """Turn device names into rows we can print and export."""
    devices_by_key = {}
    unknown_devices = []

    for raw_name in device_names:
        quantity, name = parse_quantity_and_name(raw_name)
        device_key = resolve_device_name(name)

        if device_key is None:
            unknown_devices.append(raw_name)
            continue

        data = DEVICE_LIBRARY[device_key]
        daily_wh = data["watts"] * data["hours"] * data["duty"] * quantity

        if device_key not in devices_by_key:
            devices_by_key[device_key] = {
                "name": device_key,
                "category": data["category"],
                "quantity": 0,
                "voltage": data["voltage"],
                "watts": data["watts"],
                "hours": data["hours"],
                "duty": data["duty"],
                "daily_wh": 0,
            }

        devices_by_key[device_key]["quantity"] += quantity
        devices_by_key[device_key]["daily_wh"] += daily_wh

    devices = list(devices_by_key.values())
    return devices, unknown_devices


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


def print_report(devices, dc_total, ac_total, overall_total):
    """Show the results in a simple table."""
    print("\nDevice\t\tCategory\tQty\tType\tWatts\tHours\tDuty\tDaily Wh")
    print("-" * 98)

    for device in devices:
        print(
            f"{device['name']:<15}"
            f"{device['category']:<16}"
            f"{device['quantity']:<8}"
            f"{device['voltage']:<8}"
            f"{device['watts']:<8}"
            f"{device['hours']:<8}"
            f"{device['duty']:<8}"
            f"{device['daily_wh']:.0f}"
        )

    print("-" * 98)
    print(f"12V Total: {dc_total:.0f} Wh/day")
    print(f"AC Total: {ac_total:.0f} Wh/day")
    print(f"Overall Total: {overall_total:.0f} Wh/day")


def print_unknown_devices(unknown_devices):
    """Show any devices we could not match."""
    if not unknown_devices:
        return

    print("\nUnknown devices")
    print("-" * 30)

    for device_name in unknown_devices:
        print(device_name)


def export_csv(devices, overall_total):
    """Save the device list and total to a CSV file."""
    with open(CSV_FILE, "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Device", "Category", "Quantity", "Voltage Type", "Watts", "Hours", "Duty Cycle", "Daily Wh"])

        for device in devices:
            writer.writerow(
                [
                    device["name"],
                    device["category"],
                    device["quantity"],
                    device["voltage"],
                    device["watts"],
                    device["hours"],
                    device["duty"],
                    device["daily_wh"],
                ]
            )

        writer.writerow([])
        writer.writerow(["Total", "", "", "", "", "", "", overall_total])

    print(f"Saved to {CSV_FILE}")


def main():
    print("Enter devices. Press Enter on a blank line when finished:")
    input_lines = []

    while True:
        line = input()
        if line == "":
            break
        input_lines.append(line)

    user_input = "\n".join(input_lines)
    device_names = parse_device_names(user_input)
    devices, unknown_devices = build_device_rows(device_names)
    dc_total, ac_total, overall_total = calculate_totals(devices)

    print_report(devices, dc_total, ac_total, overall_total)
    print_unknown_devices(unknown_devices)
    export_csv(devices, overall_total)


if __name__ == "__main__":
    main()
