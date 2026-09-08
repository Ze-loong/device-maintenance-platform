"""MQTT 消息入口层：连接 Broker、订阅上行、校验报文并发布预测。
网络线程负责回调和保活，工作线程通过队列取事件并调用业务服务。
当前是单进程 Demo：队列不落盘，也没有业务幂等去重或失败补发机制。"""
import logging
import queue
import threading

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from app.schemas.mqtt import UplinkEvent

logger = logging.getLogger("iot")


class MQTTClient:
    """封装平台侧 MQTT 连接，并通过传入的 service 处理事件。
    业务规则留在 service；本类只承担消息接入、线程调度和发布。"""
    def __init__(self, settings, service):
        """接收 Settings 和具备 handle_event 方法的业务服务，准备线程与回调。
        此时尚未连接 Broker，实际启动由 start 完成。"""
        self.settings, self.service = settings, service
        # 最多暂存 100 条事件；这是内存缓冲，进程退出会丢失，满时由入口拒绝新事件。
        self.pending = queue.Queue(maxsize=100)
        # Event 是线程间信号：stopping 通知退出，ready 表示订阅确认已收到。
        self.stopping = threading.Event()
        self.ready = threading.Event()
        # VERSION2 选择新版回调参数格式；固定客户端 ID 适合单实例，多实例会互相顶掉连接。
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="iot-platform-demo")
        self.client.username_pw_set(settings.mqtt_username, settings.mqtt_password.get_secret_value())
        # 重连失败时逐步增加等待间隔，上限 30 秒，避免不断快速重试。
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        # 把方法注册给 paho，之后由网络线程在相应事件到来时调用。
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        # daemon 线程不会独自阻止进程退出，正常退出仍由 stop 主动等待它结束。
        self.worker = threading.Thread(target=self.work, name="iot-inference", daemon=True)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        """收到 Broker 的连接确认时触发；首次连接和重连成功都会重新订阅。
        client 是 paho 客户端，reason_code 是连接结果；其余参数由回调协议提供。"""
        if reason_code.is_failure:
            logger.error("MQTT 认证或连接失败：%s", reason_code)
            return
        # 两个 + 分别匹配一个产线和设备层级；QoS 1 允许重复投递，不等于业务只执行一次。
        client.subscribe("line/+/+/event", qos=1)

    def on_subscribe(self, client, userdata, mid, reason_codes, properties):
        """收到订阅确认时触发。mid 是本次订阅报文编号，reason_codes 是各主题结果。
        只有确认订阅成功，才解除 start 中的等待。"""
        if reason_codes and all(not code.is_failure for code in reason_codes):
            self.ready.set()
            logger.info("已连接 MQTT 并订阅 line/+/+/event")

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        """连接断开时清除就绪标记；正常停机时不输出重连告警。
        自动重连由仍运行的 paho 网络循环负责。"""
        self.ready.clear()
        if not self.stopping.is_set():
            logger.warning("MQTT 连接断开，自动重连：%s", reason_code)

    def on_message(self, client, userdata, message):
        """网络线程收到报文时触发：message.topic 是主题，payload 是原始字节。
        校验格式与主题一致性后立即入队，不在回调中等待大模型。"""
        try:
            # 先限制报文字节数，再解析 JSON，避免大报文无节制占用处理资源。
            if len(message.payload) > 65536:
                raise ValueError("payload too large")
            event = UplinkEvent.model_validate_json(message.payload)
            # 主题与 JSON 内的编号必须一致；此处不是数据库注册校验或产线访问权限校验。
            if message.topic != f"line/{event.line_id}/{event.device_id}/event":
                raise ValueError("topic mismatch")
            # 不等待空位：队列满会抛 queue.Full，避免网络线程被阻塞。
            self.pending.put_nowait(event)
        except (ValidationError, ValueError, queue.Full) as exc:
            logger.warning("上行消息被拒绝：%s", type(exc).__name__)

    def work(self):
        """工作线程循环取事件、调用 service、发布预测，并等待 Broker 确认。
        单条处理失败只记录异常类型，让线程继续处理后续事件；当前没有补发。"""
        # 推理在独立线程执行，避免阻塞 MQTT 保活及下行 PUBACK。
        # 收到停止信号后仍尝试清空队列；网络断开要等工作线程结束之后才执行。
        while not self.stopping.is_set() or not self.pending.empty():
            try:
                # 短超时让空队列时的线程也能定期检查停止信号。
                event = self.pending.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                prediction = self.service.handle_event(event)
                if prediction is None:
                    # DB 唯一约束确认是 QoS1 重投后不再发布第二条预测。
                    continue
                # 下行到设备级（line_id+device_id），不是产线级：维护建议本质是单设备行为
                # （"这台风机需要检修"），必须精确路由到目标设备，网关订阅通配符 topic 后
                # 靠路径本身解析出 device_id，payload（DownlinkPrediction）不重复携带该字段，
                # 与上行"topic 负责寻址、payload 负责内容"的设计原则保持一致。
                # retain=False 不让 Broker 把本次预测保存为未来订阅者的保留消息。
                info = self.client.publish(f"line/{event.line_id}/{event.device_id}/prediction", prediction.model_dump_json(), qos=1, retain=False)
                # 等待 QoS 1 的 PUBACK，只说明 Broker 确认收到，不代表网关已经执行或处理。
                info.wait_for_publish(timeout=10)
                if not info.is_published():
                    raise TimeoutError("publish acknowledgement timed out")
                logger.info("已回推 产线=%s 设备=%s 事件=%s", event.line_id, event.device_id, prediction.event_id)
            except Exception as exc:
                logger.error("事件处理或回推失败：%s", type(exc).__name__)
            finally:
                # 标记这次取出的队列任务已结束；不是向 MQTT 确认消息，也不是落盘。
                self.pending.task_done()

    def start(self):
        """启动网络循环并等待连接及订阅成功，最多等待 15 秒。
        成功后才启动工作线程；超时清理网络资源并使应用启动失败。"""
        self.client.connect_async(self.settings.mqtt_host, self.settings.mqtt_port, keepalive=30)
        # 启动 paho 网络线程，负责连接确认、消息回调、保活及重连。
        self.client.loop_start()
        if not self.ready.wait(15):
            self.client.disconnect()
            self.client.loop_stop()
            raise RuntimeError("MQTT startup failed")
        self.worker.start()

    def stop(self):
        """发出停止信号，等待工作线程退出，再断开 MQTT。
        工作线程会尝试处理队列剩余事件；join 没有设超时，因此退出可能等待较久。"""
        self.stopping.set()
        # 等待推理和发布结束，保持 MQTT 网络线程可用以接收 PUBACK。
        self.worker.join()
        self.client.disconnect()
        self.client.loop_stop()
