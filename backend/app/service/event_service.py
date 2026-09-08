"""事件业务编排层：统一处理 MQTT 与未来 REST 调试入口提交的事件。"""
import json
import logging
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import BACKEND_DIR
from app.core.db import session_scope
from app.core.timeutil import to_beijing
from app.repository.device_repository import DeviceRepository
from app.repository.event_repository import EventRepository
from app.repository.line_repository import LineRepository
from app.repository.unregistered_alert_repository import UnregisteredAlertRepository
from app.schemas.mqtt import DownlinkPrediction, UplinkEvent

logger = logging.getLogger("iot")
UNREGISTERED_FALLBACK = "暂无法判断，设备或产线未注册，请先完成平台注册"
STORAGE_FALLBACK = "暂无法判断，平台存储服务异常，已启用兜底提示"


class EventService:
    """执行一条事件的完整业务链路，不负责 MQTT 网络连接和实际发布。"""

    def __init__(self, inference_service, raw_data_dir: Path | None = None):
        self.inference_service = inference_service
        self.raw_data_dir = raw_data_dir or BACKEND_DIR / "data" / "raw"

    def _archive(self, event: UplinkEvent) -> str:
        """按产线和北京时间日期追加 JSONL，返回相对 backend 的归档路径。"""
        day = to_beijing(event.occurred_at).date().isoformat()
        path = self.raw_data_dir / event.line_id / f"{day}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")
        try:
            return path.relative_to(BACKEND_DIR).as_posix()
        except ValueError:
            return str(path)

    @staticmethod
    def _unregistered_prediction(event: UplinkEvent) -> DownlinkPrediction:
        return DownlinkPrediction(line_id=event.line_id, next_behavior="暂无法提供预测", confidence="low", reasoning=UNREGISTERED_FALLBACK)

    def handle_event(self, event: UplinkEvent) -> DownlinkPrediction | None:
        """处理校验后的事件；QoS1 重复投递返回 None，其余路径尽量返回兜底结果。"""
        logger.info("收到事件 产线=%s 设备=%s", event.line_id, event.device_id)
        try:
            with session_scope() as db:
                line = LineRepository(db).get_by_code(event.line_id)
                device = DeviceRepository(db).get_by_code(event.device_id) if line else None
                reason = None
                if line is None:
                    reason = "line_not_registered"
                elif device is None:
                    reason = "device_not_registered"
                elif device.line_id != line.id:
                    reason = "device_line_mismatch"
                if reason:
                    UnregisteredAlertRepository(db).create(line_id_raw=event.line_id, device_id_raw=event.device_id, topic=f"line/{event.line_id}/{event.device_id}/event", reason=reason, raw_payload=event.model_dump(mode="json"))
                    logger.warning("未注册事件已拒绝 产线=%s 设备=%s 原因=%s", event.line_id, event.device_id, reason)
                    return self._unregistered_prediction(event)

                # 归档保留接收到的原始事实，因此即使是 QoS1 重投也允许多一行。
                raw_payload_path = self._archive(event)
                inserted = EventRepository(db).create_if_not_duplicate(line_id=line.id, line_code=line.line_code, device_id=device.id, device_code=device.device_code, event_type=event.event_type, value=event.value, extra=event.extra, occurred_at=event.occurred_at, is_backfill=event.is_backfill, raw_payload_path=raw_payload_path)
                if inserted is None:
                    logger.info("重复事件已忽略（QoS1可能重投）产线=%s 设备=%s 时间=%s", event.line_id, event.device_id, event.occurred_at.isoformat())
                    return None
                # 回填用于构建昨日画像，只需归档和入库。若对数百条历史事件逐条调用实时推理，
                # 既会产生无意义的历史回推，也会放大模型费用；实时事件仍走下面完整推理链路。
                if event.is_backfill:
                    logger.info("回填事件已入库，跳过实时预测 产线=%s 设备=%s", event.line_id, event.device_id)
                    return None
                return self.inference_service.infer(db, line, device, event, source_event_id=inserted.id)
        except (SQLAlchemyError, OSError, RuntimeError) as exc:
            logger.exception("事件存储或编排失败：%s", type(exc).__name__)
            return DownlinkPrediction(line_id=event.line_id, next_behavior="暂无法判断，建议保持正常观察", confidence="low", reasoning=STORAGE_FALLBACK)
