# main.py
from fastapi import FastAPI, Request, Form, Depends, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_302_FOUND
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import bcrypt
from database import get_db, init_db
from models import User, RoleEnum, Document
from utils.auth import require_role, ROLE_ADMIN, ROLE_SUPPORT, ROLE_USER, is_logged_in, jinja_context_injector
import json
import uvicorn
import os
from datetime import datetime
from urllib.parse import urlparse
import hmac
import hashlib
import subprocess
import uuid

# 🔸 Abwesenheiten-Storage (falls genutzt)
try:
    from utils.absence_storage import list_absences, add_absence, delete_absence
except Exception:
    # optional – falls das Modul (noch) nicht existiert
    def list_absences(): return []
    def add_absence(**kwargs): return None
    def delete_absence(_): return False

# 🔸 Einladungs-Keys (für Registrierung)
from utils.invite_keys import (
    list_keys as list_invite_keys,
    create_key as create_invite_key,
    revoke_key as revoke_invite_key,
    validate_key as validate_invite_key,
    mark_used as mark_invite_used
)

app = FastAPI()
init_db()

# Router
from routers.member_form import router as member_form_router
app.include_router(member_form_router)

# Pfade / Templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "web", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "web", "static")
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")
ROLES_CACHE_PATH = os.path.join(BASE_DIR, "utils", "roles_cache.json")

# 🔸 Dokumenten-Verzeichnis
DOCS_DIR = os.path.join(BASE_DIR, "user_documents")
os.makedirs(DOCS_DIR, exist_ok=True)

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals['now'] = datetime.now
templates.env.globals.update(jinja_context_injector())


def _ensure_defaults(data: Dict[str, Any]) -> Dict[str, Any]:
    defaults = {
        "welcome_text": "Willkommen im Ticket! Beschreibe kurz dein Anliegen.",
        "ticket_categories": ["Support", "Technik"],
        "admin_roles": [],
        "support_roles": [],
        "absence_channel_id": ""
    }
    return {**defaults, **(data or {})}


def load_settings() -> Dict[str, Any]:
    if not os.path.exists(SETTINGS_PATH):
        return _ensure_defaults({})
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {}
    return _ensure_defaults(data)


def save_settings(settings: Dict[str, Any]) -> None:
    data = _ensure_defaults(settings)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_tickets():
    path = os.path.join(BASE_DIR, "tickets", "tickets.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


app.add_middleware(SessionMiddleware, secret_key="your_secret_key", same_site="lax")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

ALL_ROLES = [r.value for r in RoleEnum]


def _is_safe_path(u: str) -> bool:
    if not u:
        return False
    p = urlparse(u)
    return (p.scheme == "" and p.netloc == "" and u.startswith("/"))


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return RedirectResponse(url="/dashboard", status_code=HTTP_302_FOUND)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, "settings": load_settings()})


# -----------------------
# Login / Logout
# -----------------------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    username = (username or "").strip()
    password = (password or "").strip()
    if not username or not password:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Ungültige Zugangsdaten"})

    user = db.query(User).filter_by(username=username).first()
    if not user or not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Ungültige Zugangsdaten"})

    request.session["logged_in"] = True
    request.session["username"] = user.username
    request.session["role"] = user.role.value

    target = next.strip() if (next and _is_safe_path(next)) else "/dashboard"
    return RedirectResponse(url=target, status_code=HTTP_302_FOUND)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)


# -----------------------
# Registrierung (mit Key)
# -----------------------
@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if request.session.get("logged_in"):
        return RedirectResponse(url="/dashboard", status_code=HTTP_302_FOUND)
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register")
async def register_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    invite_key: str = Form(...),
    db: Session = Depends(get_db)
):
    username = (username or "").strip()
    if not username or not password or not confirm_password or not invite_key:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Bitte alle Felder ausfüllen."})
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Passwörter stimmen nicht überein."})

    # Key prüfen
    if not validate_invite_key(invite_key):
        return templates.TemplateResponse("register.html", {"request": request, "error": "Ungültiger oder bereits verwendeter Key."})

    # Username frei?
    if db.query(User).filter(User.username == username).first():
        return templates.TemplateResponse("register.html", {"request": request, "error": "Benutzername bereits vergeben."})

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user = User(username=username, password_hash=hashed, role=RoleEnum("user"), discord_id="")

    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse("register.html", {"request": request, "error": "Anlegen fehlgeschlagen (DB-Fehler)."})

    # Key verbrauchen
    mark_invite_used(invite_key, username)

    # Auto-Login
    request.session["logged_in"] = True
    request.session["username"] = user.username
    request.session["role"] = user.role.value
    return RedirectResponse(url="/dashboard", status_code=HTTP_302_FOUND)


