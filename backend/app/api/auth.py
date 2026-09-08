"""FR-01 登录控制器：校验管理员并用 httponly Cookie 管理进程内会话。"""
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response

from app.core import security
from app.core.deps import get_db
from app.repository.admin_user_repository import AdminUserRepository
from app.schemas.auth import LoginRequest, LoginResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response, db=Depends(get_db)):
    """校验用户名和 bcrypt 哈希，成功后下发只允许 HTTP 读取的会话 Cookie。"""
    user = AdminUserRepository(db).get_by_username(payload.username)
    if user is None or not security.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = security.create_session(user.username)
    response.set_cookie(
        security.SESSION_COOKIE_NAME,
        token,
        httponly=True,
        max_age=int(security.SESSION_TTL.total_seconds()),
        samesite="lax",
    )
    return LoginResponse(status="ok", username=user.username)


@router.post("/logout", status_code=204)
def logout(response: Response, token: str | None = Cookie(default=None, alias=security.SESSION_COOKIE_NAME)):
    """使当前令牌立即失效并清除浏览器 Cookie。"""
    security.destroy_session(token)
    response.delete_cookie(security.SESSION_COOKIE_NAME)
