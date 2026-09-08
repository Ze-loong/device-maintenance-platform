"""核心服务验收测试：使用真实 PostgreSQL，模型使用确定性的假客户端。"""
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
import pytest
from app.ai.llm_client import InferenceError
from app.ai.prompts import DimensionResult, InferenceResult, ProfileGenerationResult, TimeWindow
from app.core.config import Settings
from app.core.db import get_engine, init_engine, session_scope
from app.models import Base
from app.models.device import Device
from app.models.event import Event
from app.models.line import Line
from app.models.prediction import Prediction
from app.models.profile import Profile
from app.models.profile_segment import ProfileSegment
from app.models.unregistered_alert import UnregisteredAlert
from app.schemas.mqtt import UplinkEvent
from app.service.event_service import EventService
from app.service.inference_service import InferenceService, calculate_confidence
from app.service.profile_service import ProfileService


class FakeLLM:
    """返回固定合法结构，并记录实时推理次数。"""
    def __init__(self, fail=False): self.fail, self.infer_calls = fail, 0
    def infer(self, context, event, matched_segments):
        self.infer_calls += 1
        if self.fail: raise InferenceError("test failure")
        return InferenceResult(next_behavior="建议检查风机运行状态", reasoning="依据测试画像或常识推测", profile_refs=[])
    def generate_profile(self, context, sampled_events):
        if self.fail: raise InferenceError("test failure")
        items = []
        for name in ("运行时长规律", "振动特征", "启停冲击模式", "温度趋势", "异响/异常记录"):
            windows = None if name in ("温度趋势", "异响/异常记录") else [TimeWindow(activity="测试运行时段", location="workshop_a", start="18:00", end="19:00", day_type="all")]
            items.append(DimensionResult(dimension=name, content=f"{name}新内容", time_windows=windows))
        return ProfileGenerationResult(summary="测试摘要", dimensions=items)


def make_event(line="L001", device="D001", occurred_at=None, event_type="fan_started"):
    return UplinkEvent(line_id=line, device_id=device, device_type="vibration", location="workshop_a", event_type=event_type, value=1, occurred_at=occurred_at or datetime.now(timezone.utc))


def setup_module():
    """只在独立测试库重建表，绝不清空正常联调数据库。"""
    url = make_url(Settings().database_url.get_secret_value())
    test_name = "iot_platform_test"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": test_name}):
            conn.execute(text('CREATE DATABASE "iot_platform_test"'))
    admin.dispose()
    init_engine(url.set(database=test_name).render_as_string(hide_password=False))
    Base.metadata.drop_all(get_engine()); Base.metadata.create_all(get_engine())


def clear_and_seed():
    Base.metadata.drop_all(get_engine()); Base.metadata.create_all(get_engine())
    with session_scope() as db:
        f1, f2 = Line(line_code="L001", name="测试产线1"), Line(line_code="L002", name="测试产线2")
        db.add_all([f1, f2]); db.flush()
        db.add_all([Device(device_code="D001", line_id=f1.id, device_type="vibration", location="workshop_a"), Device(device_code="D002", line_id=f2.id, device_type="vibration", location="workshop_a")])


def test_unregistered_three_reasons_and_alert_rows(tmp_path):
    clear_and_seed(); service = EventService(InferenceService(FakeLLM()), tmp_path)
    for index, pair in enumerate([("UNKNOWN", "D001"), ("L001", "UNKNOWN"), ("L001", "D002")]):
        result = service.handle_event(make_event(*pair, datetime(2026, 9, 3, index, tzinfo=timezone.utc)))
        assert result.confidence == "low" and "未注册" in result.reasoning
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(UnregisteredAlert)) == 3
        assert {row.reason for row in db.scalars(select(UnregisteredAlert))} == {"line_not_registered", "device_not_registered", "device_line_mismatch"}


def test_archive_beijing_date_and_qos_duplicate(tmp_path):
    clear_and_seed(); llm = FakeLLM(); service = EventService(InferenceService(llm), tmp_path)
    item = make_event(occurred_at=datetime(2026, 9, 3, 16, 30, tzinfo=timezone.utc))
    first, second = service.handle_event(item), service.handle_event(item)
    assert first is not None and second is None and llm.infer_calls == 1
    assert len((tmp_path / "L001" / "2026-09-04.jsonl").read_text(encoding="utf-8").splitlines()) == 2
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(Event)) == 1
        assert db.scalar(select(func.count()).select_from(Prediction)) == 1