# -----------------------
# Account (inkl. Dokumente)
# -----------------------
@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request, db: Session = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login?next=/account", status_code=HTTP_302_FOUND)

    username = request.session.get("username")
    user = db.query(User).filter_by(username=username).first()

    documents = []
    if user:
        documents = (
            db.query(Document)
            .filter_by(user_id=user.id)
            .order_by(Document.uploaded_at.desc())
            .all()
        )

    success = request.session.pop("success", None)
    error = request.session.pop("error", None)
    return templates.TemplateResponse("account.html", {
    "request": request,
    "success": success,
    "error": error,
    "documents": documents,
    "user": user,  # 🔥 WICHTIG: User dem Template übergeben
})



@app.post("/account", dependencies=[Depends(require_role(*ALL_ROLES))])
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    username = request.session.get("username")
    user = db.query(User).filter_by(username=username).first()
    if not user or not bcrypt.checkpw(current_password.encode(), user.password_hash.encode()):
        return templates.TemplateResponse("account.html", {"request": request, "error": "Aktuelles Passwort ist falsch."})
    if new_password != confirm_password:
        return templates.TemplateResponse("account.html", {"request": request, "error": "Die Passwörter stimmen nicht überein."})

    user.password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    db.commit()
    request.session["success"] = "Passwort erfolgreich geändert."
    return RedirectResponse(url="/account", status_code=HTTP_302_FOUND)


# 🔹 Dokument-Upload durch den Benutzer selbst
@app.post("/account/documents", dependencies=[Depends(require_role(*ALL_ROLES))])
async def upload_own_document(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not is_logged_in(request):
        return RedirectResponse(url="/login?next=/account", status_code=HTTP_302_FOUND)

    username = request.session.get("username")
    user = db.query(User).filter_by(username=username).first()
    if not user:
        raise HTTPException(status_code=403, detail="Benutzer nicht gefunden")

    if not file.filename:
        request.session["error"] = "Keine Datei ausgewählt."
        return RedirectResponse(url="/account", status_code=HTTP_302_FOUND)

    _, ext = os.path.splitext(file.filename)
    stored_name = f"{user.id}_{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(DOCS_DIR, stored_name)

    content = await file.read()
    with open(dest_path, "wb") as f:
        f.write(content)

    doc = Document(
        user_id=user.id,
        original_filename=file.filename,
        stored_filename=stored_name,
        content_type=file.content_type or "application/octet-stream",
        uploaded_by=username,
    )
    db.add(doc)
    db.commit()

    request.session["success"] = "Dokument erfolgreich hochgeladen."
    return RedirectResponse(url="/account", status_code=HTTP_302_FOUND)


# 🔹 Dokument löschen durch den Benutzer (nur eigene)
@app.post("/account/documents/{doc_id}/delete", dependencies=[Depends(require_role(*ALL_ROLES))])
async def delete_own_document(
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    if not is_logged_in(request):
        return RedirectResponse(url=f"/login?next=/account", status_code=HTTP_302_FOUND)

    username = request.session.get("username")
    current_user = db.query(User).filter_by(username=username).first()
    if not current_user:
        raise HTTPException(status_code=403, detail="Kein Zugriff")

    doc = db.query(Document).filter_by(id=doc_id).first()
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf dieses Dokument")

    file_path = os.path.join(DOCS_DIR, doc.stored_filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass

    db.delete(doc)
    db.commit()

    request.session["success"] = "Dokument wurde gelöscht."
    return RedirectResponse(url="/account", status_code=HTTP_302_FOUND)


# --- ADMIN-BEREICH ---
@app.get("/admin/dashboard", response_class=HTMLResponse, dependencies=[Depends(require_role(ROLE_ADMIN))])
async def admin_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, "settings": load_settings()})


@app.get("/admin/settings", response_class=HTMLResponse, dependencies=[Depends(require_role(ROLE_ADMIN, ROLE_SUPPORT))])
async def settings_page(request: Request):
    settings = load_settings()
    all_roles = []
    roles_path = ROLES_CACHE_PATH
    if os.path.exists(roles_path):
        with open(roles_path, "r", encoding="utf-8") as f:
            all_roles = json.load(f)
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": settings,
        "all_roles": all_roles
    })


