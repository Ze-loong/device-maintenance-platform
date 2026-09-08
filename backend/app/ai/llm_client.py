"""大模型适配层：封装 OpenAI 兼容接口、输出校验和安全异常转换。
业务层（inference_service / profile_service）只接收 InferenceResult / ProfileGenerationResult
或 InferenceError，不依赖供应商响应结构，也不直接拼接提示词字符串。
"""
import json
import logging
import time

from openai import OpenAI, OpenAIError
from pydantic import ValidationError

from app.ai.prompts import INFERENCE_SYSTEM_PROMPT, PROFILE_SYSTEM_PROMPT, InferenceResult, ProfileGenerationResult
from app.ai.sanitized_context import SanitizedLineContext
from app.core.base_data import PROFILE_DIMENSIONS
from app.core.timeutil import to_beijing_hhmm

logger = logging.getLogger("iot")


class InferenceError(Exception):
    """传递可安全记录的失败原因，避免携带第三方完整响应或凭据。
    画像生成与实时推理共用这一个异常类型——调用方（profile_service/inference_service）
    分别有自己的降级/失败处理逻辑，不需要在异常类型上再区分场景。
    """


class LLMClient:
    """管理可复用的 HTTP 客户端，将业务输入转换成模型请求。"""

    def __init__(self, settings):
        """根据配置创建客户端；此时不发请求，实际推理由 infer/generate_profile 执行。"""
        self.settings = settings
        # SDK 对可重试错误最多额外尝试 2 次；认证失败一般不重试，总耗时可能超过单次超时。
        self.client = OpenAI(api_key=settings.deepseek_api_key.get_secret_value(), base_url=settings.deepseek_base_url, timeout=settings.llm_timeout_seconds, max_retries=2)

    def _chat_json(self, *, system_prompt: str, user_payload: dict, max_tokens: int, disable_thinking: bool = False):
        """统一的"发一次 JSON 模式请求并记录耗时/用量"逻辑，画像生成与实时推理共用。
        只做传输层的事，不理解 user_payload 的业务含义；返回模型原始回复字符串。
        接口错误统一转换为 InferenceError，调用方不需要关心是哪种 OpenAIError 子类。
        """
        started = time.monotonic()
        payload_text = json.dumps(user_payload, ensure_ascii=False)
        # 两类结构化请求均关闭 V4 思考模式，避免推理耗尽额度却未输出 JSON；其他模型不传私有参数。
        options = {"extra_body": {"thinking": {"type": "disabled"}}} if disable_thinking and self.settings.llm_model.startswith("deepseek-v4") else {}
        try:
            response = self.client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": payload_text}],
                response_format={"type": "json_object"},
                # 比 SDK 默认值低，减少 JSON 格式波动和幻觉风险，同时保留一点自然语言变化度。
                temperature=0.4,
                max_tokens=max_tokens,
                **options,
            )
            content = response.choices[0].message.content or ""
        except (OpenAIError, IndexError) as exc:
            raise InferenceError(f"大模型调用或输出校验失败（{type(exc).__name__}）") from None
        logger.info("大模型完成 耗时=%.3fs token用量=%s", time.monotonic() - started, response.usage.model_dump() if response.usage else None)
        return content

    def infer(self, context: SanitizedLineContext, event, matched_segments: list[dict]) -> InferenceResult:
        """实时推理：输入脱敏产线上下文 + 当前事件关键字段 + 命中的历史画像片段（仅 dimension+content）。
        不传 time_windows 给模型——置信度判断完全由规则程序独立完成，
        塞给模型只会增加它误以为需要自己判断时间吻合的风险。
        event 是 schemas.mqtt.UplinkEvent（或等价对象），只读取其中允许流向大模型的字段。
        """
        user_payload = {
            "line_code": context.line_code,
            "event": {
                "device_type": event.device_type,
                "location": event.location,
                "event_type": event.event_type,
                "value": event.value,
                "occurred_at_beijing": to_beijing_hhmm(event.occurred_at),
            },
            # 检索结果为空时明确写空数组；提示词硬性规则要求模型据此说明"暂无历史画像"。
            "profile_segments": matched_segments,
        }
        # D6 带画像实测连 2000 上限也可能全耗在思考中，因此让额度直接用于预测 JSON。
        content = self._chat_json(system_prompt=INFERENCE_SYSTEM_PROMPT, user_payload=user_payload, max_tokens=2000, disable_thinking=True)
        try:
            return InferenceResult.model_validate_json(content)
        except ValidationError as exc:
            raise InferenceError(f"大模型调用或输出校验失败（{type(exc).__name__}）") from None

    def generate_profile(self, context: SanitizedLineContext, sampled_events: list[dict]) -> ProfileGenerationResult:
        """画像生成：输入脱敏产线上下文 + 抽样后的当天事件列表。
        Pydantic 的 Literal 只能约束单条记录的维度名合法，不能保证五个维度"恰好各出现一次、
        不重复不遗漏"，这里在 Pydantic 校验通过后再做一次集合比对。
        """
        user_payload = {"line_code": context.line_code, "events": sampled_events}
        # D6 实测连 16000 上限也可能全耗在推理中；画像明确关闭 V4 思考模式，额度用于结构化正文。
        content = self._chat_json(system_prompt=PROFILE_SYSTEM_PROMPT, user_payload=user_payload, max_tokens=16000, disable_thinking=True)
        try:
            result = ProfileGenerationResult.model_validate_json(content)
        except ValidationError as exc:
            raise InferenceError(f"大模型调用或输出校验失败（{type(exc).__name__}）") from None
        actual_dims = {d.dimension for d in result.dimensions}
        if actual_dims != set(PROFILE_DIMENSIONS):
            # 健壮性优先于严格性：宁可整份画像生成失败（该产线当天画像缺失），
            # 也不接受维度缺失/重复的半成品数据进入数据库。
            raise InferenceError("大模型调用或输出校验失败（DimensionMismatch）")
        return result

    def close(self):
        """关闭底层 HTTP 连接池，由应用退出清理流程调用。"""
        self.client.close()
