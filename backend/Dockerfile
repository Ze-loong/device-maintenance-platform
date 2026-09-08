# 后端镜像定义；本机 Demo 使用共享虚拟环境，容器内则使用 Python 3.12 精简镜像。
FROM python:3.12-slim
# 后续复制、安装及启动命令均以容器内 /app 为工作目录。
WORKDIR /app
# 先复制依赖清单，业务代码变化时可复用依赖安装缓存。
COPY requirements.txt .
# 使用本机课程项目约定的镜像源，并为网络波动保留重试时间；不保留下载缓存以控制镜像体积。
RUN pip install --no-cache-dir --timeout 120 --retries 5 \
    -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
# 复制应用代码、基础数据配置和运维脚本；真实 .env 由部署时注入，不打包进镜像。
COPY app ./app
COPY config ./config
COPY scripts ./scripts
# 导入 app/main.py 中的 app；0.0.0.0 是容器内监听，宿主机暴露范围由端口映射决定。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
