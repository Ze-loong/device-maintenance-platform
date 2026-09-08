"""device 表持久化。"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.device import Device


class DeviceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_code(self, device_code: str) -> Device | None:
        """按业务编号查设备，只返回未软删除的记录。"""
        stmt = select(Device).where(Device.device_code == device_code, Device.is_deleted.is_(False))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_id(self, device_id: int) -> Device | None:
        return self.db.get(Device, device_id)

    def create(self, *, device_code: str, line_id: int, device_type: str, location: str, name: str | None) -> Device:
        """新建设备（FR-03）。device_type/location 的合法性由 service 层查
        config/base_data.yaml 校验后再调用这里，仓储层本身不做业务规则校验。"""
        device = Device(device_code=device_code, line_id=line_id, device_type=device_type, location=location, name=name)
        self.db.add(device)
        self.db.flush()
        return device

    def update(self, device: Device, *, device_type: str, location: str, name: str | None) -> Device:
        """更新设备档案（FR-03）。device_code/line_id 不在更新范围内，理由见
        schemas/device.py 的 DeviceUpdate 注释。"""
        device.device_type = device_type
        device.location = location
        device.name = name
        self.db.flush()
        return device

    def soft_delete(self, device: Device) -> None:
        """软删除：只标记 is_deleted，不物理删除，保留历史事件可追溯。"""
        device.is_deleted = True
        self.db.flush()

    def list_paginated(self, *, page: int, page_size: int, line_id: int | None = None, include_deleted: bool = False) -> tuple[list[Device], int]:
        """分页列表，供 FR-03 管理页面使用；line_id 传入时按归属产线过滤，
        用于"产线详情页查看名下设备"或调试页面"选完产线后过滤设备下拉框"这类场景。"""
        stmt = select(Device)
        count_stmt = select(func.count()).select_from(Device)
        if not include_deleted:
            stmt = stmt.where(Device.is_deleted.is_(False))
            count_stmt = count_stmt.where(Device.is_deleted.is_(False))
        if line_id is not None:
            stmt = stmt.where(Device.line_id == line_id)
            count_stmt = count_stmt.where(Device.line_id == line_id)
        total = self.db.execute(count_stmt).scalar_one()
        stmt = stmt.order_by(Device.id).offset((page - 1) * page_size).limit(page_size)
        items = list(self.db.execute(stmt).scalars())
        return items, total

    def list_by_line(self, line_id: int) -> list[Device]:
        """某产线名下全部未软删除设备，不分页——调试页面(FR-11)按产线过滤设备下拉框用，
        单产线设备数量级（个位数到十几个）不需要分页。"""
        stmt = select(Device).where(Device.line_id == line_id, Device.is_deleted.is_(False)).order_by(Device.id)
        return list(self.db.execute(stmt).scalars())

    def count_active(self) -> int:
        """未软删除设备总数，供仪表盘统计卡使用（FR-10）。"""
        stmt = select(func.count()).select_from(Device).where(Device.is_deleted.is_(False))
        return self.db.execute(stmt).scalar_one()

    def count_online(self) -> int:
        """在线设备数，供仪表盘统计卡使用（FR-10）。FR-13（心跳/在线状态维护）本期不实现，
        online_status 恒为默认值 False，这个统计卡在 D6 之前会一直显示 0——
        这不是查询逻辑的 bug，是 FR-13 被砍到"应该级、D6 可选"范围之外的必然结果，
        仪表盘页面可以在这张卡片旁加一句"FR-13 暂未实现"的小字说明，避免被误解成故障。"""
        stmt = select(func.count()).select_from(Device).where(Device.is_deleted.is_(False), Device.online_status.is_(True))
        return self.db.execute(stmt).scalar_one()
