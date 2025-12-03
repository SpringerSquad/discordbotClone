# utils/invite_keys.py
# -*- coding: utf-8 -*-

import os
import json
import secrets
from datetime import datetime
from typing import Dict, List, Optional

DATA_DIR = "utils"
os.makedirs(DATA_DIR, exist_ok=True)
INVITE_FILE = os.path.join(DATA_DIR, "invite_keys.json")


def _load() -> Dict:
    if not os.path.exists(INVITE_FILE):
        return {"items": []}
    with open(INVITE_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"items": []}


def _save(data: Dict) -> None:
    with open(INVITE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _new_code(n: int = 20) -> str:
    # gut lesbarer, kryptografisch starker Code
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # ohne 0,O,1,I
    return "".join(secrets.choice(alphabet) for _ in range(n))


def list_keys() -> List[Dict]:
    data = _load()
    # neueste zuerst
    return sorted(data["items"], key=lambda x: x.get("created_at", ""), reverse=True)


def create_key(created_by: str, note: str = "", code: Optional[str] = None) -> Dict:
    data = _load()
    code = code or _new_code()
    item = {
        "code": code,
        "created_by": created_by,
        "created_at": datetime.utcnow().isoformat(),
        "note": note.strip(),
        "used": False,
        "used_by": None,
        "used_at": None,
        "revoked": False,
    }
    data["items"].append(item)
    _save(data)
    return item


def revoke_key(code: str) -> bool:
    data = _load()
    changed = False
    for it in data["items"]:
        if it["code"] == code and not it.get("used"):
            it["revoked"] = True
            changed = True
            break
    if changed:
        _save(data)
    return changed


def validate_key(code: str) -> bool:
    code = (code or "").strip()
    if not code:
        return False
    data = _load()
    for it in data["items"]:
        if it["code"] == code and not it.get("used") and not it.get("revoked"):
            return True
    return False


def mark_used(code: str, username: str) -> bool:
    data = _load()
    for it in data["items"]:
        if it["code"] == code and not it.get("used") and not it.get("revoked"):
            it["used"] = True
            it["used_by"] = username
            it["used_at"] = datetime.utcnow().isoformat()
            _save(data)
            return True
    return False
