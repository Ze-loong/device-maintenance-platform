"""device 表：设备档案（"当前状态"表）。device_type 合法性由 config/base_data.yaml 校验，
不做数据库层枚举约束。
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Device(Base):
    __tablename__ = "device"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # ON DELETE RESTRICT：禁止硬删除有设备归属的产线，倒逼走软删除路径。
    line_id: Mapped[int] = mapped_column(ForeignKey("line.id", ondelete="RESTRICT"), nullable=False, index=True)
    device_type: Mapped[str] = mapped_column(String(64), nullable=False)
    location: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 对应 FR-13（应该级），字段先建，心跳更新逻辑列入 D6 可选实现，本期恒为默认值。
    online_status: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
