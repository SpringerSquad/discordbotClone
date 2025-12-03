import pytest
from fastapi.routing import APIRoute
from starlette.requests import Request
from fastapi import HTTPException, status

from main import app


def get_dependency(path: str, method: str = "GET"):
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            assert route.dependencies, f"{path} missing dependencies"
            return route.dependencies[0].dependency
    raise AssertionError(f"route {path} not found")


async def run_dependency(dep, role: str = None, logged_in: bool = True):
    session = {"logged_in": logged_in}
    if role:
        session["role"] = role
    scope = {"type": "http", "session": session}
    request = Request(scope)
    return await dep(request)


@pytest.mark.anyio
async def test_admin_dashboard_roles():
    dep = get_dependency("/admin/dashboard")
    await run_dependency(dep, "admin")
    with pytest.raises(HTTPException) as exc:
        await run_dependency(dep, "support")
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.anyio
async def test_admin_tickets_roles():
    dep = get_dependency("/admin/tickets")
    await run_dependency(dep, "admin")
    await run_dependency(dep, "support")
    with pytest.raises(HTTPException) as exc:
        await run_dependency(dep, "user")
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.anyio
async def test_account_requires_login_and_all_roles_allowed():
    dep = get_dependency("/account")
    for role in ["admin", "support", "user"]:
        await run_dependency(dep, role)
    with pytest.raises(HTTPException) as exc:
        await run_dependency(dep, logged_in=False)
    assert exc.value.status_code == status.HTTP_302_FOUND