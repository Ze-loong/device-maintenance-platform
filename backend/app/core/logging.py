"""统一配置 iot 日志器，供 MQTT、业务服务和大模型适配层共用。
由应用启动时调用，日志同时写控制台和后端 logs/app.log。"""
import logging
from logging.handlers import RotatingFileHandler

from app.core.config import BACKEND_DIR


def setup_logging():
    """初始化共享日志器，无返回值；会创建日志目录和文件处理器。
    重复调用时不重复添加处理器，避免同一条消息输出多次。"""
    directory = BACKEND_DIR / "logs"
    directory.mkdir(exist_ok=True)
    logger = logging.getLogger("iot")
    # INFO 及更高等级会输出，DEBUG 默认不输出。
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        # 文件达到约 2 MB 时轮转，最多留 3 个备份；控制台编码由启动环境决定。
        for handler in (logging.StreamHandler(), RotatingFileHandler(directory / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")):
            handler.setFormatter(formatter)
            logger.addHandler(handler)
    # 不继续传给根日志器，避免与 uvicorn 的日志配置叠加造成重复输出。
    logger.propagate = False
