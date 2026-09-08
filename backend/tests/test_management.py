"""D4-D5 管理端验收：使用独立真实 PostgreSQL 测试库，LLM 用确定性替身。"""
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app.api import auth, devices, lines, management, pages, profiles
from app.core.db import session_scope
from app.core.security import hash_password
from app.models.admin_user import AdminUser
from app.models.event import Event
from app.models.line import Line
from app.models.device import Device
from app.models.profile import Profile
from app.models.profile_segment import ProfileSegment
from app.service.debug_service import DebugService
from app.service.event_service import EventService
from app.service.inference_service import InferenceService
from app.service.query_service import QueryService
from test_core_services import FakeLLM, clear_and_seed, setup_module as setup_test_database


def setup_module():
    """沿用核心测试的独立数据库，绝不改动正常演示库。"""
    setup_test_database()


@pytest.fixture
def client(tmp_path):
    """每项测试重置测试库并装配全部路由，避免启动真实 MQTT 后台线程。"""
    clear_and_seed()
    with session_scope() as db:
        db.add(AdminUser(username="test_admin", password_hash=hash_password("test_password")))
    app = FastAPI()
    app.state.debug_service = DebugService(EventService(InferenceService(FakeLLM()), tmp_path))
    for router in (auth.router, lines.router, devices.router, profiles.router, management.router, pages.router):
        app.include_router(router)
    with TestClient(app) as browser:
        yield browser


def login(client):
    """以测试管理员登录，后续请求由 TestClient 自动携带会话 Cookie。"""
    return client.post("/api/auth/login", json={"username": "test_admin", "password": "test_password"})


def test_login_failure_success_logout_and_guards(client):
    assert client.post("/api/auth/login", json={"username": "test_admin", "password": "wrong"}).status_code == 401
    for path in ("/api/lines", "/api/devices", "/api/events", "/api/profiles", "/api/dashboard", "/api/base-data"):
        assert client.get(path).status_code == 401
    assert client.post("/api/profiles/generate", json={"line_code": "L001", "target_date": "2026-09-02"}).status_code == 401
    assert client.post("/api/profiles/rebuild-all", json={"target_date": "2026-09-02"}).status_code == 401
    response = login(client)
    assert response.status_code == 200 and "httponly" in response.headers["set-cookie"].lower()
    assert client.get("/api/lines").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/lines").status_code == 401


def test_line_device_crud_conflicts_and_base_validation(client):
    login(client)
    line_body = {"line_code": "NEW06", "name": "新产线"}
    created = client.post("/api/lines", json=line_body)
    assert created.status_code == 201
    line_id = created.json()["id"]
    assert client.post("/api/lines", json=line_body).status_code == 409
    assert client.put(f"/api/lines/{line_id}", json={"name": "已更新"}).json()["name"] == "已更新"
    device_body = {"device_code": "NEW06-D", "line_id": line_id, "device_type": "vibration", "location": "workshop_a", "name": "测试设备"}
    created_device = client.post("/api/devices", json=device_body)
    assert created_device.status_code == 201
    device_id = created_device.json()["id"]
    assert client.post("/api/devices", json=device_body).status_code == 409
    assert client.post("/api/devices", json={**device_body, "device_code": "INVALID", "location": "unknown"}).status_code == 422
    assert client.put(f"/api/devices/{device_id}", json={"device_type": "temperature", "location": "workshop_b", "name": "新名称"}).json()["location"] == "workshop_b"
    assert client.delete(f"/api/devices/{device_id}").status_code == 204
    assert all(item["id"] != device_id for item in client.get("/api/devices").json()["items"])
    assert client.delete(f"/api/lines/{line_id}").status_code == 204
    assert all(item["id"] != line_id for item in client.get("/api/lines").json()["items"])


def test_event_filters_pagination_and_soft_delete_history(client):
    login(client)
    base = datetime(2026, 9, 3, 8, tzinfo=timezone.utc)
    with session_scope() as db:
        line = db.scalar(select(Line).where(Line.line_code == "L001"))
        device = db.scalar(select(Device).where(Device.device_code == "D001"))
        line_id, device_id = line.id, device.id
        for index in range(5):
            db.add(Event(line_id=line.id, line_code="L001", device_id=device.id, device_code="D001", event_type="sensor_reading", value=index, occurred_at=base + timedelta(minutes=index), is_backfill=True, raw_payload_path="test"))
    params = {"line_code": "L001", "device_code": "D001", "start_time": (base + timedelta(minutes=1)).isoformat(), "end_time": (base + timedelta(minutes=3)).isoformat(), "page": 2, "page_size": 2}
    result = client.get("/api/events", params=params).json()
    assert result["total"] == 3 and len(result["items"]) == 1 and result["items"][0]["value"] == 1
    client.delete(f"/api/devices/{device_id}")
    client.delete(f"/api/lines/{line_id}")
    assert client.get("/api/events", params={"line_code": "L001"}).json()["total"] == 5


def test_profile_list_detail_and_dashboard_counts(client):
    login(client)
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        line = db.scalar(select(Line).where(Line.line_code == "L001"))
        device = db.scalar(select(Device).where(Device.device_code == "D001"))
        db.add(Event(line_id=line.id, line_code="L001", device_id=device.id, device_code="D001", event_type="fan_started", value=1, occurred_at=now - timedelta(hours=1), is_backfill=False, raw_payload_path="test"))
        profile = Profile(line_id=line.id, profile_date=date(2026, 9, 2), summary="画像摘要", full_content="画像全文", source_event_count=1, generation_trigger="manual")
        db.add(profile); db.flush(); profile_id = profile.id
        db.add(ProfileSegment(profile_id=profile.id, line_id=line.id, dimension="运行时长规律", content="分段全文", segment_date=profile.profile_date, time_windows=[]))
    listing = client.get("/api/profiles", params={"line_code": "L001"}).json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == profile_id
    detail = client.get(f"/api/profiles/{profile_id}").json()
    assert detail["full_content"] == "画像全文" and detail["segments"][0]["content"] == "分段全文"
    assert client.get("/api/profiles/999999").status_code == 404
    data = client.get("/api/dashboard").json()
    assert data["stats"] == {"line_count": 2, "device_count": 2, "online_device_count": 0, "event_count": 1, "profile_count": 1, "recent_24h_event_count": 1}
    assert len(data["hourly_events"]) == 24 and sum(item["event_count"] for item in data["hourly_events"]) == 1


def test_debug_normal_and_duplicate_same_chain(client):
    login(client)
    payload = {"line_id": "L001", "device_id": "D001", "device_type": "vibration", "location": "workshop_a", "event_type": "fan_started", "value": 1, "occurred_at": datetime.now(timezone.utc).isoformat()}
    first = client.post("/api/debug/predict", json=payload).json()
    second = client.post("/api/debug/predict", json=payload).json()
    assert first["prediction"]["confidence"] == "low" and first["is_duplicate"] is False
    assert second["is_duplicate"] is True and second["prediction"] is None


def test_page_routes_redirect_and_render(client):
    for path in ("/dashboard", "/lines", "/devices", "/events", "/profiles", "/debug"):
        assert client.get(path, follow_redirects=False).status_code == 303
    login(client)
    for path in ("/dashboard", "/lines", "/devices", "/events", "/profiles", "/debug"):
        assert client.get(path).status_code == 200
