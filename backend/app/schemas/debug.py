"""FR-11 预测调试页面的数据契约。
请求体直接复用 app.schemas.mqtt.UplinkEvent（不新建一个"看起来一样但其实是另一份"的模型）——
这是保证"调试页面与 MQTT 上报走同一处理链路"最直观的证据：连输入数据结构都是同一个 Pydantic 类，
不是照抄字段搭了个相似的壳。调试页面表单只需要把管理员在页面上选择/填写的值组装成这个模型，
调用与 mqtt/client.py 完全相同的 event_service.handle_event()。
"""
from pydantic import BaseModel, Field

from app.schemas.mqtt import DownlinkPrediction


class MatchedSegmentDetail(BaseModel):
    """命中画像分段的详情，供调试页面展示完整依据。
    比 MQTT 下行 profile_refs 更完整——profile_refs 是给网关看的轻量摘要（截断+简短摘要），
    调试页面是给开发/运营人员看的，可以展示分段全文，帮助判断"这次置信度为什么是这个档位"。"""
    dimension: str
    content: str
    segment_date: str


class DebugPredictionResponse(BaseModel):
    """调试页面提交事件后的展示数据。
    prediction 为 None 且 is_duplicate=True 时，说明这条构造的事件在 (device_id, occurred_at)
    维度上与已有记录重复，被 event_service 的 QoS1 去重机制拦截、未真正触发本次推理——
    这不是 bug，是"调试页面与 MQTT 上报完全同链路"的必然结果（该去重逻辑对两个入口一视同仁）。
    页面遇到这种情况应提示管理员调整发生时间后重试，而不是让请求看起来像是"什么都没发生"。

    is_degraded 单独作为本响应的字段，而不是塞进 DownlinkPrediction——DownlinkPrediction
    是网关侧使用的 MQTT 下行数据契约，网关不需要也不应该依赖这个内部诊断字段；
    调试页面是给开发/运营人员看的内部工具，需要知道"这次是模型真实给出的低置信度，
    还是调用失败被迫降级"，这个区分对判断链路是否健康很重要，从 prediction 表的
    is_degraded 列读出即可。"""
    prediction: DownlinkPrediction | None = None
    matched_segments: list[MatchedSegmentDetail] = Field(default_factory=list)
    is_duplicate: bool = False
    is_degraded: bool = False
