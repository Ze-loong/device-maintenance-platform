"""profile_segment 表：画像按维度拆分的分段（"历史事实"表）。
time_windows 字段是对表结构的追加字段，
供置信度规则程序判断用，不依赖解析自然语言 content。
"""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProfileSegment(Base):
    __tablename__ = "profile_segment"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id", ondelete="RESTRICT"), nullable=False, index=True)
    # 冗余 line_id，避免检索置信度分段时需要先 JOIN profile。
    line_id: Mapped[int] = mapped_column(ForeignKey("line.id", ondelete="RESTRICT"), nullable=False, index=True)
    # 五选一：运行时长规律/振动特征/启停冲击模式/温度趋势/异响/异常记录。
    dimension: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 仅"运行时长规律"/"振动特征"/"启停冲击模式"三个维度填充，"温度趋势"/"异响/异常记录"固定为 null。
    time_windows: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # 冗余 profile.profile_date，按"最近 N 天"过滤检索时不用再 JOIN profile。
    segment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
