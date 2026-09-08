r"""任务书05真实验收脚本：准备独立演示产线并调用 DeepSeek 生成昨日画像。

脚本只追加或覆盖编号为 VERIFY05 的验收数据，不清理其他产线数据；实时 MQTT 推理
由随后启动的平台进程完成，避免绕过真实消息入口。
"""
from datetime import datetime, timedelta, timezone
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from app.ai.llm_client import LLMClient
from app.core.config import Settings
from app.core.db import init_engine, session_scope
from app.core.logging import setup_logging
from app.core.timeutil import to_beijing
from app.models.device import Device
from app.models.event import Event
from app.models.line import Line
from app.models.profile_segment import ProfileSegment
from app.service.profile_service import ProfileService


def main():
    """准备三条昨日事件并做一次真实画像生成，打印经校验后的结构化结果摘要。"""
    setup_logging(); settings = Settings(); init_engine(settings.database_url.get_secret_value())
    now = datetime.now(timezone.utc)
    target_date = (to_beijing(now) - timedelta(days=1)).date()
    with session_scope() as db:
        line = db.scalar(select(Line).where(Line.line_code == "VERIFY05"))
        if line is None:
            line = Line(line_code="VERIFY05", name="任务书05验收产线"); db.add(line); db.flush()
        device = db.scalar(select(Device).where(Device.device_code == "VERIFY05-WORKSHOP-A"))
        if device is None:
            device = Device(device_code="VERIFY05-WORKSHOP-A", line_id=line.id, device_type="vibration", location="workshop_a"); db.add(device); db.flush()
        base = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone(timedelta(hours=8))).astimezone(timezone.utc)
        for offset in (18 * 60, 18 * 60 + 20, 19 * 60):
            occurred = base + timedelta(minutes=offset)
            exists = db.scalar(select(Event).where(Event.device_id == device.id, Event.occurred_at == occurred))
            if exists is None:
                db.add(Event(line_id=line.id, line_code=line.line_code, device_id=device.id, device_code=device.device_code, event_type="fan_started", value=1, extra={"verification": True}, occurred_at=occurred, is_backfill=True, raw_payload_path="verification/seed"))
    llm = LLMClient(settings)
    try:
        with session_scope() as db:
            line = db.scalar(select(Line).where(Line.line_code == "VERIFY05"))
            profile = ProfileService(llm).generate_for_line(db, line, target_date, "manual")
            if profile is None: raise RuntimeError("profile generation failed")
            segments = list(db.scalars(select(ProfileSegment).where(ProfileSegment.profile_id == profile.id).order_by(ProfileSegment.id)))
            print(json.dumps({"line_code": line.line_code, "profile_date": str(target_date), "summary": profile.summary, "source_event_count": profile.source_event_count, "dimensions": [{"dimension": item.dimension, "content": item.content, "time_windows": item.time_windows} for item in segments]}, ensure_ascii=False))
    finally:
        llm.close()


if __name__ == "__main__": main()
