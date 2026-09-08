"""ORM 基类：全部表模型共用同一个 SQLAlchemy 声明基类，
scripts/init_db.py 靠这个基类的 metadata 拿到全部表定义并统一建表。
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """项目内所有 models/*.py 表定义都继承这个基类。"""
