"""统一配置入口，供应用装配和各基础组件使用。
以本文件位置定位 backend/.env，避免从不同工作目录启动时读错配置。"""
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# parents[2] 从 core/config.py 向上定位到 backend，项目文件夹改名不影响此定位。
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """将环境配置转换为带类型的字段。
    优先级为：构造时显式传值 > 进程环境变量 > backend/.env > 字段默认值。
    SecretStr 避免常规打印时暴露密码，但不是磁盘加密。"""

    # 读取 UTF-8 配置；忽略 .env 内不属于 Settings 的其他配置项。
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")
    app_env: str = "dev"
    # 数据库连接字符串也可能含密码，因此同样用 SecretStr。
    database_url: SecretStr = SecretStr("")
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_username: str = "platform"
    # 没有默认值的字段必须提供；仅在调用第三方客户端时提取真实字符串。
    mqtt_password: SecretStr
    deepseek_api_key: SecretStr
    deepseek_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-v4-flash"
    # gt=0 拒绝零或负数；这是客户端超时配置，不是含重试的端到端总时限。
    llm_timeout_seconds: float = Field(default=20, gt=0)
