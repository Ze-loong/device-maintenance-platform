"""profile 表持久化：按 (line_id, profile_date) upsert（FR-08"重复生成覆盖当日旧画像"）。"""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.line import Line
from app.models.profile import Profile
from app.models.profile_segment import ProfileSegment


class ProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_line_and_date(self, line_id: int, profile_date: date) -> Profile | None:
        stmt = select(Profile).where(Profile.line_id == line_id, Profile.profile_date == profile_date)
        return self.db.execute(stmt).scalar_one_or_none()

    def upsert(self, *, line_id: int, profile_date: date, summary: str | None, full_content: str, source_event_count: int, generation_trigger: str) -> Profile:
        """存在则覆盖当日旧画像内容（同时级联删除旧的 profile_segment，避免新旧分段混杂），
        不存在则新建。这里不直接 commit，事务边界交给调用方的 session_scope。
        """
        existing = self.get_by_line_and_date(line_id, profile_date)
        if existing is not None:
            # 先删旧分段：旧画像的维度内容与新画像不是简单的字段覆盖关系（分段数量、time_windows 都可能变化），
            # 保留旧分段会导致同一天同一维度出现新旧混杂的记录，破坏"覆盖当日旧画像"的语义。
            self.db.query(ProfileSegment).filter(ProfileSegment.profile_id == existing.id).delete()
            existing.summary = summary
            existing.full_content = full_content
            existing.source_event_count = source_event_count
            existing.generation_trigger = generation_trigger
            self.db.flush()
            return existing
        profile = Profile(line_id=line_id, profile_date=profile_date, summary=summary, full_content=full_content, source_event_count=source_event_count, generation_trigger=generation_trigger)
        self.db.add(profile)
        self.db.flush()
        return profile

    def list_paginated(self, *, line_code: str | None = None, page: int = 1, page_size: int = 20):
        """FR-09 画像列表查询：可选按产线编号过滤，按 profile_date 降序（最新的画像排在前面）。
        返回的是 (Profile, line_code) 元组列表——Profile 模型本身没有 line_code 快照字段
        （profile 表没有像 event 表那样冗余这个字段），这里通过 JOIN line 表补上，
        列表页展示需要，但不想为此单独给 Profile 模型加字段（产线软删除的边界情况处理见下方过滤条件）。
        """
        stmt = select(Profile, Line.line_code).join(Line, Profile.line_id == Line.id)
        count_stmt = select(func.count()).select_from(Profile).join(Line, Profile.line_id == Line.id)
        if line_code:
            stmt = stmt.where(Line.line_code == line_code)
            count_stmt = count_stmt.where(Line.line_code == line_code)
        total = self.db.execute(count_stmt).scalar_one()
        stmt = stmt.order_by(Profile.profile_date.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = []
        for profile, line_code_value in self.db.execute(stmt):
            profile.line_code = line_code_value
            rows.append(profile)
        return rows, total

    def get_by_id_with_segments(self, profile_id: int):
        """FR-09 画像详情：按主键取一条画像 + 其全部维度分段，供"全文查看"页面展示。
        返回 None 表示画像不存在（比如 id 是被伪造的）；调用方（service/API 路由）负责转 404。"""
        profile = self.db.get(Profile, profile_id)
        if profile is None:
            return None, []
        line = self.db.get(Line, profile.line_id)
        profile.line_code = line.line_code if line else "未知"
        segments = list(
            self.db.execute(
                select(ProfileSegment).where(ProfileSegment.profile_id == profile_id).order_by(ProfileSegment.id)
            ).scalars()
        )
        return profile, segments

    def count_total(self) -> int:
        """画像总数，供仪表盘统计卡使用（FR-10）。"""
        return self.db.execute(select(func.count()).select_from(Profile)).scalar_one()
