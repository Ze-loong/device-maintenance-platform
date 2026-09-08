"""大模型输入的显式白名单：集中定义允许传入的产线信息。
即使工业风机场景的信息敏感度更低，也只向大模型提供必要的产线编号，
避免数据库模型字段的增减直接扩散到大模型输入边界：
所有会流向大模型的代码路径（profile_service 生成画像、inference_service 实时推理），
参数类型强制使用本模块的 SanitizedLineContext，不能直接传递 Line 数据库模型对象。
"""
from pydantic import BaseModel


class SanitizedLineContext(BaseModel):
    """喂给大模型的产线上下文，只携带白名单中的必要业务信息。
    任何需要向大模型发送产线相关信息的代码，只能使用这个类型，
    不能直接传递 Line 数据库模型对象。
    """
    line_code: str
    # 仅开放产线编号，不直接暴露数据库模型中的名称、备注等其他字段。
