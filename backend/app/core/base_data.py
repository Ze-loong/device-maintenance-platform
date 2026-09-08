"""业务基础数据加载器：读取 config/base_data.yaml 并转换成方便查询的内存结构。
对应 FR-14 最简实现——设备类型/位置/事件类型/画像维度映射等业务规则放配置文件，
代码只在启动时加载一次并做基本结构校验，不在每次请求时重复读文件。
"""
from functools import lru_cache
from pathlib import Path

import yaml

from app.core.config import BACKEND_DIR

CONFIG_PATH = BACKEND_DIR / "config" / "base_data.yaml"

# 五个画像维度是提示词模板与数据库表结构共同定死的枚举，不放进可配置文件——
# 这是模型输出契约的一部分，改动需要同时改提示词、Pydantic 校验和本文件，不是"业务规则"层面的配置项。
PROFILE_DIMENSIONS = ("运行时长规律", "振动特征", "启停冲击模式", "温度趋势", "异响/异常记录")
# 温度趋势与异响/异常记录沿用原来的无时间窗口约定，本轮不改变 time_windows 结构。
DIMENSIONS_WITHOUT_TIME_WINDOWS = ("温度趋势", "异响/异常记录")


@lru_cache(maxsize=1)
def load_base_data() -> dict:
    """加载并缓存 base_data.yaml；同一进程内多次调用只读一次磁盘。
    lru_cache 会缓存到进程生命周期结束，测试如需替换配置内容需自行清理缓存
    （load_base_data.cache_clear()），生产环境不会频繁改配置文件所以不需要热重载。
    """
    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    _validate(data)
    return data


def _validate(data: dict) -> None:
    """做最基本的结构校验，配置写错时启动阶段就报错，而不是运行到一半才发现字段缺失。"""
    required_keys = {"device_types", "locations", "event_types", "dimension_mapping", "dimension_fallback", "confidence_time_tolerance_minutes", "confidence_lookback_days", "profile_max_sample_events"}
    missing = required_keys - data.keys()
    if missing:
        raise ValueError(f"base_data.yaml 缺少必需字段: {missing}")
    fallback_dims = set(data["dimension_fallback"])
    if not fallback_dims.issubset(set(PROFILE_DIMENSIONS)):
        raise ValueError(f"dimension_fallback 包含未知维度: {fallback_dims - set(PROFILE_DIMENSIONS)}")
    for key, dims in data["dimension_mapping"].items():
        unknown = set(dims) - set(PROFILE_DIMENSIONS)
        if unknown:
            raise ValueError(f"dimension_mapping[{key!r}] 包含未知维度: {unknown}")


def get_dimensions_for_event(location: str, event_type: str) -> list[str]:
    """超限事件直接命中指标维度；其余事件按位置查表，查不到时使用兜底维度。"""
    if event_type == "vibration_alert":
        return ["振动特征"]
    if event_type == "temperature_alert":
        return ["温度趋势"]
    data = load_base_data()
    key = f"{location}:{event_type}"
    return list(data["dimension_mapping"].get(key, data["dimension_fallback"]))


def get_confidence_time_tolerance_minutes() -> int:
    """置信度算法"时间规律吻合"判断用的容差分钟数，可调参数。"""
    return int(load_base_data()["confidence_time_tolerance_minutes"])


def get_confidence_lookback_days() -> int:
    """置信度算法检索历史画像分段的窗口天数。"""
    return int(load_base_data()["confidence_lookback_days"])


def get_profile_max_sample_events() -> int:
    """画像生成超量抽样阈值（阶段四 抽样规则）。"""
    return int(load_base_data()["profile_max_sample_events"])


def normalize_location_code(value: str | None) -> str | None:
    """把模型可能返回的中文位置名称还原为配置中的代码，保证规则匹配稳定。"""
    if value is None:
        return None
    for item in load_base_data()["locations"]:
        if value == item["code"] or value == item["name"] or value in item["name"].split("/"):
            return item["code"]
    return value


def list_device_types() -> list[dict]:
    """设备类型清单（code+name），供产线/设备管理页面的下拉选项使用（FR-03）。"""
    return list(load_base_data()["device_types"])


def list_locations() -> list[dict]:
    """安装位置清单（code+name），供产线/设备管理页面的下拉选项使用（FR-03）。"""
    return list(load_base_data()["locations"])
