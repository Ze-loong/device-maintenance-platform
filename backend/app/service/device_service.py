"""设备业务层：校验归属与基础数据，并编排设备 CRUD。"""
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.base_data import list_device_types, list_locations
from app.repository.device_repository import DeviceRepository
from app.repository.line_repository import LineRepository
from app.schemas.device import DeviceCreate, DeviceListResponse, DeviceOut, DeviceUpdate


class DeviceService:
    """实现 FR-03 的设备编号、归属产线和枚举值规则。"""

    @staticmethod
    def _validate_base_data(device_type: str, location: str) -> None:
        if device_type not in {item["code"] for item in list_device_types()}:
            raise HTTPException(status_code=422, detail="设备类型不在基础数据清单中")
        if location not in {item["code"] for item in list_locations()}:
            raise HTTPException(status_code=422, detail="安装位置不在基础数据清单中")

    def list(self, db, page: int, page_size: int, line_id: int | None) -> DeviceListResponse:
        items, total = DeviceRepository(db).list_paginated(page=page, page_size=page_size, line_id=line_id)
        return DeviceListResponse(items=[DeviceOut.model_validate(item) for item in items], total=total, page=page, page_size=page_size)

    def create(self, db, payload: DeviceCreate):
        self._validate_base_data(payload.device_type, payload.location)
        line = LineRepository(db).get_by_id(payload.line_id)
        if line is None or line.is_deleted:
            raise HTTPException(status_code=404, detail="归属产线不存在")
        try:
            with db.begin_nested():
                return DeviceRepository(db).create(**payload.model_dump())
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="设备编号已存在") from exc

    def update(self, db, device_id: int, payload: DeviceUpdate):
        self._validate_base_data(payload.device_type, payload.location)
        repo = DeviceRepository(db)
        device = repo.get_by_id(device_id)
        if device is None or device.is_deleted:
            raise HTTPException(status_code=404, detail="设备不存在")
        return repo.update(device, **payload.model_dump())

    def delete(self, db, device_id: int) -> None:
        repo = DeviceRepository(db)
        device = repo.get_by_id(device_id)
        if device is None or device.is_deleted:
            raise HTTPException(status_code=404, detail="设备不存在")
        repo.soft_delete(device)
