"""时区转换工具：统一 UTC 存储、按需转北京时间展示/传给大模型。
中国不实行夏令时，北京时间固定为 UTC+8，用固定偏移量换算即可，
不需要引入 zoneinfo/tzdata 依赖（Windows 上 zoneinfo 默认不带 IANA 时区数据库，
额外装 tzdata 包纯粹为了这一个固定偏移不划算）。
"""
from datetime import datetime, timedelta, timezone

BEIJING_OFFSET = timedelta(hours=8)


def to_beijing(dt: datetime) -> datetime:
    """把带时区的 UTC（或其他时区）时间转换成北京时间（tzinfo 固定为 +08:00）。
    传入 naive datetime（没有 tzinfo）视为已经是 UTC，先补上 UTC 标记再换算，
    避免调用方漏加时区时静默产生错误结果。
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(BEIJING_OFFSET))


def to_beijing_hhmm(dt: datetime) -> str:
    """转换成北京时间的 HH:MM 字符串，供画像生成/实时推理提示词直接使用
    。
    """
    return to_beijing(dt).strftime("%H:%M")


def is_beijing_weekend(dt: datetime) -> bool:
    """按北京时间判断某一时刻所在的日期是否为周末（周六、周日）。
    置信度算法和画像生成的 day_type 判断都依赖这个，
    统一用北京时间而不是服务器本地时间/UTC，避免在 UTC 深夜时段（对应北京时间已经是第二天）判断错日期。
    """
    return to_beijing(dt).weekday() >= 5
