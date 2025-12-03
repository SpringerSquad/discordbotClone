# routers/member_form.py
# -*- coding: utf-8 -*-

from __future__ import annotations
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette import status
from utils.auth import require_role, require_login, ROLE_ADMIN, ROLE_SUPPORT, ROLE_USER
import os, json
from datetime import datetime

router = APIRouter()
ALL_ROLES = ["admin", "support", "user"]
templates = Jinja2Templates(directory="web/templates")
from datetime import datetime as _dt
templates.env.globals['now'] = _dt.now  # Footer

# Speicherorte
UTILS_DIR = "utils"
os.makedirs(UTILS_DIR, exist_ok=True)
DATA_FILE    = os.path.join(UTILS_DIR, "member_submissions.json")
HEADERS_FILE = os.path.join(UTILS_DIR, "member_headers.json")
PLAYERS_FILE = os.path.join(UTILS_DIR, "players.json")

# ------- Helpers -------
def _load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_headers():
    return _load_json(HEADERS_FILE, [])

def load_players() -> list[str]:
    # Liste der erlaubten Spielernamen
    return _load_json(PLAYERS_FILE, [])

def load_submissions():
    return _load_json(DATA_FILE, [])

def add_submission(entry: dict) -> None:
    items = load_submissions()
    entry["id"] = len(items) + 1
    items.append(entry)
    _save_json(DATA_FILE, items)

def _to_float(v):
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "", "null") else None
    except Exception:
        return None

# ------- Routes (BEIDE Pfade) -------

@router.get("/member-form", dependencies=[Depends(require_role(*ALL_ROLES))])
@router.get("/member/form", dependencies=[Depends(require_role(*ALL_ROLES))])
# Roles allowed: admin, support, user
async def show_member_form(request: Request):
    headers = load_headers()
    players = load_players()
    return templates.TemplateResponse(
        "member_form.html",
        {"request": request, "headers": headers, "players": players},
    )


@router.get("/member/avg7", dependencies=[Depends(require_role(*ALL_ROLES))])
async def get_avg7(request: Request):
    spieler = (request.query_params.get("spielername") or "").strip()
    if not spieler:
        return {"ok": False, "avg7": None, "count": 0}

    subs = load_submissions()
    # nur Einträge dieses Spielers
    player_subs = [s for s in subs if s.get("username") == spieler]

    # nach Zeit sortieren
    def _parse_ts(x):
        try:
            return datetime.fromisoformat((x or "").replace("Z",""))
        except Exception:
            return datetime.min

    player_subs.sort(key=lambda s: _parse_ts(s.get("submitted_at","")))
    # die letzten 7 Gesamt‑AVG Werte (falls vorhanden)
    values = []
    for s in player_subs[-7:]:
        v = _to_float(s.get("data", {}).get("gesamt_avg"))
        if v is not None:
            values.append(v)

    if len(values) == 7:
        avg = round(sum(values) / 7.0, 1)
        return {"ok": True, "avg7": avg, "count": 7}
    else:
        return {"ok": True, "avg7": None, "count": len(values)}

@router.post("/member-form", dependencies=[Depends(require_role(*ALL_ROLES))])
@router.post("/member/form", dependencies=[Depends(require_role(*ALL_ROLES))])
# Roles allowed: admin, support, user
async def submit_member_form(request: Request):

    form = await request.form()
    headers = load_headers()

    # Spielername aus Formular (Dropdown) oder Fallback auf Session
    spielername = (form.get("spielername") or request.session.get("username") or "").strip()

    # Einzelwerte sammeln (Checkbox -> "1"/"0"; 7T-Durchschnitt NICHT aus dem Formular übernehmen)
    payload = {}
    for h in headers:
        name = h.get("name")
        if not name:
            continue
        if name == "sieben_tage_durchschnitt":
            continue  # wird unten berechnet
        if name == "gesamt_avg":
            continue  # wird clientseitig berechnet; wir berechnen notfalls serverseitig nach
        val = form.get(name)
        if (h.get("type") == "checkbox"):
            val = "1" if val is not None else "0"
        payload[name] = val

    # Gesamt AVG (fallback-berechnung falls leer)
    if not form.get("gesamt_avg"):
        parts = [
            _to_float(form.get("avg_zielgenauigkeit")),
            _to_float(form.get("avg_map_kenntnis")),
            _to_float(form.get("avg_teamplay")),
            _to_float(form.get("avg_kommunikation")),
            _to_float(form.get("avg_reaktionszeit")),
        ]
        if all(v is not None for v in parts):
            gesamt = round(sum(parts) / len(parts), 1)
            payload["gesamt_avg"] = str(gesamt)
    else:
        payload["gesamt_avg"] = str(_to_float(form.get("gesamt_avg")) or "")

    # 7-Tage-Durchschnitt berechnen (aktueller Eintrag + letzte 6 dieses Spielers)
    subs = load_submissions()
    # nur Einträge dieses Spielers
    subs_player = [s for s in subs if s.get("username") == spielername]
    # nach Datum sortieren (älteste -> neueste)
    def _parse_ts(x):
        try:
            return datetime.fromisoformat(x.replace("Z",""))
        except Exception:
            return datetime.min
    subs_player.sort(key=lambda s: _parse_ts(s.get("submitted_at","")))
    # letzte 6 gesamt_avg holen
    last6 = []
    for s in subs_player[-6:]:
        v = _to_float(s.get("data", {}).get("gesamt_avg"))
        if v is not None:
            last6.append(v)
    # aktuellen gesamt_avg
    cur_total = _to_float(payload.get("gesamt_avg"))
    seven_avg = None
    if cur_total is not None:
        values = last6 + [cur_total]
        if len(values) >= 7:
            seven_avg = round(sum(values) / 7.0, 1)

    if seven_avg is not None:
        payload["sieben_tage_durchschnitt"] = str(seven_avg)
    else:
        payload["sieben_tage_durchschnitt"] = ""  # noch nicht verfügbar

    # Submission speichern
    entry = {
        "username": spielername or "unbekannt",
        "submitted_at": datetime.utcnow().isoformat() + "Z",
        "data": payload,
    }
    add_submission(entry)

    players = load_players()
    return templates.TemplateResponse(
    "member_form.html",
    {
        "request": request,
        "headers": load_headers(),
        "players": players,
        "success": True
    },
)
@router.get("/admin/menu", dependencies=[Depends(require_role(ROLE_ADMIN))])
# Roles allowed: admin
async def admin_menu(request: Request):
    headers = load_headers()
    submissions = load_submissions()
    return templates.TemplateResponse(
        "admin_menu.html",
        {"request": request, "headers": headers, "submissions": submissions},
    )

@router.get("/support/menu", dependencies=[Depends(require_role(ROLE_ADMIN, ROLE_SUPPORT))])
# Roles allowed: admin, support
async def support_menu(request: Request):
    headers = load_headers()
    submissions = load_submissions()
    return templates.TemplateResponse(
        "support_menu.html",
        {"request": request, "headers": headers, "submissions": submissions},
    )

@router.get("/admin/member-data", dependencies=[Depends(require_role(ROLE_ADMIN))])
async def admin_member_data(request: Request):
    
    headers = load_headers()
    submissions = load_submissions()
    return templates.TemplateResponse(
        "admin_member_data.html",
        {"request": request, "headers": headers, "submissions": submissions},

    )