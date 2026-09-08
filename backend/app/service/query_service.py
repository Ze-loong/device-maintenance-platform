"""管理端只读业务编排：事件、画像和仪表盘查询统一放在 service 层。"""
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.core.timeutil import to_beijing
from app.repository.device_repository import DeviceRepository
from app.repository.event_repository import EventRepository
from app.repository.line_repository import LineRepository
from app.repository.profile_repository import ProfileRepository
from app.schemas.dashboard import DashboardResponse, DashboardStats, HourlyEventPoint
from app.schemas.event import EventListResponse, EventOut, EventQuery
from app.schemas.profile import ProfileDetail, ProfileListItem, ProfileListResponse, ProfileSegmentDetail


class QueryService:
    """把多个 repository 的查询结果组装成稳定的 API 响应。"""

    def events(self, db, query: EventQuery) -> EventListResponse:
        items, total = EventRepository(db).list_paginated(**query.model_dump())
        return EventListResponse(items=[EventOut.model_validate(item) for item in items], total=total, page=query.page, page_size=query.page_size)

    def profiles(self, db, line_code: str | None, page: int, page_size: int) -> ProfileListResponse:
        items, total = ProfileRepository(db).list_paginated(line_code=line_code, page=page, page_size=page_size)
        return ProfileListResponse(items=[ProfileListItem.model_validate(item) for item in items], total=total, page=page, page_size=page_size)

    def profile_detail(self, db, profile_id: int) -> ProfileDetail:
        profile, segments = ProfileRepository(db).get_by_id_with_segments(profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="画像不存在")
        return ProfileDetail(
            **ProfileListItem.model_validate(profile).model_dump(),
            full_content=profile.full_content,
            segments=[ProfileSegmentDetail.model_validate(item) for item in segments],
        )

    def dashboard(self, db, now_utc: datetime | None = None) -> DashboardResponse:
        now_utc = now_utc or datetime.now(timezone.utc)
        since = now_utc - timedelta(hours=24)
        event_repo = EventRepository(db)
        times = event_repo.list_occurred_at_since(since)
        buckets = Counter(to_beijing(value).replace(minute=0, second=0, microsecond=0) for value in times)
        # 从当前北京时间整点向前补齐 24 个连续整点，折线图不会因空小时断轴。
        current_hour = to_beijing(now_utc).replace(minute=0, second=0, microsecond=0)
        points = [current_hour - timedelta(hours=offset) for offset in range(23, -1, -1)]
        return DashboardResponse(
            stats=DashboardStats(
                line_count=LineRepository(db).count_active(),
                device_count=DeviceRepository(db).count_active(),
                online_device_count=DeviceRepository(db).count_online(),
                event_count=event_repo.count_total(),
                profile_count=ProfileRepository(db).count_total(),
                recent_24h_event_count=event_repo.count_since(since),
            ),
            hourly_events=[HourlyEventPoint(hour=point.strftime("%Y-%m-%d %H:00"), event_count=buckets[point]) for point in points],
        )
