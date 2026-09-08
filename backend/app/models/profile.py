"""profile 表：每日画像（"历史事实"表）。(line_id, profile_date) 联合唯一，
生成/重新生成走 upsert。
"""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Profile(Base):
    __tablename__ = "profile"
    __table_args__ = (UniqueConstraint("line_id", "profile_date", name="uq_profile_line_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("line.id", ondelete="RESTRICT"), nullable=False, index=True)
    # 事件所属日期（"前一天"），不是本行生成时间——两者可能不是同一天（比如手动补生成很久以前的画像）。
    profile_date: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str | None] = mapped_column(String(200), nullable=True)
    full_content: Mapped[str] = mapped_column(Text, nullable=False)
    # 依据事件条数，FR-09 展示用；抽样后实际喂给大模型的条数，不是原始事件总数
    # （两者的区别在 profile_service 里用注释说明）。
    source_event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    # scheduled（定时任务）/ manual（手动触发）。
    generation_trigger: Mapped[str] = mapped_column(String(16), nullable=False)
