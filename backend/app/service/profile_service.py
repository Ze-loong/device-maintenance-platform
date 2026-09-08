"""每日画像业务层：汇总事件、均匀抽样、调用模型并覆盖写入五维画像。"""
import logging
from datetime import date

from app.ai.llm_client import InferenceError
from app.ai.sanitized_context import SanitizedLineContext
from app.core.base_data import DIMENSIONS_WITHOUT_TIME_WINDOWS, get_profile_max_sample_events, normalize_location_code
from app.core.timeutil import to_beijing_hhmm
from app.core.db import session_scope
from app.repository.line_repository import LineRepository
from app.repository.event_repository import EventRepository
from app.repository.profile_repository import ProfileRepository
from app.repository.profile_segment_repository import ProfileSegmentRepository

logger = logging.getLogger("iot")


def sample_evenly(events: list, k: int) -> list:
    """从已按时间升序排列的事件中等间隔取样，覆盖全天。"""
    n = len(events)
    if n <= k:
        return events
    if k <= 1:
        return events[:1]
    indices = {round(i * (n - 1) / (k - 1)) for i in range(k)}
    return [events[i] for i in sorted(indices)]


class ProfileService:
    """生成单产线指定自然日的画像；模型失败时不留下半成品。"""

    def __init__(self, llm_client):
        self.llm_client = llm_client

    def generate_by_code(self, line_code: str, target_date: date, trigger: str = "manual"):
        """供 HTTP 单产线入口调用，返回 completed/failed/not_found 状态。"""
        with session_scope() as db:
            line = LineRepository(db).get_by_code(line_code)
            if line is None:
                return "not_found"
            result = self.generate_for_line(db, line, target_date, trigger)
            return "completed" if result is not None else "failed"

    def generate_all(self, target_date: date, trigger: str) -> dict:
        """逐产线独立事务执行，单产线异常只计失败，不影响其他产线。"""
        with session_scope() as db:
            line_ids = [line.id for line in LineRepository(db).list_active()]
        success = failed = 0
        for line_id in line_ids:
            try:
                with session_scope() as db:
                    line = LineRepository(db).get_by_id(line_id)
                    if line and self.generate_for_line(db, line, target_date, trigger):
                        success += 1
                    else:
                        failed += 1
            except Exception as exc:
                failed += 1
                logger.exception("单产线画像任务失败 产线ID=%s 原因=%s", line_id, type(exc).__name__)
        logger.info("全量画像任务完成 日期=%s 成功=%d 失败=%d", target_date, success, failed)
        return {"success": success, "failed": failed}

    def generate_for_line(self, db, line, target_date: date, trigger: str):
        events = EventRepository(db).list_by_line_and_date(line.id, target_date)
        sampled = sample_evenly(events, get_profile_max_sample_events())
        payload = [{"event_type": item.event_type, "location": item.location, "value": float(item.value), "occurred_at": to_beijing_hhmm(item.occurred_at)} for item in sampled]
        try:
            result = self.llm_client.generate_profile(SanitizedLineContext(line_code=line.line_code), payload)
        except InferenceError as exc:
            logger.warning("画像生成失败 产线=%s 日期=%s 原因=%s", line.line_code, target_date, exc)
            return None
        full_content = "\n\n".join(f"【{item.dimension}】\n{item.content}" for item in result.dimensions)
        # source_event_count 是真正送入模型的抽样条数，原始总数属于另一统计口径。
        profile = ProfileRepository(db).upsert(line_id=line.id, profile_date=target_date, summary=result.summary, full_content=full_content, source_event_count=len(sampled), generation_trigger=trigger)
        segments = []
        for item in result.dimensions:
            windows = None
            if item.dimension not in DIMENSIONS_WITHOUT_TIME_WINDOWS:
                windows = []
                for window in item.time_windows or []:
                    data = window.model_dump()
                    data["location"] = normalize_location_code(data["location"])
                    windows.append(data)
            segments.append({"profile_id": profile.id, "line_id": line.id, "dimension": item.dimension, "content": item.content, "time_windows": windows, "segment_date": target_date})
        ProfileSegmentRepository(db).bulk_create(segments)
        logger.info("画像生成完成 产线=%s 日期=%s 事件数=%d", line.line_code, target_date, len(sampled))
        return profile
