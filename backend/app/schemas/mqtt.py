"""MQTT 上下行数据契约：Pydantic 负责把 JSON 校验为明确的 Python 对象。
上行供 MQTT 入口解析，下行由业务层生成后交给 MQTT 发布。
字段与约束严格对应 MQTT 主题规范与数据库设计中的上下行契约定义。
"""
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# 协议层固定五选一：启动、停机、传感器读数、振动超限、温度超限。
EventType = Literal["fan_started", "fan_stopped", "sensor_reading", "vibration_alert", "temperature_alert"]


class UplinkEvent(BaseModel):
    """传感器上行事件。输入字段不合法时抛出 ValidationError，由入口拒绝。
    这里只做格式校验，不代表该产线或设备已在数据库注册——归属校验在 event_service 里做。
    """
    model_config = ConfigDict(extra="forbid")
    # 协议版本号，二期对接真实网关协议变化时用于新旧版本共存判断；本期固定 "1.0"。
    schema_version: str = "1.0"
    # 产线与设备编号仅允许字母、数字、下划线、连字符，避免混入 MQTT 的 /、+、#。
    line_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    device_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    # 设备类型、安装位置合法性由 config/base_data.yaml 校验，这里只校验长度（对应 FR-14）。
    device_type: str = Field(min_length=1, max_length=64)
    location: str = Field(min_length=1, max_length=64)
    event_type: EventType
    # 沿用单个数值字段：启停、传感器读数及超限事件均不增加载荷字段；具体单位与编码留待联调确认。
    value: float
    # default_factory 每次创建独立字典，避免多个事件共用可变对象。
    extra: dict[str, Any] = Field(default_factory=dict)
    # 必须包含时区，避免同一时间在不同机器上被解释为不同时间点。
    occurred_at: AwareDatetime
    # 是否为模拟器回填的历史数据，用于区分"回填批量数据"与"实时上报数据"（演示冷启动过程用）。
    is_backfill: bool = False


class DownlinkPrediction(BaseModel):
    """发给产线网关的预测结果。
    不回传完整原始事件/画像全文——网关已知道原始事件内容，画像全文体积大且无必要；
    完整关联关系（原始事件外键、命中的画像分段 ID）持久化在数据库 prediction 表中，
    管理端与预测调试页面通过数据库查询获取，MQTT 下行只承载网关侧需要的精简版本。
    """
    line_id: str
    # 平台为本次预测生成的 UUID，不是设备上报的幂等键。
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    next_behavior: str
    # 三档，由规则计算得出（非模型自评）：无画像→low；命中≥1天→medium；≥3天且时间吻合→high。
    confidence: Literal["low", "medium", "high"]
    # 正常时为模型给出的依据说明，降级时为收敛后的安全失败原因（不暴露内部异常类名）。
    reasoning: str
    # 命中的画像分段轻量引用（维度标题+简短摘要），非全文；无画像时为空数组。
    profile_refs: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
