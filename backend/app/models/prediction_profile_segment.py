"""prediction_profile_segment 表：预测-画像分段多对多关联表。
记录"这次预测命中了哪些具体画像分段"，支撑 FR-11 预测调试页面的溯源展示。
用级联删除而非 RESTRICT——这只是关系数据，不是事实数据本身。
"""
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PredictionProfileSegment(Base):
    __tablename__ = "prediction_profile_segment"

    prediction_id: Mapped[int] = mapped_column(ForeignKey("prediction.id", ondelete="CASCADE"), primary_key=True)
    profile_segment_id: Mapped[int] = mapped_column(ForeignKey("profile_segment.id", ondelete="CASCADE"), primary_key=True)
