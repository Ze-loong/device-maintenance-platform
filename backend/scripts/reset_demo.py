"""清空验收演示的历史事实数据，同时保留注册数据与管理员账号。

脚本只截断业务事实表，不删除表结构。用于反复演示“清库、回填、画像、预测”流程，
因此 line、device 和 admin_user 不在清理范围内。
"""
import argparse
import sys
from pathlib import Path

# 与 init_db.py、create_admin.py 保持一致，让按文件路径执行的脚本也能导入后端包。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.db import init_engine  # noqa: E402


# 子表排在主表前，便于读者理解外键依赖；CASCADE 负责处理实际引用关系。
TABLES_TO_TRUNCATE = [
    "prediction_profile_segment",
    "prediction",
    "profile_segment",
    "profile",
    "event",
    "unregistered_alert",
]


def main():
    """确认清理范围后，在一个数据库事务中截断六张事实表。"""
    parser = argparse.ArgumentParser(description="清空业务事实表，供验收演示反复使用")
    parser.add_argument("--yes", action="store_true", help="跳过确认提示，直接执行（供脚本化调用）")
    args = parser.parse_args()
    if not args.yes:
        answer = input(
            f"将清空以下表的全部数据：{', '.join(TABLES_TO_TRUNCATE)}\n"
            "不影响 line/device 注册数据与 admin_user 账号。确认执行？(yes/no): "
        )
        if answer.strip().lower() != "yes":
            print("已取消。")
            sys.exit(0)

    settings = Settings()
    engine = init_engine(settings.database_url.get_secret_value())
    with engine.begin() as conn:
        # 重置自增编号便于重复演示；CASCADE 避免遗漏关联表而导致清理失败。
        conn.execute(text(f"TRUNCATE TABLE {', '.join(TABLES_TO_TRUNCATE)} RESTART IDENTITY CASCADE"))
    print("已清空事实表，line/device 注册与管理员账号保留。")


if __name__ == "__main__":
    main()
