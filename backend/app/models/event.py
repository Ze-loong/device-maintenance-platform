"""event 表：结构化事件（"历史事实"表）。写入时冗余 line_code/device_code 快照，
保证哪怕产线/设备被软删除，历史记录依然可读。

去重设计：对 (device_id, occurred_at, event_type) 建唯一约束，用于捕获 MQTT QoS1 的重复投递——
重复投递发送的是同一条消息，device_id/occurred_at/event_type 三者完全相同，精确匹配即可 100% 命中；
event_service 写入时捕获这个唯一键冲突，视为重复事件直接跳过后续推理和回推。
用数据库精确约束而不是时间窗口判断去重，是因为时间窗口容易把两个时间相近但真实发生的独立事件
误判成重复，数据库精确约束不会有这个问题，且天然对多线程/未来 REST 调试入口并发写入安全，不依赖内存状态。

约束为什么是三列而不是两列：如果只按 (device_id, occurred_at) 判重，会隐含假设
"同一设备同一精确时刻只会产生一种事件"——但一次超限读数会同时产生 sensor_reading 和
vibration_alert/temperature_alert 两条消息、共享同一个 occurred_at（它们本来就是同一次测量的两种解读），
两列约束会把后到的告警误判成 QoS1 重投而吞掉。加入 event_type 后，
QoS1 真正的重复投递（同设备+同时间+同事件类型）依然 100% 精确捕获，去重能力不打折，
同时允许同一时刻的不同事件类型共存。
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Event(Base):
    __tablename__ = "event"
    __table_args__ = (
        # QoS1 去重的核心约束，见上方模块 docstring。
        UniqueConstraint("device_id", "occurred_at", "event_type", name="uq_event_device_occurred_at_event_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("line.id", ondelete="RESTRICT"), nullable=False, index=True)
    line_code: Mapped[str] = mapped_column(String(64), nullable=False)
    device_id: Mapped[int] = mapped_column(ForeignKey("device.id", ondelete="RESTRICT"), nullable=False, index=True)
    device_code: Mapped[str] = mapped_column(String(64), nullable=False)
    # 四选一，互斥；Pydantic 层已用 Literal 强校验，这里用普通字符串即可
    # （数据库层再加 CHECK 约束属于双重校验，7天周期内收益不大，故略）。
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[float] = mapped_column(Numeric, nullable=False)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_backfill: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    # 原始报文归档文件路径，如 data/raw/L001/2026-09-04.jsonl（相对 backend/ 的路径）。
    raw_payload_path: Mapped[str] = mapped_column(String(255), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
