"""后端装配入口：由 uvicorn 加载 app，注册 HTTP 路由和启动/退出流程。
这里只连接配置、MQTT 与业务服务，不直接编写推理规则。"""
from contextlib import asynccontextmanager
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.ai.llm_client import LLMClient
from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.devices import router as devices_router
from app.api.lines import router as lines_router
from app.api.management import router as management_router
from app.api.pages import router as pages_router
from app.api.profiles import router as profiles_router
from app.core.config import Settings
from app.core.db import init_engine
from app.core.logging import setup_logging
from app.mqtt.client import MQTTClient
from app.service.event_service import EventService
from app.service.debug_service import DebugService
from app.service.inference_service import InferenceService
from app.service.profile_service import ProfileService
from app.tasks.scheduler import create_scheduler


@asynccontextmanager
async def lifespan(app):
    """管理应用生命周期：启动 MQTT 后才让 FastAPI 接受请求。
    yield 前是启动阶段，之后是退出清理；即使启动失败，也关闭大模型 HTTP 客户端。"""
    setup_logging()
    settings = Settings()
    init_engine(settings.database_url.get_secret_value())
    llm = LLMClient(settings)
    inference_service = InferenceService(llm)
    profile_service = ProfileService(llm)
    event_service = EventService(inference_service)
    broker = MQTTClient(settings, event_service)
    scheduler = create_scheduler(profile_service)
    try:
        # MQTT 启动含阻塞等待，移到线程执行，避免卡住 FastAPI 的异步事件循环。
        await asyncio.to_thread(broker.start)
        app.state.broker = broker
        app.state.event_service = event_service
        app.state.debug_service = DebugService(event_service)
        app.state.profile_service = profile_service
        scheduler.start()
        try:
            # 在这里把控制权交给 FastAPI，开始处理请求；退出时再进入下面的 finally。
            yield
        finally:
            scheduler.shutdown(wait=False)
            # 先等事件处理与 MQTT 发布结束，再在外层 finally 关闭大模型连接池。
            await asyncio.to_thread(broker.stop)
    finally:
        llm.close()


app = FastAPI(title="设备预测性维护平台", lifespan=lifespan)

logger = logging.getLogger("iot")
DB_ERROR_MESSAGE = "平台数据库暂时不可用，请稍后重试；具体原因已记录在后台日志。"


@app.exception_handler(SQLAlchemyError)
async def handle_database_error(request: Request, exc: SQLAlchemyError):
    """统一兜底数据库连接或查询异常。

    API 返回中文 JSON 503，管理页面返回简单中文错误页。真实异常只写后台日志，
    避免响应体泄露数据库连接信息，同时让前端能区分临时故障和普通业务错误。
    """
    logger.exception("数据库操作异常：%s", type(exc).__name__)
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=503, content={"detail": DB_ERROR_MESSAGE})
    return HTMLResponse(
        status_code=503,
        content=(
            "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<title>暂时不可用</title></head><body style=\"font-line:sans-serif;"
            f"text-align:center;margin-top:10%\"><h2>页面暂时不可用</h2><p>{DB_ERROR_MESSAGE}</p></body></html>"
        ),
    )

app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(lines_router)
app.include_router(devices_router)
app.include_router(profiles_router)
app.include_router(management_router)
app.include_router(pages_router)
