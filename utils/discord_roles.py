import json
import os
from discord import Guild

ROLES_CACHE_FILE = os.path.join(os.path.dirname(__file__), "roles_cache.json")


def get_cached_roles():
    try:
        if os.path.exists(ROLES_CACHE_FILE):
            with open(ROLES_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                else:
                    print("[Fehler] roles_cache.json ist kein Array.")
        else:
            print(f"[Warnung] Datei nicht gefunden: {ROLES_CACHE_FILE}")
    except Exception as e:
        print(f"[Fehler beim Laden der Rollen] {e}")
    return []


async def cache_roles(guild: Guild):
    try:
        roles = [{"id": role.id, "name": role.name} for role in guild.roles]
        with open(ROLES_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(roles, f, indent=4, ensure_ascii=False)
        print(f"[Info] {len(roles)} Rollen wurden erfolgreich im Cache gespeichert.")
    except Exception as e:
        print(f"[Fehler beim Cachen der Rollen] {e}")
