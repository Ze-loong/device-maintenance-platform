"""admin_user 表持久化。FR-01 登录本身列入 D4-D5，这里先建好查询方法供后续复用。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admin_user import AdminUser


class AdminUserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_username(self, username: str) -> AdminUser | None:
        stmt = select(AdminUser).where(AdminUser.username == username)
        return self.db.execute(stmt).scalar_one_or_none()
