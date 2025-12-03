import json
import os

SETTINGS_FILE = "settings.json"

def load_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {
            "welcome_text": "Willkommen beim Support!",
            "ticket_categories": [],
            "admin_roles": [],
            "support_roles": []
        }

    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_settings(data: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
