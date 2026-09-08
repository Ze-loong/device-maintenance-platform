"""独立的一次性模拟网关，不导入后端业务代码。
正常模式先订阅预测主题，再上报固定事件、打印回推并退出。
匿名模式只检查 Broker 是否拒绝无账号连接，不发送事件。"""
import argparse
import json
from pathlib import Path
import threading
import time
from uuid import uuid4

from dotenv import dotenv_values
import paho.mqtt.client as mqtt


def run(timeout=90, anonymous=False, line_id="L001", device_id="L001-A-VIB"):
    """连接 Broker 并返回记录连接结果、预测与耗时的字典。
    timeout 是发布后等待回推的秒数；anonymous 为真时仅验证匿名拒绝。
    连接、订阅或回推失败会抛异常；进入 try 后无论结果如何都会断开连接。"""
    # 按脚本位置读取模拟器自己的 .env，不依赖当前终端所在目录。
    config = dotenv_values(Path(__file__).with_name(".env"))
    # 三个线程信号分别表示订阅完成、收到预测、收到连接结果，避免靠固定睡眠猜状态。
    subscribed, received, connected = threading.Event(), threading.Event(), threading.Event()
    state = {}
    # 每次使用随机客户端 ID，避免两个测试客户端因同名而互相断开。
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"demo-{uuid4().hex[:12]}")
    if not anonymous:
        client.username_pw_set(config["MQTT_USERNAME"], config["MQTT_PASSWORD"])

    def on_connect(client, userdata, flags, reason_code, properties):
        """记录连接是否被拒绝并通知主线程；成功后申请订阅设备预测。"""
        state["connection"] = str(reason_code)
        state["rejected"] = reason_code.is_failure
        connected.set()
        if not reason_code.is_failure:
            client.subscribe(f"line/{line_id}/{device_id}/prediction", qos=1)

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        """收到成功的订阅确认后通知主线程，保证发布事件前已准备好接收。"""
        if reason_codes and all(not code.is_failure for code in reason_codes):
            subscribed.set()

    def on_message(client, userdata, message):
        """保存非保留消息并唤醒等待线程。
        本 Demo 只等待该设备下一条预测，没有并发事件的请求关联标识。"""
        # 忽略订阅时收到的历史保留消息；不能排除其他并发上报产生的新预测。
        if not message.retain:
            state["prediction"] = json.loads(message.payload)
            received.set()

    client.on_connect, client.on_subscribe, client.on_message = on_connect, on_subscribe, on_message
    client.connect(config.get("MQTT_HOST", "127.0.0.1"), int(config.get("MQTT_PORT", "1883")))
    client.loop_start()
    try:
        if not connected.wait(10):
            raise TimeoutError("MQTT connection timed out")
        if anonymous:
            print(json.dumps({"anonymous_rejected": state["rejected"], "reason": state["connection"]}))
            if not state["rejected"]:
                raise RuntimeError("Anonymous connection unexpectedly accepted")
            return state
        if not subscribed.wait(10):
            raise RuntimeError("MQTT subscription failed")
        # 固定车间A风机启动场景便于复现；occurred_at 使用当前 UTC 时间。
        # 当前时间可避免重复运行脚本时命中 QoS1 去重；产线和设备可由验收命令指定。
        from datetime import datetime, timezone
        event = {"line_id": line_id, "device_id": device_id, "device_type": "vibration", "location": "workshop_a", "event_type": "fan_started", "value": 1, "extra": {}, "occurred_at": datetime.now(timezone.utc).isoformat()}
        # 端到端耗时从发布前计时，直到本客户端收到预测，包含网络与推理等待。
        started = time.monotonic()
        client.publish(f"line/{line_id}/{device_id}/event", json.dumps(event), qos=1).wait_for_publish(timeout=10)
        if not received.wait(timeout):
            raise TimeoutError("No prediction received")
        state["elapsed_seconds"] = round(time.monotonic() - started, 3)
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return state
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    # 仅直接运行此文件时解析命令行；被集成脚本导入时只提供 run 函数。
    parser = argparse.ArgumentParser()
    parser.add_argument("--anonymous", action="store_true")
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--line-id", default="L001")
    parser.add_argument("--device-id", default="L001-A-VIB")
    args = parser.parse_args()
    run(args.timeout, args.anonymous, args.line_id, args.device_id)
