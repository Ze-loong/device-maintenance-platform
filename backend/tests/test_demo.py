"""基础契约测试：大模型输出校验、MQTT 字段安全和健康接口。"""
from datetime import datetime, timezone
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import OpenAI
from pydantic import ValidationError
import pytest
from app.ai.llm_client import InferenceError, LLMClient
from app.ai.sanitized_context import SanitizedLineContext
from app.api.health import router
from app.core.base_data import get_dimensions_for_event
from app.core.config import Settings
from app.schemas.mqtt import UplinkEvent


def event():
    return UplinkEvent(line_id="L001", device_id="D001", device_type="vibration", location="workshop_a", event_type="fan_started", value=1, occurred_at=datetime.now(timezone.utc))


def test_alert_events_use_fixed_dimensions():
    """两个超限事件不依赖安装位置，直接命中各自的固定画像维度。"""
    assert get_dimensions_for_event("unknown", "vibration_alert") == ["振动特征"]
    assert get_dimensions_for_event("unknown", "temperature_alert") == ["温度趋势"]


@pytest.mark.parametrize("status,body", [(401, {"error": {"message": "invalid", "type": "authentication_error"}}), (200, {"choices": [{"message": {"role": "assistant", "content": "invalid-json"}, "finish_reason": "stop", "index": 0}], "id": "test", "created": 0, "model": "test", "object": "chat.completion"})])
def test_llm_failures_are_normalized(status, body):
    """调用失败和 JSON 校验失败都转换成业务层可捕获的异常。"""
    llm = LLMClient(Settings(deepseek_api_key="test", mqtt_password="test")); llm.client.close()
    llm.client = OpenAI(api_key="test", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body))))
    try:
        with pytest.raises(InferenceError): llm.infer(SanitizedLineContext(line_code="L001"), event(), [])
    finally: llm.close()


def test_topic_injection_rejected():
    with pytest.raises(ValidationError): UplinkEvent(**(event().model_dump() | {"line_id": "L001/+/event"}))


def test_health_contract():
    app = FastAPI(); app.include_router(router)
    assert TestClient(app).get("/health").json() == {"status": "ok"}
