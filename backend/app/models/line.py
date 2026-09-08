"""line 表：产线档案（"当前状态"表）。
支持软删除；任何流向大模型的代码禁止直接使用本模型对象，
必须先转换成 app.ai.sanitized_context.SanitizedLineContext（脱敏红线）。
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Line(Base):
    __tablename__ = "line"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 业务编号，对应 MQTT 消息里的 line_id，如 L001。
    line_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
