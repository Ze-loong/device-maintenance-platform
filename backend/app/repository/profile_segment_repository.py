"""profile_segment 表持久化：按维度写入分段，并支持置信度算法所需的"最近 N 天"检索。"""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.profile_segment import ProfileSegment


class ProfileSegmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def bulk_create(self, segments: list[dict]) -> list[ProfileSegment]:
        """批量写入一份画像的全部维度分段（通常一次 5 条）。"""
        rows = [ProfileSegment(**s) for s in segments]
        self.db.add_all(rows)
        self.db.flush()
        return rows

    def find_recent_by_dimensions(self, line_id: int, dimensions: list[str], lookback_days: int, as_of: date) -> list[ProfileSegment]:
        """查某产线在 [as_of - lookback_days, as_of] 窗口内、指定维度列表的全部分段。
        命中的天数（distinct segment_date）
        由调用方（inference_service 的置信度算法）自己统计，这里只负责把候选集合取出来。
        """
        start = as_of - timedelta(days=lookback_days)
        stmt = select(ProfileSegment).where(
            ProfileSegment.line_id == line_id,
            ProfileSegment.dimension.in_(dimensions),
            ProfileSegment.segment_date >= start,
            ProfileSegment.segment_date <= as_of,
        ).order_by(ProfileSegment.segment_date.desc())
        return list(self.db.execute(stmt).scalars())
