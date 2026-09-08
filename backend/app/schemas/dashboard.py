"""FR-10 仪表盘接口的数据契约：6 个统计卡 + 近 24 小时按小时事件时序图。
6 个统计卡的口径与字段顺序按需求会议纪要 FR-10 原文："产线数、设备总数、在线设备数、
事件总数、画像总数、近24小时事件数"。
"""
from pydantic import BaseModel


class DashboardStats(BaseModel):
    """产线数/设备总数默认只统计未软删除的记录——管理端列表也是这个口径，两处保持一致，
    避免"仪表盘显示10个产线，但列表页只看到8个"这种对不上的观感。"""
    line_count: int
    device_count: int
    online_device_count: int
    event_count: int
    profile_count: int
    recent_24h_event_count: int


class HourlyEventPoint(BaseModel):
    """近 24 小时按小时统计的一个数据点。hour 用北京时间"YYYY-MM-DD HH:00"格式的整点标签，
    不用纯数字 0-23——跨天时纯数字会有歧义（比如凌晨1点和昨天凌晨1点显示成同一个刻度），
    折线图 x 轴标签直接用这个字符串即可。"""
    hour: str
    event_count: int


class DashboardResponse(BaseModel):
    stats: DashboardStats
    hourly_events: list[HourlyEventPoint]
