"""FR-12 独立模拟网关：经 REST 注册设备，经 MQTT 回填、实时上报并接收预测。"""
import argparse
from datetime import datetime, time as clock_time, timedelta, timezone
import json
import os
from pathlib import Path
import random
import threading
import time
from uuid import uuid4

import httpx
from dotenv import dotenv_values
import paho.mqtt.client as mqtt

from schedule import LINES, DeviceSpec, LineSchedule

BEIJING = timezone(timedelta(hours=8))


class Simulator:
    """持有 HTTP 会话与 MQTT 连接，串起注册、回填和实时三个阶段。"""

    def __init__(self, config: dict, interval_seconds: float, publish_delay_seconds: float = 0.02):
        self.config = config
        self.interval_seconds = interval_seconds
        # 回填有数百条消息，轻微节流可避免平台 100 条内存队列瞬时溢出；不等待预测回推。
        self.publish_delay_seconds = publish_delay_seconds
        self.http = httpx.Client(base_url=config.get("API_BASE_URL", "http://127.0.0.1:8000"), timeout=20)
        self.mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"simulator-{uuid4().hex[:10]}")
        self.mqtt.username_pw_set(config["MQTT_USERNAME"], config["MQTT_PASSWORD"])
        self.connected = threading.Event()
        self.subscribed = threading.Event()
        self.predictions: list[dict] = []
        self.mqtt.on_connect = self._on_connect
        self.mqtt.on_subscribe = self._on_subscribe
        self.mqtt.on_disconnect = self._on_disconnect
        self.mqtt.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """连接成功后订阅所有设备的下行主题。"""
        if reason_code.is_failure:
            print(f"MQTT 连接失败: {reason_code}")
            return
        self.connected.set()
        print("MQTT 已连接，正在订阅 line/+/+/prediction 预测主题")
        client.subscribe("line/+/+/prediction", qos=1)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        """记录异常断线；paho 网络循环继续运行时会自动尝试重连。"""
        self.connected.clear()
        self.subscribed.clear()
        if reason_code.is_failure:
            print(f"MQTT 连接断开，等待自动重连: {reason_code}")

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if reason_codes and all(not code.is_failure for code in reason_codes):
            self.subscribed.set()

    def _on_message(self, client, userdata, message):
        """打印真实下行内容，并保留接收时间供端到端验收计时。"""
        if message.retain:
            return
        payload = json.loads(message.payload)
        parts = message.topic.split("/")
        if len(parts) != 4 or parts[0] != "line" or parts[3] != "prediction":
            return
        payload["received_topic"] = message.topic
        device_code = parts[2]
        payload["received_at"] = datetime.now(timezone.utc).isoformat()
        self.predictions.append(payload)
        print(f"收到预测 产线={payload.get('line_id')} 设备={device_code} 内容={payload.get('next_behavior')} 置信度={payload.get('confidence')} 时间={payload['received_at']}")

    def start(self) -> None:
        self.mqtt.connect(self.config.get("MQTT_HOST", "127.0.0.1"), int(self.config.get("MQTT_PORT", 1883)))
        self.mqtt.loop_start()
        if not self.connected.wait(10) or not self.subscribed.wait(10):
            raise RuntimeError("MQTT 连接或订阅超时")

    def stop(self) -> None:
        self.http.close()
        self.mqtt.disconnect()
        self.mqtt.loop_stop()

    def register(self) -> None:
        """先登录，再通过平台 REST API 幂等注册 2 条产线和 12 个传感器。"""
        response = self.http.post("/api/auth/login", json={"username": self.config["ADMIN_USERNAME"], "password": self.config["ADMIN_PASSWORD"]})
        response.raise_for_status()
        known = {item["line_code"]: item for item in self.http.get("/api/lines", params={"page": 1, "page_size": 200}).raise_for_status().json()["items"]}
        for line in LINES:
            if line.line_code not in known:
                result = self.http.post("/api/lines", json={"line_code": line.line_code, "name": line.line_name, "remark": line.remark})
                if result.status_code != 409:
                    result.raise_for_status()
                print(f"产线注册完成: {line.line_code}")
            else:
                print(f"产线已存在，跳过: {line.line_code}")
        lines = {item["line_code"]: item for item in self.http.get("/api/lines", params={"page": 1, "page_size": 200}).json()["items"]}
        known_devices = {item["device_code"] for item in self.http.get("/api/devices", params={"page": 1, "page_size": 200}).raise_for_status().json()["items"]}
        for line in LINES:
            for device in line.devices:
                if device.device_code in known_devices:
                    print(f"设备已存在，跳过: {device.device_code}")
                    continue
                result = self.http.post("/api/devices", json={"device_code": device.device_code, "line_id": lines[line.line_code]["id"], "device_type": device.device_type, "location": device.location, "name": device.name})
                if result.status_code != 409:
                    result.raise_for_status()
                print(f"设备注册完成: {device.device_code}")

    @staticmethod
    def _event(line: LineSchedule, device: DeviceSpec, event_type: str, value: float, occurred_at: datetime, is_backfill: bool) -> dict:
        return {"schema_version": "1.0", "line_id": line.line_code, "device_id": device.device_code, "device_type": device.device_type, "location": device.location, "event_type": event_type, "value": value, "extra": {}, "occurred_at": occurred_at.astimezone(timezone.utc).isoformat(), "is_backfill": is_backfill}

    def publish(self, payload: dict) -> None:
        topic = f"line/{payload['line_id']}/{payload['device_id']}/event"
        self.mqtt.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1).wait_for_publish(timeout=10)
        if payload["is_backfill"] and self.publish_delay_seconds:
            time.sleep(self.publish_delay_seconds)

    def _publish_reading(self, line: LineSchedule, device: DeviceSpec, occurred_at: datetime, is_backfill: bool) -> int:
        """每次读数有 2% 概率模拟超限，同时发送读数和对应告警；阈值仅用于演示。"""
        alert = random.random() < 0.02
        if device.device_type == "temperature":
            value = round(random.uniform(85, 95) if alert else random.uniform(45, 70), 1)
            event_type = "temperature_alert"
        else:
            value = round(random.uniform(8, 12) if alert else random.uniform(1, 4), 2)
            event_type = "vibration_alert"
        self.publish(self._event(line, device, "sensor_reading", value, occurred_at, is_backfill))
        if alert:
            self.publish(self._event(line, device, event_type, value, occurred_at, is_backfill))
        return 2 if alert else 1

    def backfill(self) -> int:
        """生成北京时间昨天的全部运行边界与传感器读数，QoS1 批量发布。"""
        target = datetime.now(BEIJING).date() - timedelta(days=1)
        day_type = "weekend" if target.weekday() >= 5 else "weekday"
        count = 0
        for line in LINES:
            devices = {item.device_code: item for item in line.devices}
            for window in line.run_windows:
                if window.day_type != day_type:
                    continue
                device = devices[window.device_code]
                for at, event_type, value in ((window.start, "fan_started", 1), (window.end, "fan_stopped", 0)):
                    local = datetime.combine(target, clock_time.fromisoformat(at), tzinfo=BEIJING)
                    self.publish(self._event(line, device, event_type, value, local, True)); count += 1
            for device in (item for item in line.devices if item.device_type in {"temperature", "vibration"}):
                for minute in range(0, 24 * 60, line.reading_interval_minutes):
                    local = datetime.combine(target, clock_time.min, tzinfo=BEIJING) + timedelta(minutes=minute)
                    count += self._publish_reading(line, device, local, True)
        print(f"回填发布完成: 日期={target} 事件数={count}")
        return count

    def emit_once(self, line_code: str = "L001") -> float:
        """立即发送一条实时风机启动事件并等待对应设备下一条回推，供验收和演示。"""
        line = next(item for item in LINES if item.line_code == line_code)
        device = next(item for item in line.devices if item.device_type == "vibration" and item.location == "workshop_a")
        before = len(self.predictions)
        started = time.monotonic()
        self.publish(self._event(line, device, "fan_started", 1, datetime.now(timezone.utc), False))
        deadline = time.monotonic() + 90
        topic = f"line/{line_code}/{device.device_code}/prediction"
        def received_target():
            return any(item.get("received_topic") == topic for item in self.predictions[before:])
        while not received_target() and time.monotonic() < deadline:
            time.sleep(0.1)
        if not received_target():
            raise TimeoutError("等待预测回推超时")
        elapsed = time.monotonic() - started
        print(f"实时链路完成: 产线={line_code} 耗时={elapsed:.3f}秒")
        return elapsed

    def run_realtime(self) -> None:
        """按真实北京时间检查运行边界，并持续发送振动和温度周期读数。"""
        previous = datetime.now(BEIJING)
        next_environment = {line.line_code: previous for line in LINES}
        while True:
            time.sleep(self.interval_seconds)
            current = datetime.now(BEIJING)
            day_type = "weekend" if current.weekday() >= 5 else "weekday"
            for line in LINES:
                devices = {item.device_code: item for item in line.devices}
                for window in line.run_windows:
                    if window.day_type != day_type:
                        continue
                    for at, event_type, value in ((window.start, "fan_started", 1), (window.end, "fan_stopped", 0)):
                        boundary = datetime.combine(current.date(), clock_time.fromisoformat(at), tzinfo=BEIJING)
                        if previous < boundary <= current:
                            self.publish(self._event(line, devices[window.device_code], event_type, value, boundary, False))
                if current >= next_environment[line.line_code]:
                    for device in (item for item in line.devices if item.device_type in {"temperature", "vibration"}):
                        self._publish_reading(line, device, current, False)
                    next_environment[line.line_code] = current + timedelta(minutes=line.reading_interval_minutes)
            previous = current


