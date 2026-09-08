"""事件、画像、仪表盘、基础数据与调试接口的轻量 HTTP 控制器。"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request

from app.core.base_data import list_device_types, list_locations
from app.core.deps import get_db, require_admin
from app.schemas.dashboard import DashboardResponse
from app.schemas.debug import DebugPredictionResponse
from app.schemas.event import EventListResponse, EventQuery
from app.schemas.mqtt import UplinkEvent
from app.schemas.profile import ProfileDetail, ProfileListResponse
from app.service.query_service import QueryService

router = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])
query_service = QueryService()


@router.get("/base-data")
def base_data():
    return {"device_types": list_device_types(), "locations": list_locations()}


@router.get("/events", response_model=EventListResponse)
def events(
    line_code: str | None = None,
    device_code: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db=Depends(get_db),
):
    return query_service.events(db, EventQuery(line_code=line_code, device_code=device_code, start_time=start_time, end_time=end_time, page=page, page_size=page_size))


@router.get("/profiles", response_model=ProfileListResponse)
def profiles(line_code: str | None = None, page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=200), db=Depends(get_db)):
    return query_service.profiles(db, line_code, page, page_size)


@router.get("/profiles/{profile_id}", response_model=ProfileDetail)
def profile_detail(profile_id: int, db=Depends(get_db)):
    return query_service.profile_detail(db, profile_id)


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(db=Depends(get_db)):
    return query_service.dashboard(db)


@router.post("/debug/predict", response_model=DebugPredictionResponse)
def debug_predict(payload: UplinkEvent, request: Request):
    return request.app.state.debug_service.predict(payload)
