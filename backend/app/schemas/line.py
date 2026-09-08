"""FR-02 产线管理接口的数据契约：产线档案 CRUD + 列表分页。"""
from datetime import datetime

from pydantic import BaseModel, Field


class LineCreate(BaseModel):
    """新建产线。line_code 由管理员手工填写（不是系统自动生成）——它同时也是
    MQTT 消息里网关侧要填写的编号，需要能对外沟通，不适合用系统生成的不可预测值。"""
    line_code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=128)
    remark: str | None = None


class LineUpdate(BaseModel):
    """更新产线：line_code 创建后不允许修改——MQTT 网关侧可能已经在用这个编号上报，
    改掉会导致历史事件与产线档案的编号对不上，只能改名称/备注。"""
    name: str = Field(min_length=1, max_length=128)
    remark: str | None = None


class LineOut(BaseModel):
    """产线详情/列表项。"""
    id: int
    line_code: str
    name: str
    remark: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LineListResponse(BaseModel):
    """分页列表响应，与 device/event 等其他列表接口保持同样的 items+total+page+page_size 形状，
    前端 JS 的分页渲染逻辑可以在几个页面间复用同一套代码。"""
    items: list[LineOut]
    total: int
    page: int
    page_size: int
