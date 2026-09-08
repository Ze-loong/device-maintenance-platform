"""unregistered_alert 表：未注册产线/设备告警。
line_id_raw/device_id_raw 不是外键——它们可能根本不存在于 line/device 表，
这张表存的是"拒绝了什么"，不是"关联到了什么"。管理端可视化本期不做，只保证结构化落库。
"""
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UnregisteredAlert(Base):
    __tablename__ = "unregistered_alert"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    line_id_raw: Mapped[str] = mapped_column(String(64), nullable=False)
    device_id_raw: Mapped[str] = mapped_column(String(64), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    # line_not_registered / device_not_registered / device_line_mismatch
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
