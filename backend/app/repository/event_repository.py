"""event 表持久化：结构化事件的写入与查询。
QoS1 去重依赖 event 表的唯一约束 (device_id, occurred_at, event_type)，本仓储把"插入即去重"
封装成 create_if_not_duplicate，调用方（event_service）不需要关心具体是哪种数据库异常。
"""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.device import Device


class EventRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_if_not_duplicate(self, **fields) -> Event | None:
        """尝试插入一条事件；若 (device_id, occurred_at, event_type) 已存在（QoS1 重复投递），
        捕获唯一键冲突、回滚本次插入并返回 None，调用方据此判断"这是重复事件，跳过后续处理"。
        约束是三列而不是两列：同一设备同一时刻的不同事件类型（如一次超限读数
        同时产生 sensor_reading 和 vibration_alert）不会被误判为重复，只有三者都相同才算重投。
        用 SAVEPOINT（begin_nested）而不是回滚整个外层事务，这样即使这条事件是重复的，
        同一个 session 里其他还没提交的操作不会被一起撤销。
        """
        event = Event(**fields)
        try:
            with self.db.begin_nested():
                self.db.add(event)
                self.db.flush()
        except IntegrityError:
            return None
        return event

    def list_by_line_and_date(self, line_id: int, day: date) -> list[Event]:
        """查某产线某个北京时间自然日的全部事件，供画像生成聚合使用。"""
        start = datetime.combine(day, time.min, tzinfo=timezone(timedelta(hours=8))).astimezone(timezone.utc)
        end = start + timedelta(days=1)
        stmt = select(Event, Device.location, Device.device_type).join(Device, Event.device_id == Device.id).where(Event.line_id == line_id, Event.occurred_at >= start, Event.occurred_at < end).order_by(Event.occurred_at)
        events = []
        for event, location, device_type in self.db.execute(stmt):
            # 画像输入需要设备位置，但 event 表按设计只保存 device_id；查询时从设备表补齐临时属性。
            event.location = location
            event.device_type = device_type
            events.append(event)
        return events

    def list_paginated(self, *, line_code: str | None = None, device_code: str | None = None, start_time=None, end_time=None, page: int = 1, page_size: int = 20) -> tuple[list[Event], int]:
        """FR-05 事件日志查询：按产线/设备编号（快照字段，不 JOIN 主表）+ occurred_at 时间范围过滤分页。
        用快照字段过滤而不是 JOIN line/device 表，一是查询更简单，二是哪怕产线/设备已被软删除，
        历史事件依然能按编号查到（"历史事实表冗余快照"设计原则在查询侧的直接体现）。
        按 occurred_at 降序排列——运营人员查日志通常最关心"最近发生了什么"。"""
        stmt = select(Event)
        count_stmt = select(func.count()).select_from(Event)
        conditions = []
        if line_code:
            conditions.append(Event.line_code == line_code)
        if device_code:
            conditions.append(Event.device_code == device_code)
        if start_time:
            conditions.append(Event.occurred_at >= start_time)
        if end_time:
            conditions.append(Event.occurred_at <= end_time)
        for condition in conditions:
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = self.db.execute(count_stmt).scalar_one()
        stmt = stmt.order_by(Event.occurred_at.desc()).offset((page - 1) * page_size).limit(page_size)
        items = list(self.db.execute(stmt).scalars())
        return items, total

    def count_total(self) -> int:
        """事件总数，供仪表盘统计卡使用（FR-10）。"""
        return self.db.execute(select(func.count()).select_from(Event)).scalar_one()

    def count_since(self, since: datetime) -> int:
        """指定时间点以来的事件数，供仪表盘"近24小时事件数"统计卡使用（FR-10）；
        since 由调用方（dashboard 相关 service）传入 UTC 时间点（当前时间减 24 小时）。"""
        stmt = select(func.count()).select_from(Event).where(Event.occurred_at >= since)
        return self.db.execute(stmt).scalar_one()

    def list_occurred_at_since(self, since: datetime) -> list[datetime]:
        """返回指定时间点以来全部事件的 occurred_at，供仪表盘"近24小时按小时统计"折线图使用。
        只取这一列而不是整行，减少不必要的数据传输；按小时分桶聚合放在 service 层用 Python 做
        （而不是写 SQL 的 date_trunc），因为分桶要按北京时间（core/timeutil.to_beijing）而不是
        数据库存储用的 UTC，用 Python 做转换更直观、不用在 SQL 里手写时区偏移表达式。
        30-50 产线、分钟级事件的规模下，24 小时窗口内的行数是几千条量级，Python 里聚合足够快。"""
        stmt = select(Event.occurred_at).where(Event.occurred_at >= since).order_by(Event.occurred_at)
        return list(self.db.execute(stmt).scalars())
