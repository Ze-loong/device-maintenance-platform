"""line 表持久化：service 层只调这里，不直接写 ORM 查询。"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.line import Line


class LineRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_code(self, line_code: str) -> Line | None:
        """按业务编号查产线，只返回未软删除的记录——已删除的产线视同不存在，
        用于 MQTT 事件的归属校验。
        """
        stmt = select(Line).where(Line.line_code == line_code, Line.is_deleted.is_(False))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_id(self, line_id: int) -> Line | None:
        return self.db.get(Line, line_id)

    def list_active(self) -> list[Line]:
        """返回全部未软删除产线，供每日批处理与手动全量重跑使用。"""
        stmt = select(Line).where(Line.is_deleted.is_(False)).order_by(Line.id)
        return list(self.db.execute(stmt).scalars())

    def create(self, *, line_code: str, name: str, remark: str | None) -> Line:
        """新建产线（FR-02）。line_code 唯一约束由数据库保证；调用方（service 层）
        负责捕获 IntegrityError 并转换成对管理员友好的"编号已存在"提示，这里只管插入。"""
        line = Line(line_code=line_code, name=name, remark=remark)
        self.db.add(line)
        self.db.flush()
        return line

    def update(self, line: Line, *, name: str, remark: str | None) -> Line:
        """更新产线档案（FR-02）。line_code 不在更新范围内，理由见 schemas/line.py 的 LineUpdate 注释。"""
        line.name = name
        line.remark = remark
        self.db.flush()
        return line

    def soft_delete(self, line: Line) -> None:
        """软删除：只标记 is_deleted，不物理删除，保留历史事件可追溯。"""
        line.is_deleted = True
        self.db.flush()

    def list_paginated(self, *, page: int, page_size: int, include_deleted: bool = False) -> tuple[list[Line], int]:
        """分页列表，供 FR-02 管理页面使用。include_deleted=False 时与 get_by_code 口径一致，
        只看未软删除的产线；管理端如果需要"查看已删除产线"这类排查功能，可以传 True，
        本期页面默认不传，先只暴露"当前有效产线"这一种视图。"""
        stmt = select(Line)
        count_stmt = select(func.count()).select_from(Line)
        if not include_deleted:
            stmt = stmt.where(Line.is_deleted.is_(False))
            count_stmt = count_stmt.where(Line.is_deleted.is_(False))
        total = self.db.execute(count_stmt).scalar_one()
        stmt = stmt.order_by(Line.id).offset((page - 1) * page_size).limit(page_size)
        items = list(self.db.execute(stmt).scalars())
        return items, total

    def count_active(self) -> int:
        """未软删除产线总数，供仪表盘统计卡使用（FR-10）。"""
        stmt = select(func.count()).select_from(Line).where(Line.is_deleted.is_(False))
        return self.db.execute(stmt).scalar_one()
