"""画像控制器：提供单产线同步生成和全量异步重跑接口。"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.core.deps import require_admin
from app.schemas.profile import ProfileGenerateRequest, ProfileRebuildAllRequest, ProfileTriggerResponse
from app.tasks.scheduler import run_all_profiles

router = APIRouter(prefix="/api/profiles", tags=["profiles"], dependencies=[Depends(require_admin)])


@router.post("/generate", response_model=ProfileTriggerResponse)
def generate_one(payload: ProfileGenerateRequest, request: Request):
    """同步生成单产线指定日期画像。"""
    result = request.app.state.profile_service.generate_by_code(payload.line_code, payload.target_date)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="产线不存在")
    if result == "failed":
        raise HTTPException(status_code=502, detail="画像生成失败")
    return ProfileTriggerResponse(status="completed", message="画像生成完成")


@router.post("/rebuild-all", response_model=ProfileTriggerResponse, status_code=202)
def rebuild_all(payload: ProfileRebuildAllRequest, background_tasks: BackgroundTasks, request: Request):
    """立即返回已提交，并由 FastAPI 后台任务逐产线重跑。"""
    background_tasks.add_task(run_all_profiles, request.app.state.profile_service, payload.target_date, "manual")
    return ProfileTriggerResponse(status="submitted", message="全量画像重跑已提交")
