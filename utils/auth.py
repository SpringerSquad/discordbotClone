# utils/auth.py
# -*- coding: utf-8 -*-
"""
Zentrale RBAC-Helfer (Session-basiert).
Nicht eingeloggt -> 302 Redirect /login?next=...
Unzureichende Rolle -> 403.
"""

from __future__ import annotations
from typing import Optional, Callable
from fastapi import Request, HTTPException, status

ROLE_ADMIN   = "admin"
ROLE_SUPPORT = "support"
ROLE_USER    = "user"

def is_logged_in(request: Request) -> bool:
    return bool(request.session.get("logged_in")
                and request.session.get("username")
                and request.session.get("role"))

def get_user_role(request: Request) -> Optional[str]:
    return request.session.get("role") if is_logged_in(request) else None

def user_has_any_role(request: Request, *roles: str) -> bool:
    r = get_user_role(request)
    return (r in roles) if r else False

def require_role(*roles: str) -> Callable:
    async def checker(request: Request):
        if not is_logged_in(request):
            raise HTTPException(
                status_code=status.HTTP_302_FOUND,
                headers={"Location": f"/login?next={request.url.path}"},
            )
        if roles and not user_has_any_role(request, *roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return checker

# für Routen die nur Login brauchen (z.B. /account POST)
require_login = require_role(ROLE_ADMIN, ROLE_SUPPORT, ROLE_USER)

def jinja_context_injector():
    """
    In main.py via:
        templates.env.globals.update(jinja_context_injector())
    """
    return {
        "is_logged_in": lambda request: is_logged_in(request),
        "is_admin":     lambda request: user_has_any_role(request, ROLE_ADMIN),
        "is_support":   lambda request: user_has_any_role(request, ROLE_SUPPORT),
        "current_role": lambda request: get_user_role(request),
    }
