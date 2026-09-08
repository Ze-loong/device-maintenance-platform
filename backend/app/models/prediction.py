"""prediction 表：每次实时推理的结果记录（"历史事实"表）。
source_event_id 可空——极端情况下（事件入库失败但仍需吐出兜底结果）允许没有关联的原始事件，
优先保证"任何时候都有响应"这条红线。
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Prediction(Base):
    __tablename__ = "prediction"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 对应下行载荷 event_id，平台为本次预测生成的 UUID 字符串。
    event_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("line.id", ondelete="RESTRICT"), nullable=False, index=True)
    line_code: Mapped[str] = mapped_column(String(64), nullable=False)
    # 触发本次预测的原始事件；可空，见上方 docstring。
    source_event_id: Mapped[int | None] = mapped_column(ForeignKey("event.id", ondelete="RESTRICT"), nullable=True)
    next_behavior: Mapped[str] = mapped_column(String(200), nullable=False)
    # low / medium / high，规则计算得出，非模型自评。
    confidence: Mapped[str] = mapped_column(String(8), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    # 是否为降级兜底结果，便于统计降级频率、故障演练验收取证。
    is_degraded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