def main() -> None:
    parser = argparse.ArgumentParser(description="设备预测性维护 FR-12 模拟器")
    parser.add_argument("--backfill-only", action="store_true", help="完成注册和昨日回填后退出")
    parser.add_argument("--emit-once", action="store_true", help="回填后立即发送一条实时风机启动事件并等待回推")
    parser.add_argument("--skip-backfill", action="store_true", help="跳过昨日回填，便于单独验证实时链路")
    parser.add_argument("--interval", type=float, default=30, help="实时运行边界检查间隔（秒）")
    parser.add_argument("--publish-delay", type=float, default=0.02, help="回填消息间最小间隔（秒）")
    args = parser.parse_args()
    values = {**dotenv_values(Path(__file__).with_name(".env")), **os.environ}
    required = ["MQTT_USERNAME", "MQTT_PASSWORD", "ADMIN_USERNAME", "ADMIN_PASSWORD"]
    if missing := [key for key in required if not values.get(key)]:
        raise SystemExit(f"模拟器缺少配置: {', '.join(missing)}")
    simulator = Simulator(values, args.interval, args.publish_delay)
    simulator.start()
    try:
        simulator.register()
        if not args.skip_backfill:
            simulator.backfill()
        if args.emit_once:
            simulator.emit_once()
        if not args.backfill_only and not args.emit_once:
            simulator.run_realtime()
    finally:
        simulator.stop()


if __name__ == "__main__":
    main()
