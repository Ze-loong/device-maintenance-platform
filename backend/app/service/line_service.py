"""产线业务层：编排 CRUD，并把数据库唯一约束转换成稳定的业务错误。"""
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.repository.line_repository import LineRepository
from app.schemas.line import LineCreate, LineListResponse, LineOut, LineUpdate


class LineService:
    """实现 FR-02 产线管理规则，控制器只负责接收和返回。"""

    def list(self, db, page: int, page_size: int) -> LineListResponse:
        items, total = LineRepository(db).list_paginated(page=page, page_size=page_size)
        return LineListResponse(items=[LineOut.model_validate(item) for item in items], total=total, page=page, page_size=page_size)

    def create(self, db, payload: LineCreate):
        repo = LineRepository(db)
        try:
            with db.begin_nested():
                return repo.create(**payload.model_dump())
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="产线编号已存在") from exc

    def update(self, db, line_id: int, payload: LineUpdate):
        repo = LineRepository(db)
        line = repo.get_by_id(line_id)
        if line is None or line.is_deleted:
            raise HTTPException(status_code=404, detail="产线不存在")
        return repo.update(line, **payload.model_dump())

    def delete(self, db, line_id: int) -> None:
        repo = LineRepository(db)
        line = repo.get_by_id(line_id)
        if line is None or line.is_deleted:
            raise HTTPException(status_code=404, detail="产线不存在")
        repo.soft_delete(line)
