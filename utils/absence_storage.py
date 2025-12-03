# utils/absence_storage.py
# -*- coding: utf-8 -*-

import os
import json
from datetime import datetime
from typing import Dict, List, Optional

DATA_DIR = "utils"
os.makedirs(DATA_DIR, exist_ok=True)
ABSENCE_FILE = os.path.join(DATA_DIR, "absences.json")


def _load() -> Dict:
    if not os.path.exists(ABSENCE_FILE):
        return {"last_id": 0, "items": []}
    with open(ABSENCE_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"last_id": 0, "items": []}


def _save(payload: Dict) -> None:
    with open(ABSENCE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def list_absences() -> List[Dict]:
    data = _load()
    # Sort: newest first by created_at
    return sorted(data["items"], key=lambda x: x.get("created_at", ""), reverse=True)


def add_absence(
    user_display: str,
    start_date: str,
    end_date: str,
    reason: str,
    submitted_by: Optional[str] = None,
) -> Dict:
    """
    Dates as ISO strings: 'YYYY-MM-DD' (UI liefert das so).
    """
    data = _load()
    new_id = int(data.get("last_id", 0)) + 1
    now = datetime.utcnow().isoformat()

    item = {
        "id": new_id,
        "user_display": user_display.strip(),
        "start_date": start_date.strip(),
        "end_date": end_date.strip(),
        "reason": reason.strip(),
        "submitted_by": (submitted_by or "").strip(),
        "created_at": now,
        "posted": False,          # noch nicht nach Discord gepostet
        "posted_at": None,        # ISO-Zeitstempel, wenn gepostet
        "message_id": None,       # optionale spätere Nutzung
        "channel_id": None        # optionale spätere Nutzung
    }

    data["last_id"] = new_id
    data["items"].append(item)
    _save(data)
    return item


def mark_posted(absence_id: int, channel_id: Optional[int] = None, message_id: Optional[int] = None) -> None:
    data = _load()
    changed = False
    for it in data["items"]:
        if int(it["id"]) == int(absence_id):
            it["posted"] = True
            it["posted_at"] = datetime.utcnow().isoformat()
            if channel_id is not None:
                it["channel_id"] = int(channel_id)
            if message_id is not None:
                it["message_id"] = int(message_id)
            changed = True
            break
    if changed:
        _save(data)


def delete_absence(absence_id: int) -> bool:
    data = _load()
    before = len(data["items"])
    data["items"] = [it for it in data["items"] if int(it.get("id", -1)) != int(absence_id)]
    after = len(data["items"])
    if after != before:
        _save(data)
        return True
    return False
