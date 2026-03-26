import csv

# A single library of known devices. Each device has:
# - watts: power draw
# - hours: daily runtime
# - duty: how often it is actually running during those hours
# - voltage: either "12v" or "ac"
DEVICE_LIBRARY = {
    "fridge": {"watts": 45, "hours": 24, "duty": 0.4, "voltage": "12v"},
    "laptop": {"watts": 60, "hours": 2, "duty": 1.0, "voltage": "ac"},
    "fan": {"watts": 20, "hours": 5, "duty": 0.7, "voltage": "12v"},
    "lights": {"watts": 10, "hours": 5, "duty": 1.0, "voltage": "12v"},
}

# Friendly names that should map back to the main device keys.
# We keep this simple: if the alias text appears inside the user's input,
# we treat it as a match.
DEVICE_ALIASES = {
    "fridge": ["small fridge", "12v fridge"],
    "fan": ["roof fan"],
    "lights": ["led lights"],
}

INVERTER_EFFICIENCY = 0.9
CSV_FILE = "power_audit.csv"


def parse_device_names(user_input):
    """Split a comma-separated list like 'fridge, laptop, fan' into clean names."""
    return [name.strip().lower() for name in user_input.split(",") if name.strip()]


def resolve_device_name(name):
    """Return the main device key for an exact name or a simple alias match."""
    if name in DEVICE_LIBRARY:
        return name

    for device_key, aliases in DEVICE_ALIASES.items():
        for alias in aliases:
            if alias in name:
                return device_key

    return None


def build_device_rows(device_names):
    """Turn device names into rows we can print and export."""
    devices = []

    for raw_name in device_names:
        device_key = resolve_device_name(raw_name)

        if device_key is None:
            print(f"Unknown device: {raw_name}")
            continue

        data = DEVICE_LIBRARY[device_key]
        daily_wh = data["watts"] * data["hours"] * data["duty"]

        devices.append(
            {
                "name": device_key,
                "voltage": data["voltage"],
                "watts": data["watts"],
                "hours": data["hours"],
                "duty": data["duty"],
                "daily_wh": daily_wh,
            }
        )

    return devices


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
    print("\nDevice\t\tType\tWatts\tHours\tDuty\tDaily Wh")
    print("-" * 65)

    for device in devices:
        print(
            f"{device['name']:<15}"
            f"{device['voltage']:<8}"
            f"{device['watts']:<8}"
            f"{device['hours']:<8}"
            f"{device['duty']:<8}"
            f"{device['daily_wh']:.0f}"
        )

    print("-" * 65)
    print(f"12V Total: {dc_total:.0f} Wh/day")
    print(f"AC Total: {ac_total:.0f} Wh/day")
    print(f"Overall Total: {overall_total:.0f} Wh/day")


def export_csv(devices, overall_total):
    """Save the device list and total to a CSV file."""
    with open(CSV_FILE, "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Device", "Voltage Type", "Watts", "Hours", "Duty Cycle", "Daily Wh"])

        for device in devices:
            writer.writerow(
                [
                    device["name"],
                    device["voltage"],
                    device["watts"],
                    device["hours"],
                    device["duty"],
                    device["daily_wh"],
                ]
            )

        writer.writerow([])
        writer.writerow(["Total", "", "", "", "", overall_total])

    print(f"Saved to {CSV_FILE}")


def main():
    user_input = input("Enter devices: ")
    device_names = parse_device_names(user_input)
    devices = build_device_rows(device_names)
    dc_total, ac_total, overall_total = calculate_totals(devices)

    print_report(devices, dc_total, ac_total, overall_total)
    export_csv(devices, overall_total)


if __name__ == "__main__":
    main()
