# utils/member_submissions.py
# -*- coding: utf-8 -*-
"""
Hilfsfunktionen für das Speichern/Laden von Member-Formular-Einreichungen.
Speicherformat: JSON-Liste von Datensätzen.
"""

from __future__ import annotations
import json
import os
from typing import Any, Dict, List
from datetime import datetime

SUBMISSIONS_PATH = os.path.join("utils", "member_submissions.json")


def _ensure_file() -> None:
    os.makedirs(os.path.dirname(SUBMISSIONS_PATH), exist_ok=True)
    if not os.path.exists(SUBMISSIONS_PATH):
        with open(SUBMISSIONS_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)


def load_submissions() -> List[Dict[str, Any]]:
    _ensure_file()
    try:
        with open(SUBMISSIONS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        return []


def save_submissions(items: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(SUBMISSIONS_PATH), exist_ok=True)
    with open(SUBMISSIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def add_submission(username: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fügt eine neue Einreichung hinzu.
    payload: die form-Felder als dict
    """
    items = load_submissions()
    entry = {
        "id": len(items) + 1,
        "username": username,
        "submitted_at": datetime.utcnow().isoformat() + "Z",
        "data": payload,
    }
    items.append(entry)
    save_submissions(items)
    return entry