@app.post("/admin/settings", dependencies=[Depends(require_role(ROLE_ADMIN, ROLE_SUPPORT))])
async def save_settings_form(
    request: Request,
    welcome_text: Optional[str] = Form(""),
    ticket_categories: Optional[List[str]] = Form(None),
    admin_roles: Optional[List[str]] = Form(None),
    support_roles: Optional[List[str]] = Form(None),
    absence_channel_id: Optional[str] = Form(None),
):
    current = load_settings()
    if not ticket_categories or all((c or "").strip() == "" for c in ticket_categories):
        ticket_categories = current.get("ticket_categories", [])
    else:
        ticket_categories = [c.strip() for c in ticket_categories if (c or "").strip()]

    admin_roles_int = [int(r) for r in admin_roles] if admin_roles else []
    support_roles_int = [int(r) for r in support_roles] if support_roles else []

    current.update({
        "welcome_text": welcome_text or "",
        "ticket_categories": ticket_categories,
        "admin_roles": admin_roles_int,
        "support_roles": support_roles_int,
        "absence_channel_id": (absence_channel_id or "").strip(),
    })

    save_settings(current)
    return RedirectResponse(url="/admin/settings", status_code=HTTP_302_FOUND)


@app.get("/admin/tickets", response_class=HTMLResponse, dependencies=[Depends(require_role(ROLE_ADMIN, ROLE_SUPPORT))])
async def ticket_page(request: Request):
    tickets = get_tickets()
    return templates.TemplateResponse("tickets.html", {
        "request": request,
        "tickets": tickets,
        "settings": load_settings()
    })


@app.get("/admin/training", response_class=HTMLResponse)
async def training_page(request: Request):
    tickets = get_tickets()
    return templates.TemplateResponse("training.html", {
        "request": request,
        "tickets": tickets,
        "settings": load_settings()
    })


# --- Abwesenheiten ---
@app.get("/admin/absences", response_class=HTMLResponse, dependencies=[Depends(require_role(ROLE_ADMIN, ROLE_SUPPORT, ROLE_USER))])
async def absences_page(request: Request):
    return templates.TemplateResponse("absences.html", {
        "request": request,
        "absences": list_absences(),
        "settings": load_settings()
    })


@app.post("/admin/absences", dependencies=[Depends(require_role(ROLE_ADMIN, ROLE_SUPPORT, ROLE_USER))])
async def absences_add(
    request: Request,
    user_display: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    reason: str = Form("")
):
    submitted_by = request.session.get("username", "Adminpanel")
    add_absence(user_display=user_display, start_date=start_date, end_date=end_date, reason=reason, submitted_by=submitted_by)
    return RedirectResponse(url="/admin/absences", status_code=HTTP_302_FOUND)


@app.post("/admin/absences/delete/{absence_id}", dependencies=[Depends(require_role(ROLE_ADMIN, ROLE_SUPPORT))])
async def absences_delete_route(absence_id: int):
    delete_absence(absence_id)
    return RedirectResponse(url="/admin/absences", status_code=HTTP_302_FOUND)


# ==========================
#      USER MANAGEMENT
# ==========================
@app.get("/admin/users", response_class=HTMLResponse, dependencies=[Depends(require_role(ROLE_ADMIN))])
async def list_users(request: Request, db: Session = Depends(get_db)):
    users = db.query(User).all()
    flash_success = request.session.pop("flash_success", None)
    flash_error = request.session.pop("flash_error", None)
    roles = [e.value for e in RoleEnum]
    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users,
        "roles": roles,
        "success": flash_success,
        "error": flash_error
    })


@app.post("/admin/users", dependencies=[Depends(require_role(ROLE_ADMIN))])
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    discord_id: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    username = (username or "").strip()
    if not username:
        request.session["flash_error"] = "Benutzername darf nicht leer sein."
        return RedirectResponse(url="/admin/users", status_code=HTTP_302_FOUND)

    if db.query(User).filter(User.username == username).first():
        request.session["flash_error"] = f"Benutzername '{username}' ist bereits vergeben."
        return RedirectResponse(url="/admin/users", status_code=HTTP_302_FOUND)

    valid_roles = [e.value for e in RoleEnum]
    if role not in valid_roles:
        request.session["flash_error"] = f"Ungültige Rolle: {role}. Erlaubt: {', '.join(valid_roles)}"
        return RedirectResponse(url="/admin/users", status_code=HTTP_302_FOUND)

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user = User(username=username, password_hash=hashed, discord_id=discord_id or "", role=RoleEnum(role))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        request.session["flash_error"] = "Anlegen fehlgeschlagen: UNIQUE-Verletzung."
        return RedirectResponse(url="/admin/users", status_code=HTTP_302_FOUND)

    request.session["flash_success"] = f"Benutzer '{username}' wurde angelegt."
    return RedirectResponse(url="/admin/users", status_code=HTTP_302_FOUND)


