"""实时推理业务层：检索画像、调用模型、规则计算置信度并保存结果。"""
import logging
from datetime import time

from app.ai.llm_client import InferenceError
from app.ai.sanitized_context import SanitizedLineContext
from app.core.base_data import get_confidence_lookback_days, get_confidence_time_tolerance_minutes, get_dimensions_for_event
from app.core.timeutil import is_beijing_weekend, to_beijing
from app.repository.prediction_repository import PredictionRepository
from app.repository.profile_segment_repository import ProfileSegmentRepository
from app.schemas.mqtt import DownlinkPrediction, UplinkEvent

logger = logging.getLogger("iot")
INFERENCE_FALLBACK = "暂无法判断，建议保持正常观察"
INFERENCE_FALLBACK_REASON = "本次预测服务处理异常，已启用兜底提示，具体原因已记录在后台日志。"


def _minutes(value: str) -> int:
    parsed = time.fromisoformat(value)
    return parsed.hour * 60 + parsed.minute


def _time_matches(now_minute: int, start: int, end: int, tolerance: int) -> bool:
    """支持常规窗口、跨午夜窗口以及容差跨午夜的分钟比较。"""
    if end < start:
        end += 1440
    start -= tolerance
    end += tolerance
    return any(start <= now_minute + shift <= end for shift in (-1440, 0, 1440))


# 振动/温度超限事件命中的维度（振动特征/温度趋势）设计上不携带 time_windows，
# 常规"时间窗口命中"判断对它们永远无法成立；超限事件本身信号强度已经足够，
# 不需要作息规律佐证，因此单独放宽为"命中天数达标即可 high"。
ALERT_EVENT_TYPES = {"vibration_alert", "temperature_alert"}


def calculate_confidence(segments: list, event: UplinkEvent) -> str:
    """按命中画像天数和北京时间窗口计算 low/medium/high；
    告警类事件（振动/温度超限）不要求时间窗口匹配，命中天数达标直接 high。"""
    days = {segment.segment_date for segment in segments}
    if not days:
        return "low"
    if len(days) < 3:
        return "medium"
    if event.event_type in ALERT_EVENT_TYPES:
        return "high"
    day_type = "weekend" if is_beijing_weekend(event.occurred_at) else "weekday"
    local_time = to_beijing(event.occurred_at)
    now_minute = local_time.hour * 60 + local_time.minute
    tolerance = get_confidence_time_tolerance_minutes()
    for segment in segments:
        for window in segment.time_windows or []:
            if window.get("location") not in (None, event.location) or window.get("day_type") not in ("all", day_type):
                continue
            try:
                if _time_matches(now_minute, _minutes(window["start"]), _minutes(window["end"]), tolerance):
                    return "high"
            except (KeyError, TypeError, ValueError):
                logger.warning("画像时间窗口格式异常，已跳过 分段=%s", segment.id)
    return "medium"


class InferenceService:
    """封装实时推理的正常路径和安全降级路径。"""

    def __init__(self, llm_client):
        self.llm_client = llm_client

    def infer(self, db, line, device, event: UplinkEvent, source_event_id: int) -> DownlinkPrediction:
        dimensions = get_dimensions_for_event(event.location, event.event_type)
        segments = ProfileSegmentRepository(db).find_recent_by_dimensions(line.id, dimensions, get_confidence_lookback_days(), as_of=to_beijing(event.occurred_at).date())
        matched = [{"dimension": item.dimension, "content": item.content} for item in segments]
        degraded = False
        try:
            result = self.llm_client.infer(SanitizedLineContext(line_code=line.line_code), event, matched)
            behavior, reasoning, profile_refs = result.next_behavior, result.reasoning, result.profile_refs
            confidence = calculate_confidence(segments, event)
        except InferenceError as exc:
            logger.warning("实时推理失败，已启用降级：%s", exc)
            behavior, reasoning = INFERENCE_FALLBACK, INFERENCE_FALLBACK_REASON
            profile_refs = [f"{item.dimension}：{item.content[:80]}" for item in segments]
            confidence, degraded = "low", True
        prediction = DownlinkPrediction(line_id=line.line_code, next_behavior=behavior, confidence=confidence, reasoning=reasoning, profile_refs=profile_refs)
        PredictionRepository(db).create(event_id=prediction.event_id, line_id=line.id, line_code=line.line_code, source_event_id=source_event_id, next_behavior=behavior, confidence=confidence, reasoning=reasoning, is_degraded=degraded, hit_segment_ids=[item.id for item in segments])
        return prediction