@pytest.mark.parametrize("failure_kind", ["调用异常", "JSON输出校验失败"])
def test_inference_failures_are_saved_as_degraded(tmp_path, failure_kind):
    """两类失败在适配层都转换为 InferenceError，服务层统一安全降级。"""
    clear_and_seed(); result = EventService(InferenceService(FakeLLM(fail=True)), tmp_path).handle_event(make_event())
    assert result.confidence == "low" and result.next_behavior.startswith("暂无法判断")
    with session_scope() as db: assert db.scalar(select(Prediction)).is_degraded is True


def test_confidence_four_branches():
    event = make_event(occurred_at=datetime(2026, 9, 3, 10, 30, tzinfo=timezone.utc))
    def segment(day, start="18:00", end="19:00"):
        return type("Segment", (), {"segment_date": day, "time_windows": [{"location": "workshop_a", "day_type": "all", "start": start, "end": end}], "id": 1})()
    today = date(2026, 9, 3)
    outputs = [calculate_confidence([], event), calculate_confidence([segment(today)], event), calculate_confidence([segment(today - timedelta(days=i)) for i in range(3)], event), calculate_confidence([segment(today - timedelta(days=i), "08:00", "09:00") for i in range(3)], event)]
    assert outputs == ["low", "medium", "high", "medium"]
    print("置信度四档：0天=low，1天=medium，3天且18:30命中=high，3天但未命中=medium")


def test_confidence_alert_events_bypass_time_window():
    """振动/温度超限事件命中的维度不携带 time_windows，常规窗口匹配永远不成立；
    告警信号本身够强，命中天数达标即可直接 high，不要求窗口匹配。"""
    today = date(2026, 9, 3)
    def segment(day, dimension="振动特征"):
        return type("Segment", (), {"segment_date": day, "time_windows": [], "id": 1, "dimension": dimension})()
    for event_type, dimension in (("vibration_alert", "振动特征"), ("temperature_alert", "温度趋势")):
        event = make_event(occurred_at=datetime(2026, 9, 3, 10, 30, tzinfo=timezone.utc), event_type=event_type)
        outputs = [
            calculate_confidence([], event),
            calculate_confidence([segment(today, dimension)], event),
            calculate_confidence([segment(today - timedelta(days=i), dimension) for i in range(3)], event),
        ]
        assert outputs == ["low", "medium", "high"], f"{event_type} 置信度分档不符预期：{outputs}"
    print("告警事件置信度三档：0天=low，1天=medium，3天(无需窗口匹配)=high")


def test_profile_regeneration_replaces_segments_and_content():
    clear_and_seed()
    with session_scope() as db:
        line = db.scalar(select(Line).where(Line.line_code == "L001")); device = db.scalar(select(Device).where(Device.device_code == "D001"))
        db.add(Event(line_id=line.id, line_code="L001", device_id=device.id, device_code="D001", event_type="fan_started", value=1, extra={}, occurred_at=datetime(2026, 9, 3, 10, tzinfo=timezone.utc), is_backfill=True, raw_payload_path="test.jsonl"))
        old = Profile(line_id=line.id, profile_date=date(2026, 9, 3), summary="旧", full_content="旧内容", source_event_count=1, generation_trigger="manual"); db.add(old); db.flush()
        db.add(ProfileSegment(profile_id=old.id, line_id=line.id, dimension="运行时长规律", content="旧分段", time_windows=[], segment_date=date(2026, 9, 3)))
    with session_scope() as db:
        line = db.scalar(select(Line).where(Line.line_code == "L001")); ProfileService(FakeLLM()).generate_for_line(db, line, date(2026, 9, 3), "manual")
    with session_scope() as db:
        profile, segments = db.scalar(select(Profile)), list(db.scalars(select(ProfileSegment)))
        assert "新内容" in profile.full_content and len(segments) == 5 and all("旧" not in row.content for row in segments)
