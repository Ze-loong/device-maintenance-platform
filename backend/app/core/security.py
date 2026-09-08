"""管理员登录鉴权工具：密码哈希与会话令牌管理。
FR-01 采用最简方案——服务端内存字典存会话令牌，配合 httponly Cookie 下发，
不引入 Redis 或数据库 session 表（7 天冲刺、单管理员场景，后台进程重启需要重新登录，
这个代价可以接受，换来的是不用处理会话持久化与过期清理的额外复杂度）。
本模块只提供机制（哈希/校验/令牌生成与查找），不涉及 HTTP 层细节
（Cookie 读写在 core/deps.py 和 api/auth.py 里做），保持职责单一。
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext

logger = logging.getLogger("iot")

# bcrypt 是 admin_user 表设计里选定的哈希算法；passlib 封装了加盐、
# 迭代次数等细节，比手写 hashlib 更不容易在这些地方出安全性小纰漏。
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 会话 Cookie 名称，登录/登出/鉴权三处必须保持一致。
SESSION_COOKIE_NAME = "iot_admin_session"
# 会话有效期：单管理员开发/演示场景下，8 小时够覆盖一次完整工作/演示时段，
# 到期重新登录即可，不需要更复杂的刷新机制。
SESSION_TTL = timedelta(hours=8)

# 进程内会话存储：token -> {"username": str, "expires_at": datetime}。
# 这是最简方案的核心权衡点——后端进程一旦重启（含代码热更新触发的 reload），
# 全部会话立即失效，管理员需要重新登录。对于本项目"单管理员、7天冲刺、非高可用"
# 的场景，这个代价可以接受；如果未来需要多实例部署或持久化会话，这里是唯一需要
# 替换成外部存储（如 Redis）的位置，其余代码（deps.py 的 require_admin 等）不用改。
_SESSION_STORE: dict[str, dict] = {}


def hash_password(plain_password: str) -> str:
    """生成密码哈希，创建/重置管理员账号时调用，写入 admin_user.password_hash。"""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """校验明文密码与哈希是否匹配，登录时调用。"""
    return _pwd_context.verify(plain_password, password_hash)


def create_session(username: str) -> str:
    """登录成功后调用：生成一个不可猜测的随机令牌并记录过期时间，返回令牌字符串。
    调用方（api/auth.py 的登录路由）负责把这个字符串写进 httponly Cookie。"""
    token = secrets.token_urlsafe(32)
    _SESSION_STORE[token] = {
        "username": username,
        "expires_at": datetime.now(timezone.utc) + SESSION_TTL,
    }
    return token


def get_session_username(token: str | None) -> str | None:
    """校验令牌是否有效（存在且未过期），有效则返回对应用户名，否则返回 None。
    顺手清理过期令牌，避免字典无限增长——这不是应对高并发的正式过期清理机制，
    单账号场景下字典本身增长量很小，顺手做即可。"""
    if not token:
        return None
    record = _SESSION_STORE.get(token)
    if record is None:
        return None
    if record["expires_at"] < datetime.now(timezone.utc):
        _SESSION_STORE.pop(token, None)
        return None
    return record["username"]


def destroy_session(token: str | None) -> None:
    """登出时调用：移除令牌，之后同一个 Cookie 值不再被视为已登录。"""
    if token:
        _SESSION_STORE.pop(token, None)
