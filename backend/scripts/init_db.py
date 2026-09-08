r"""一次性建表脚本：读取配置里的 DATABASE_URL，对全部 9 张表执行 create_all。
本项目不用 alembic，迁移工具列入二期事项；表结构变化目前通过
"删库重建"或手工 ALTER 解决，当前数据量小，这个代价可以接受。

用法（项目根目录执行，使用共享 .venv）：
    D:\Claude\Project\ai\ai\.venv\Scripts\python.exe backend/scripts/init_db.py
"""
import logging
import sys
from pathlib import Path

# 独立脚本运行时 backend/ 不在 sys.path 里，需要手动加入才能 import app.*。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.models import Base  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

logger = logging.getLogger("iot")


def main():
    """创建全部尚不存在的表；已存在的表不会被修改（create_all 只补建缺失的表，不做迁移）。"""
    setup_logging()
    settings = Settings()
    engine = create_engine(settings.database_url.get_secret_value())
    Base.metadata.create_all(engine)
    table_names = sorted(Base.metadata.tables.keys())
    logger.info("建表完成，共 %d 张表：%s", len(table_names), ", ".join(table_names))
    print(f"建表完成，共 {len(table_names)} 张表：{', '.join(table_names)}")


if __name__ == "__main__":
    main()
