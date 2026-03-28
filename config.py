import os


INVERTER_EFFICIENCY = 0.9
SOLAR_SYSTEM_EFFICIENCY = 0.86
DCDC_CHARGING_VOLTAGE = 14.4
DCDC_CHARGING_EFFICIENCY = 0.9
MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
DUTY_FRACTION_MAX = 1.0
DUTY_PERCENT_SCALE = 100.0
MIN_DEVICE_WATTS = 1.0
CSV_FILE = "power_audit.csv"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
OPENAI_FALLBACK_MODEL = "gpt-4.1-mini"
OPENAI_API_KEY_ENV_VAR = "OPENAI_API_KEY"
OPENAI_CLIENT_TIMEOUT_SECONDS = 20.0
MAX_AI_INPUT_FIELD_LENGTH = 4000
FRIDGE_DEFAULT_HOURS_PER_DAY = 24.0
FRIDGE_SUBTYPE_PROFILES = {
    "portable_chest_compressor": {
        "label": "portable chest compressor fridge",
        "watts": 45.0,
        "default_duty_fraction": 0.30,
        "min_duty_fraction": 0.20,
        "max_duty_fraction": 0.45,
    },
    "front_opening_compressor": {
        "label": "front-opening compressor fridge",
        "watts": 60.0,
        "default_duty_fraction": 0.35,
        "min_duty_fraction": 0.25,
        "max_duty_fraction": 0.50,
    },
    "upright_large_compressor": {
        "label": "upright/large compressor fridge",
        "watts": 80.0,
        "default_duty_fraction": 0.45,
        "min_duty_fraction": 0.30,
        "max_duty_fraction": 0.60,
    },
    "absorption_3_way": {
        "label": "3-way / absorption fridge",
        "watts": 120.0,
        "default_duty_fraction": 1.0,
        "min_duty_fraction": 1.0,
        "max_duty_fraction": 1.0,
    },
    "generic_compressor": {
        "label": "compressor fridge",
        "watts": 55.0,
        "default_duty_fraction": 0.35,
        "min_duty_fraction": 0.25,
        "max_duty_fraction": 0.50,
    },
}
INDUCTION_DEFAULT_WATTS = 1800.0
INDUCTION_MIN_HOURS_PER_DAY = 0.1
INDUCTION_MAX_HOURS_PER_DAY = 1.5


def get_openai_api_key():
    """Read the OpenAI API key from the environment at runtime."""
    return os.getenv(OPENAI_API_KEY_ENV_VAR)
