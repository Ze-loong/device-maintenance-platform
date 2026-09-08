"""设备管理 HTTP 控制器，业务校验集中在 DeviceService。"""
from fastapi import APIRouter, Depends, Response

from app.core.deps import get_db, require_admin
from app.schemas.device import DeviceCreate, DeviceListResponse, DeviceOut, DeviceUpdate
from app.service.device_service import DeviceService

router = APIRouter(prefix="/api/devices", tags=["devices"], dependencies=[Depends(require_admin)])
service = DeviceService()


@router.get("", response_model=DeviceListResponse)
def list_devices(page: int = 1, page_size: int = 20, line_id: int | None = None, db=Depends(get_db)):
    return service.list(db, page, page_size, line_id)


@router.post("", response_model=DeviceOut, status_code=201)
def create_device(payload: DeviceCreate, db=Depends(get_db)):
    return service.create(db, payload)


@router.put("/{device_id}", response_model=DeviceOut)
def update_device(device_id: int, payload: DeviceUpdate, db=Depends(get_db)):
    return service.update(db, device_id, payload)


@router.delete("/{device_id}", status_code=204)
def delete_device(device_id: int, db=Depends(get_db)):
    service.delete(db, device_id)
    return Response(status_code=204)