@app.get("/admin/users/edit/{user_id}", response_class=HTMLResponse, dependencies=[Depends(require_role(ROLE_ADMIN))])
async def edit_user_page(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session["flash_error"] = "Benutzer nicht gefunden."
        return RedirectResponse(url="/admin/users", status_code=HTTP_302_FOUND)
    roles = [e.value for e in RoleEnum]
    return templates.TemplateResponse("user_edit.html", {
        "request": request,
        "user": user,
        "roles": roles
    })


@app.post("/admin/users/edit/{user_id}", dependencies=[Depends(require_role(ROLE_ADMIN))])
async def edit_user(
    user_id: int,
    request: Request,
    username: str = Form(...),
    role: str = Form(...),
    discord_id: Optional[str] = Form(None),
    new_password: Optional[str] = Form(None),
    game_keys: Optional[str] = Form(""),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session["flash_error"] = "Benutzer nicht gefunden."
        return RedirectResponse(url="/admin/users", status_code=HTTP_302_FOUND)

    username = (username or "").strip()
    if not username:
        request.session["flash_error"] = "Benutzername darf nicht leer sein."
        return RedirectResponse(url=f"/admin/users/edit/{user_id}", status_code=HTTP_302_FOUND)

    if username != user.username and db.query(User).filter(User.username == username).first():
        request.session["flash_error"] = f"Benutzername '{username}' ist bereits vergeben."
        return RedirectResponse(url=f"/admin/users/edit/{user_id}", status_code=HTTP_302_FOUND)

    valid_roles = [e.value for e in RoleEnum]
    if role not in valid_roles:
        request.session["flash_error"] = f"Ungültige Rolle: {role}. Erlaubt: {', '.join(valid_roles)}"
        return RedirectResponse(url=f"/admin/users/edit/{user_id}", status_code=HTTP_302_FOUND)

    user.username = username
    user.role = RoleEnum(role)
    user.game_keys = (game_keys or "").strip()
    user.discord_id = (discord_id or "").strip()

    if new_password:
        user.password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        request.session["flash_error"] = "Änderung fehlgeschlagen (Datenbankfehler)."
        return RedirectResponse(url=f"/admin/users/edit/{user_id}", status_code=HTTP_302_FOUND)

    request.session["flash_success"] = f"Benutzer '{username}' wurde aktualisiert."
    return RedirectResponse(url="/admin/users", status_code=HTTP_302_FOUND)


@app.post("/admin/users/delete/{user_id}", dependencies=[Depends(require_role(ROLE_ADMIN))])
async def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    current_username = request.session.get("username")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session["flash_error"] = "Benutzer nicht gefunden."
        return RedirectResponse(url="/admin/users", status_code=HTTP_302_FOUND)

    if user.username == current_username:
        request.session["flash_error"] = "Du kannst dich nicht selbst löschen."
        return RedirectResponse(url="/admin/users", status_code=HTTP_302_FOUND)

    db.delete(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        request.session["flash_error"] = "Löschen fehlgeschlagen (Datenbankfehler)."
        return RedirectResponse(url="/admin/users", status_code=HTTP_302_FOUND)

    request.session["flash_success"] = f"Benutzer '{user.username}' wurde gelöscht."
    return RedirectResponse(url="/admin/users", status_code=HTTP_302_FOUND)


# -----------------------
# Admin: Invite-Keys
# -----------------------
@app.get("/admin/keys", response_class=HTMLResponse, dependencies=[Depends(require_role(ROLE_ADMIN, ROLE_SUPPORT))])
async def keys_page(request: Request):
    keys = list_invite_keys()
    return templates.TemplateResponse("keys.html", {"request": request, "keys": keys})


@app.post("/admin/keys/create", dependencies=[Depends(require_role(ROLE_ADMIN, ROLE_SUPPORT))])
async def keys_create(request: Request, note: str = Form("")):
    created_by = request.session.get("username", "system")
    create_invite_key(created_by=created_by, note=note)
    return RedirectResponse(url="/admin/keys", status_code=HTTP_302_FOUND)


@app.post("/admin/keys/revoke", dependencies=[Depends(require_role(ROLE_ADMIN, ROLE_SUPPORT))])
async def keys_revoke(request: Request, code: str = Form(...)):
    revoke_invite_key(code)
    return RedirectResponse(url="/admin/keys", status_code=HTTP_302_FOUND)


# -----------------------
# Admin: User-Dokumente
# -----------------------
@app.get("/admin/users/{user_id}/documents", response_class=HTMLResponse, dependencies=[Depends(require_role(ROLE_ADMIN))])
async def admin_user_documents(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User nicht gefunden")

    documents = (
        db.query(Document)
        .filter_by(user_id=user.id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )

    return templates.TemplateResponse("user_documents.html", {
        "request": request,
        "target_user": user,
        "documents": documents,
    })


# 🔹 Admin lädt Dokument für einen Benutzer hoch
@app.post("/admin/users/{user_id}/documents", dependencies=[Depends(require_role(ROLE_ADMIN))])
async def admin_upload_user_document(
    request: Request,
    user_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User nicht gefunden")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Keine Datei ausgewählt")

    _, ext = os.path.splitext(file.filename)
    stored_name = f"{user.id}_{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(DOCS_DIR, stored_name)

    content = await file.read()
    with open(dest_path, "wb") as f:
        f.write(content)

    doc = Document(
        user_id=user.id,
        original_filename=file.filename,
        stored_filename=stored_name,
        content_type=file.content_type or "application/octet-stream",
        uploaded_by=request.session.get("username", "system"),
    )
    db.add(doc)
    db.commit()

    return RedirectResponse(url=f"/admin/users/{user.id}/documents", status_code=HTTP_302_FOUND)


# 🔹 Admin löscht Dokument eines Benutzers
@app.post("/admin/users/{user_id}/documents/{doc_id}/delete", dependencies=[Depends(require_role(ROLE_ADMIN))])
async def admin_delete_user_document(
    user_id: int,
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User nicht gefunden")

    doc = db.query(Document).filter_by(id=doc_id, user_id=user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    file_path = os.path.join(DOCS_DIR, doc.stored_filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass

    db.delete(doc)
    db.commit()

    return RedirectResponse(url=f"/admin/users/{user.id}/documents", status_code=HTTP_302_FOUND)


# -----------------------
# Download: Nur Admin oder Besitzer
# -----------------------
@app.get("/documents/{doc_id}")
async def download_document(
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    if not is_logged_in(request):
        return RedirectResponse(url=f"/login?next=/documents/{doc_id}", status_code=HTTP_302_FOUND)

    doc = db.query(Document).filter_by(id=doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    current_username = request.session.get("username")
    current_user = db.query(User).filter_by(username=current_username).first()
    if not current_user:
        raise HTTPException(status_code=403, detail="Kein Zugriff")

    # Admin darf alles, sonst nur Besitzer
    if current_user.role != RoleEnum("admin") and current_user.id != doc.user_id:
        raise HTTPException(status_code=403, detail="Kein Zugriff")

    file_path = os.path.join(DOCS_DIR, doc.stored_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Datei nicht mehr vorhanden")

    return FileResponse(
        file_path,
        media_type=doc.content_type or "application/octet-stream",
        filename=doc.original_filename
    )


# --- GitHub-Webhook / Update ---
WEBHOOK_SECRET = b"supersecretwebhook"


def verify_signature(request_body: bytes, signature: str) -> bool:
    mac = hmac.new(WEBHOOK_SECRET, msg=request_body, digestmod=hashlib.sha256)
    expected = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/update")
async def update_code(request: Request):
    signature = request.headers.get("X-Hub-Signature-256")
    body = await request.body()
    if not signature or not verify_signature(body, signature):
        return {"status": "error", "message": "Invalid signature"}
    try:
        result = subprocess.run(
            ["cmd", "/c", "git fetch --all && git reset --hard origin/main && git submodule update --init --recursive"],
            cwd="C:/Users/Administrator/discord_bot",
            capture_output=True,
            text=True,
            timeout=20
        )
        return {"status": "success", "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "git pull timed out"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
