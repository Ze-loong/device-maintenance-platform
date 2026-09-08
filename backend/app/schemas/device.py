"""FR-03 设备管理接口的数据契约：设备档案 CRUD + 列表分页。"""
from datetime import datetime

from pydantic import BaseModel, Field


class DeviceCreate(BaseModel):
    """新建设备。device_type/location 的合法值来自 config/base_data.yaml
    （FR-14 最简实现，数据库层不做枚举约束），这里不用 Literal 硬编码——
    校验放在 service 层查配置文件完成，
    保证新增设备类型时只改配置文件、不用改这个 Pydantic 模型。"""
    device_code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    line_id: int
    device_type: str = Field(min_length=1, max_length=64)
    location: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=128)


class DeviceUpdate(BaseModel):
    """更新设备：device_code 创建后不允许修改，理由同 line_code（MQTT 网关侧已在用）；
    line_id（归属产线）本期也不允许改——需求纪要没有提"设备转移归属产线"这个场景，
    改归属会牵扯历史事件的产线快照字段如何解释，本期不支持，如需要转移，走"删除重建"。"""
    device_type: str = Field(min_length=1, max_length=64)
    location: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=128)


class DeviceOut(BaseModel):
    id: int
    device_code: str
    line_id: int
    device_type: str
    location: str
    name: str | None
    online_status: bool
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeviceListResponse(BaseModel):
    items: list[DeviceOut]
    total: int
    page: int
    page_size: int
