"""FastAPI 依赖注入集中定义：数据库会话与管理员鉴权。
放在 core/ 是因为这是横切关注点，被 api/ 下几乎所有路由文件共用，不属于任何一个业务模块。
"""
from fastapi import Cookie, HTTPException, status

from app.core.db import session_scope
from app.core.security import SESSION_COOKIE_NAME, get_session_username


def get_db():
    """请求级数据库会话依赖：`db: Session = Depends(get_db)`。
    复用 core/db.py 已有的 session_scope（正常提交、异常回滚、用完关闭），
    包一层生成器函数是 FastAPI 依赖注入的写法，行为与 service 层用法完全一致。"""
    with session_scope() as db:
        yield db


def require_admin(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> str:
    """管理员鉴权依赖，用于 /api/* 下所有 JSON 接口：`Depends(require_admin)`。
    校验 Cookie 里的会话令牌是否有效，无效或缺失一律 401（对前端 fetch 调用是合适的响应方式）。
    返回值是当前登录用户名，路由函数需要的话可以直接用（比如日志里记录操作人）。
    /api/profiles/generate、/api/profiles/rebuild-all 两个接口同样需要这个依赖。"""
    username = get_session_username(session_token)
    if username is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或会话已过期，请重新登录")
    return username


def get_optional_admin(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> str | None:
    """用于渲染 Jinja2 页面的路由（api/pages.py）：不像 require_admin 那样直接抛异常，
    而是返回当前登录用户名或 None。页面路由拿到 None 时应自行返回
    `RedirectResponse("/login", status_code=303)`，而不是像 API 路由那样返回 401 JSON——
    浏览器直接访问页面地址时，一个 401 JSON 响应对用户不友好，重定向到登录页
    才是符合网页交互习惯的处理方式。这个区分是 FR-01 落地时的一个小工程判断，
    页面 vs API 两种 401 处理方式是其自然推论，统一遵循这条规则，不用每个页面路由重新决策。"""
    return get_session_username(session_token)
