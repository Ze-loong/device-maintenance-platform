"""画像定时任务：每天北京时间 00:30 为全部产线生成前一天画像。"""
import logging
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.timeutil import to_beijing

logger = logging.getLogger("iot")


def run_all_profiles(profile_service, target_date, trigger: str) -> dict:
    """调度入口只调用 service，不直接操作数据库或编写业务规则。"""
    return profile_service.generate_all(target_date, trigger)


def scheduled_job(profile_service) -> None:
    """调度器入口：按北京时间计算前一天日期。"""
    from datetime import datetime, timezone
    target_date = (to_beijing(datetime.now(timezone.utc)) - timedelta(days=1)).date()
    run_all_profiles(profile_service, target_date, "scheduled")


def create_scheduler(profile_service) -> BackgroundScheduler:
    """创建但不启动调度器，由 FastAPI lifespan 管理启停。"""
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(scheduled_job, "cron", hour=0, minute=30, args=[profile_service], id="daily-profile", replace_existing=True)
    return scheduler
