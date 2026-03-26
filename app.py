import re
import csv

DEVICE_LIBRARY = {
    "fridge": {"watts": 45, "hours": 24, "duty": 0.4, "voltage": "12v"},
    "laptop": {"watts": 60, "hours": 2, "duty": 1.0, "voltage": "ac"},
    "fan": {"watts": 20, "hours": 5, "duty": 0.7, "voltage": "12v"},
    "lights": {"watts": 10, "hours": 5, "duty": 1.0, "voltage": "12v"},
}

INVERTER_EFFICIENCY = 0.9

text = input("Enter devices: ")

items = re.findall(
    r".+?(?:12v|ac)\s+\d+(?:\.\d+)?\s*w(?:atts?)?\s+\d+(?:\.\d+)?\s*h(?:ours?)?(?:\s+\d+(?:\.\d+)?)?",
    text,
    re.IGNORECASE,
)

seen = set()
unique_items = []

for item in items:
    match = re.match(
        r"(.+?)\s+(12v|ac)\s+(\d+(?:\.\d+)?)\s*w(?:atts?)?\s+(\d+(?:\.\d+)?)\s*h(?:ours?)?(?:\s+(\d+(?:\.\d+)?))?$",
        item,
        re.IGNORECASE,
    )
    if not match:
        unique_items.append(item)
        continue

    name = match.group(1).strip().lower()
    voltage = match.group(2).lower()
    data = DEVICE_LIBRARY[item]

    if key not in seen:
        seen.add(key)
        unique_items.append(item)

items = unique_items

devices = []
total = 0

dc_total = 0
ac_total = 0

for item in items:
    match = re.match(
        r"(.+?)\s+(12v|ac)\s+(\d+(?:\.\d+)?)\s*w(?:atts?)?\s+(\d+(?:\.\d+)?)\s*h(?:ours?)?(?:\s+(\d+(?:\.\d+)?))?$",
        item,
        re.IGNORECASE,
    )

    if not match:
        print(f"Could not read: {item}")
        continue

    name = match.group(1).strip()
    voltage = match.group(2).lower()
    watts = float(match.group(3))
    hours = float(match.group(4))

    device_key = name.lower()

    if match.group(5):
        duty_cycle = float(match.group(5))
    else:
        duty_cycle = DEVICE_DEFAULTS.get(device_key, {}).get("duty_cycle", 1.0)

    daily = watts * hours * duty_cycle
    total += daily

    if voltage == "12v":
        dc_total += daily
    elif voltage == "ac":
        adjusted = daily / INVERTER_EFFICIENCY
        ac_total += adjusted
        total += (adjusted - daily)

    devices.append({
        "name": name,
        "voltage": voltage,
        "watts": watts,
        "hours": hours,
        "duty_cycle": duty_cycle,
        "daily_wh": daily
    })

print("\nDevice\t\tType\tWatts\tHours\tDuty\tDaily Wh")
print("-" * 65)

for device in devices:
    print(
        f"{device['name']:<15}"
        f"{device['voltage']:<8}"
        f"{device['watts']:<8}"
        f"{device['hours']:<8}"
        f"{device['duty_cycle']:<8}"
        f"{device['daily_wh']:.0f}"
    )

print("-" * 65)
print(f"12V Total: {dc_total:.0f} Wh/day")
print(f"AC Total: {ac_total:.0f} Wh/day")
print(f"Overall Total: {total:.0f} Wh/day")

with open("power_audit.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Device", "Voltage Type", "Watts", "Hours", "Duty Cycle", "Daily Wh"])

    for device in devices:
        writer.writerow([
            device["name"],
            device["voltage"],
            device["watts"],
            device["hours"],
            device["duty_cycle"],
            device["daily_wh"]
        ])

    writer.writerow([])
    writer.writerow(["Total", "", "", "", "", total])

print("Saved to power_audit.csv")