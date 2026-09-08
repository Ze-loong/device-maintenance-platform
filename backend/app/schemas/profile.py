"""画像手动触发接口的数据契约。"""
from datetime import date, datetime

from pydantic import BaseModel, Field


class ProfileGenerateRequest(BaseModel):
    """单产线指定日期画像生成请求。"""
    line_code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    target_date: date


class ProfileRebuildAllRequest(BaseModel):
    """全量重跑请求；日期不填时由调用端明确传入，不在服务端猜测。"""
    target_date: date


class ProfileTriggerResponse(BaseModel):
    """手动触发结果。"""
    status: str
    message: str


class ProfileListItem(BaseModel):
    """FR-09 画像列表项：只含概要信息，全文在详情接口里取（列表页不需要拉全文，减少载荷）。"""
    id: int
    line_code: str
    profile_date: date
    summary: str | None
    source_event_count: int
    generation_trigger: str
    generated_at: datetime

    model_config = {"from_attributes": True}


class ProfileSegmentDetail(BaseModel):
    """画像详情页展示的单个维度分段。"""
    dimension: str
    content: str
    time_windows: list[dict] | None

    model_config = {"from_attributes": True}

class ProfileDetail(BaseModel):
    """FR-09 画像详情：列表项字段 + 全文 + 按维度拆分的分段列表，供"全文查看"展示。"""
    id: int
    line_code: str
    profile_date: date
    summary: str | None
    full_content: str
    source_event_count: int
    generation_trigger: str
    generated_at: datetime
    segments: list[ProfileSegmentDetail]

    model_config = {"from_attributes": True}



class ProfileListResponse(BaseModel):
    items: list[ProfileListItem]
    total: int
    page: int
    page_size: int
