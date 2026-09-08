"""FR-05 事件日志查询接口的数据契约：按产线/设备/时间过滤分页查询。"""
from datetime import datetime

from pydantic import BaseModel, Field


class EventQuery(BaseModel):
    """查询参数：全部可选，不传即查全部（分页仍然生效，避免一次性拉全表）。
    时间过滤用 occurred_at 而不是 received_at——运营人员关心"设备什么时候发生了这件事"，
    不是"平台什么时候收到"，这两者在网络延迟或模拟器回填场景下可能相差很大。"""
    line_code: str | None = None
    device_code: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)


class EventOut(BaseModel):
    """事件列表项。展示用快照字段（line_code/device_code）而不是再关联查 line/device 表，
    这是"历史事实表冗余快照"设计原则在查询侧的直接收益——哪怕产线/设备已被软删除，
    这里的编号依然完整可读。"""
    id: int
    line_code: str
    device_code: str
    event_type: str
    value: float
    extra: dict | None
    occurred_at: datetime
    is_backfill: bool
    received_at: datetime

    model_config = {"from_attributes": True}


class EventListResponse(BaseModel):
    items: list[EventOut]
    total: int
    page: int
    page_size: int
