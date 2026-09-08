"""产线管理 HTTP 控制器，只负责参数、鉴权和 service 调用。"""
from fastapi import APIRouter, Depends, Response

from app.core.deps import get_db, require_admin
from app.schemas.line import LineCreate, LineListResponse, LineOut, LineUpdate
from app.service.line_service import LineService

router = APIRouter(prefix="/api/lines", tags=["lines"], dependencies=[Depends(require_admin)])
service = LineService()


@router.get("", response_model=LineListResponse)
def list_lines(page: int = 1, page_size: int = 20, db=Depends(get_db)):
    return service.list(db, page, page_size)


@router.post("", response_model=LineOut, status_code=201)
def create_line(payload: LineCreate, db=Depends(get_db)):
    return service.create(db, payload)


@router.put("/{line_id}", response_model=LineOut)
def update_line(line_id: int, payload: LineUpdate, db=Depends(get_db)):
    return service.update(db, line_id, payload)


@router.delete("/{line_id}", status_code=204)
def delete_line(line_id: int, db=Depends(get_db)):
    service.delete(db, line_id)
    return Response(status_code=204)
