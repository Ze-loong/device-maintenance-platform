"""数据库连接与会话管理：SQLAlchemy 引擎在应用启动时创建一次，全局复用。
本项目不用 alembic（任务清单已定案），建表统一走 scripts/init_db.py 的 create_all；
这里只负责"连接怎么建、会话怎么拿"，不包含任何业务查询（查询在 repository 层）。
"""
import logging
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger("iot")

# 模块级单例，由 init_engine() 在应用启动时赋值；避免每次请求都新建连接池。
_engine = None
_SessionFactory: sessionmaker | None = None


def init_engine(database_url: str):
    """用配置里的 DATABASE_URL 创建全局引擎和会话工厂。
    pool_pre_ping=True：借出连接前先探活，避免用到数据库重启后失效的旧连接
    （对应 NFR-01"数据库故障时不中断"精神——至少不会因为连接失效而莫名其妙报错）。
    """
    global _engine, _SessionFactory
    _engine = create_engine(database_url, pool_pre_ping=True, future=True)
    _SessionFactory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    logger.info("数据库引擎已初始化")
    return _engine


def get_engine():
    """返回全局引擎，供 init_db.py 等需要直接操作元数据的脚本使用。"""
    if _engine is None:
        raise RuntimeError("数据库引擎尚未初始化，请先调用 init_engine()")
    return _engine


@contextmanager
def session_scope():
    """提供一个自动提交/回滚的会话上下文，service 层用 with session_scope() as db: 获取会话。
    正常退出提交事务；抛异常则回滚，异常继续向上传播由调用方（如 event_service 的降级逻辑）处理；
    无论如何都会关闭会话，避免连接池泄漏。
    """
    if _SessionFactory is None:
        raise RuntimeError("数据库引擎尚未初始化，请先调用 init_engine()")
    db: Session = _SessionFactory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
