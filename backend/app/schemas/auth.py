"""FR-01 管理员登录接口的数据契约。"""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录表单提交的数据。"""
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    """登录成功的响应；会话令牌本身通过 httponly Cookie 下发，不在响应体里重复返回——
    响应体带上令牌字符串对前端 JS 没有实际用途，反而多一个可能被脚本读取的暴露面。"""
    status: str
    username: str
