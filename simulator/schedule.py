"""独立模拟器的产线、传感器与风机运行窗口配置，不依赖后端代码。

两条产线分别模拟分段白班和频繁间歇运行；时间均为北京时间。
数值与窗口仅用于演示数据，不代表工业设备的安全标准。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceSpec:
    """传感器编号、类型、安装位置和名称。"""
    device_code: str
    device_type: str
    location: str
    name: str


@dataclass(frozen=True)
class RunWindow:
    """由指定传感器代报风机启动与停机，避免同位置多传感器重复计数。"""
    device_code: str
    start: str  # 北京时间 HH:MM
    end: str
    day_type: str  # weekday / weekend
    activity: str


@dataclass(frozen=True)
class LineSchedule:
    """一条产线的档案、设备与运行计划。"""
    line_code: str
    line_name: str
    remark: str
    devices: list[DeviceSpec]
    run_windows: list[RunWindow]
    reading_interval_minutes: int = 30


def _standard_devices(code: str) -> list[DeviceSpec]:
    """每条产线六个传感器，覆盖三种类型和五个位置。"""
    return [
        DeviceSpec(f"{code}-A-VIB", "vibration", "workshop_a", "车间A风机振动"),
        DeviceSpec(f"{code}-A-TEMP", "temperature", "workshop_a", "车间A风机温度"),
        DeviceSpec(f"{code}-B-VIB", "vibration", "workshop_b", "车间B风机振动"),
        DeviceSpec(f"{code}-TOWER-TEMP", "temperature", "cooling_tower", "冷却塔风机温度"),
        DeviceSpec(f"{code}-STORE-SPEED", "speed", "warehouse", "仓库风机转速"),
        DeviceSpec(f"{code}-OUT-VIB", "vibration", "outdoor", "室外风机振动"),
    ]


def _run_windows(code: str, intermittent: bool) -> list[RunWindow]:
    """白班每日两段；间歇线每日六段，周末缩短运行时长。"""
    windows = []
    for day_type in ("weekday", "weekend"):
        if intermittent:
            periods = [(f"{hour:02}:00", f"{hour:02}:{45 if day_type == 'weekday' else 20}")
                       for hour in (6, 9, 12, 15, 18, 21)]
        else:
            periods = [("07:00", "12:00"), ("13:00", "19:00")] if day_type == "weekday" else [("09:00", "11:00"), ("14:00", "16:00")]
        for suffix in ("A-VIB", "B-VIB", "TOWER-TEMP", "STORE-SPEED", "OUT-VIB"):
            for start, end in periods:
                windows.append(RunWindow(f"{code}-{suffix}", start, end, day_type,
                                         "间歇通风" if intermittent else "分段白班运行"))
    return windows


LINES: list[LineSchedule] = [
    LineSchedule("L001", "1号产线", "分段白班风机，周末缩短运行", _standard_devices("L001"), _run_windows("L001", False)),
    LineSchedule("L002", "2号产线", "间歇通风风机，每日六次启停", _standard_devices("L002"), _run_windows("L002", True)),
]
