"""HTTP 入口层的健康接口，由 main.py 注册。
仅说明 HTTP 服务能响应；不主动检查数据库或大模型是否可用。"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    """返回固定健康响应，供手动检查和 HTTP 探测使用。
    不验证 MQTT 当前连接状态，不能据此判断完整业务链路健康。"""
    return {"status": "ok"}
