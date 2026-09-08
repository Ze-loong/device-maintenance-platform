"""初始化或重置管理员账号；密码只从参数/环境/隐藏输入读取，绝不回显。"""
import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.db import init_engine, session_scope  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.admin_user import AdminUser  # noqa: E402


def main() -> None:
    """按用户名幂等创建账号；已存在时只更新密码哈希。"""
    parser = argparse.ArgumentParser(description="创建或重置管理端账号")
    parser.add_argument("--username", default=os.getenv("IOT_ADMIN_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("IOT_ADMIN_PASSWORD"))
    args = parser.parse_args()
    password = args.password or getpass.getpass("请输入管理员密码: ")
    if not password:
        raise SystemExit("密码不能为空")

    settings = Settings()
    init_engine(settings.database_url.get_secret_value())
    with session_scope() as db:
        user = db.execute(select(AdminUser).where(AdminUser.username == args.username)).scalar_one_or_none()
        if user is None:
            db.add(AdminUser(username=args.username, password_hash=hash_password(password)))
            action = "创建"
        else:
            user.password_hash = hash_password(password)
            action = "重置"
    print(f"管理员账号已{action}: {args.username}")


if __name__ == "__main__":
    main()
