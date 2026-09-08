"""prediction 与关联分段的持久化：写入推理结果，并为调试页反查完整依据。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.prediction import Prediction
from app.models.prediction_profile_segment import PredictionProfileSegment
from app.models.profile_segment import ProfileSegment


class PredictionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, event_id: str, line_id: int, line_code: str, source_event_id: int | None, next_behavior: str, confidence: str, reasoning: str, is_degraded: bool, hit_segment_ids: list[int]) -> Prediction:
        """写入一条预测记录，并同步写入命中画像分段的关联行（可能为空列表）。"""
        prediction = Prediction(event_id=event_id, line_id=line_id, line_code=line_code, source_event_id=source_event_id, next_behavior=next_behavior, confidence=confidence, reasoning=reasoning, is_degraded=is_degraded)
        self.db.add(prediction)
        self.db.flush()
        if hit_segment_ids:
            self.db.add_all([PredictionProfileSegment(prediction_id=prediction.id, profile_segment_id=segment_id) for segment_id in hit_segment_ids])
            self.db.flush()
        return prediction

    def get_by_event_id(self, event_id: str) -> tuple[Prediction | None, list[ProfileSegment]]:
        """按 MQTT 下行 event_id 返回预测及命中分段，供 FR-11 调试结果溯源。"""
        prediction = self.db.execute(
            select(Prediction).where(Prediction.event_id == event_id)
        ).scalar_one_or_none()
        if prediction is None:
            return None, []
        segments = list(
            self.db.execute(
                select(ProfileSegment)
                .join(PredictionProfileSegment, PredictionProfileSegment.profile_segment_id == ProfileSegment.id)
                .where(PredictionProfileSegment.prediction_id == prediction.id)
                .order_by(ProfileSegment.segment_date.desc(), ProfileSegment.id)
            ).scalars()
        )
        return prediction, segments
