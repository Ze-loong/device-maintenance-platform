"""Jinja2 页面控制器：登录页公开，其余页面统一检查管理员会话。"""
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.deps import get_optional_admin

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


@router.get("/")
def root():
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/login")
def login_page(request: Request, username: str | None = Depends(get_optional_admin)):
    if username:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html")


def _render(request: Request, username: str | None, template_name: str):
    """统一执行页面鉴权并向基础模板传入当前管理员名。"""
    if username is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request=request, name=template_name, context={"username": username})


@router.get("/dashboard")
def dashboard_page(request: Request, username: str | None = Depends(get_optional_admin)):
    return _render(request, username, "dashboard.html")


@router.get("/lines")
def lines_page(request: Request, username: str | None = Depends(get_optional_admin)):
    return _render(request, username, "lines.html")


@router.get("/devices")
def devices_page(request: Request, username: str | None = Depends(get_optional_admin)):
    return _render(request, username, "devices.html")


@router.get("/events")
def events_page(request: Request, username: str | None = Depends(get_optional_admin)):
    return _render(request, username, "events.html")


@router.get("/profiles")
def profiles_page(request: Request, username: str | None = Depends(get_optional_admin)):
    return _render(request, username, "profiles.html")


@router.get("/debug")
def debug_page(request: Request, username: str | None = Depends(get_optional_admin)):
    return _render(request, username, "debug.html")
