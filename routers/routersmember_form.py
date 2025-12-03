# routers/member_form.py
# -*- coding: utf-8 -*-
"""
APIRouter für:
- Member-Formular (nur für freigegebene eingeloggte Mitglieder): GET/POST /member/form
- Admin-Tabelle (nur Admin): GET /admin/member-data
"""

from __future__ import annotations
from fastapi import APIRouter, Request, Form, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Any, Dict, List, Optional

from utils.settings_manager import load_settings
from utils.member_submissions import add_submission, load_submissions

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


def _is_logged_in(request: Request) -> bool:
    return bool(request.session.get("logged_in"))


def _current_username(request: Request) -> Optional[str]:
    return request.session.get("username")


def _is_admin(request: Request, settings: Dict[str, Any]) -> bool:
    # Deine App hat bereits Admin-Logik (z. B. anhand Rollen/Session).
    # Wir nutzen hier dasselbe Session-Flag falls vorhanden, ansonsten Fallback über settings.
    if request.session.get("is_admin"):
        return True
    # Optionaler Fallback: Wenn username in settings["admin_users"]
    username = _current_username(request)
    admin_list = settings.get("admin_users", [])
    return username in admin_list


def _is_member_allowed(request: Request, settings: Dict[str, Any]) -> bool:
    """
    Nur bestimmte eingeloggte Member dürfen das Formular sehen/nutzen.
    Liste kommt aus settings["allowed_member_usernames"].
    """
    if not _is_logged_in(request):
        return False
    username = _current_username(request)
    allow_list = settings.get("allowed_member_usernames", [])
    return username in allow_list


@router.get("/member/form")
async def member_form_view(request: Request):
    settings = load_settings()
    if not _is_member_allowed(request, settings):
        # Nicht erlaubt -> zurück auf Login oder Dashboard
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    form_cfg = settings.get("member_form", {})
    title = form_cfg.get("title", "Eingabeformular")
    fields: List[Dict[str, Any]] = form_cfg.get("fields", [])

    return templates.TemplateResponse(
        "member_form.html",
        {
            "request": request,
            "title": title,
            "fields": fields,
            "settings": settings,
        },
    )


@router.post("/member/form")
async def member_form_submit(request: Request):
    settings = load_settings()
    if not _is_member_allowed(request, settings):
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    form_cfg = settings.get("member_form", {})
    fields: List[Dict[str, Any]] = form_cfg.get("fields", [])

    # Alle definierten Felder einsammeln
    form_data: Dict[str, Any] = {}
    form = await request.form()
    for field in fields:
        name = field.get("name")
        if not name:
            continue
        value = form.get(name)
        form_data[name] = value

    username = _current_username(request) or "unbekannt"
    add_submission(username=username, payload=form_data)

    # zurück zur Bestätigungsseite oder direkt auf dieselbe Seite
    return RedirectResponse(url="/member/form?success=1", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/admin/member-data")
async def admin_member_data(request: Request):
    settings = load_settings()
    if not _is_logged_in(request) or not _is_admin(request, settings):
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    form_cfg = settings.get("member_form", {})
    fields: List[Dict[str, Any]] = form_cfg.get("fields", [])
    submissions = load_submissions()

    # Spaltenüberschriften anhand der Feld-Labels bauen
    headers = [{"name": f.get("name"), "label": f.get("label", f.get("name", ""))} for f in fields]

    return templates.TemplateResponse(
        "admin_member_data.html",
        {
            "request": request,
            "headers": headers,
            "submissions": submissions,
            "settings": settings,
        },
    )
