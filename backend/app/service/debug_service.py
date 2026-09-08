"""预测调试业务层：复用生产事件链路，并补充数据库中的内部诊断信息。"""
from app.core.db import session_scope
from app.repository.prediction_repository import PredictionRepository
from app.schemas.debug import DebugPredictionResponse, MatchedSegmentDetail


class DebugService:
    """将 REST 调试请求交给同一个 EventService，保证与 MQTT 入口处理一致。"""

    def __init__(self, event_service):
        self.event_service = event_service

    def predict(self, event) -> DebugPredictionResponse:
        prediction = self.event_service.handle_event(event)
        if prediction is None:
            return DebugPredictionResponse(is_duplicate=True)
        with session_scope() as db:
            row, segments = PredictionRepository(db).get_by_event_id(prediction.event_id)
            return DebugPredictionResponse(
                prediction=prediction,
                is_degraded=bool(row.is_degraded) if row else False,
                matched_segments=[
                    MatchedSegmentDetail(dimension=item.dimension, content=item.content, segment_date=item.segment_date.isoformat())
                    for item in segments
                ],
            )
