# 独立模拟网关镜像；不 import backend 代码，只依赖自己的 requirements.txt。
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
# 与后端使用同一镜像源和重试策略，降低首次部署受公网下载波动影响的概率。
RUN pip install --no-cache-dir --timeout 120 --retries 5 \
    -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
# 容器没有交互终端，关闭 stdout 缓冲后才能实时看到连接、断线与预测日志。
ENV PYTHONUNBUFFERED=1
# 只复制模拟器自身代码；真实 .env 由部署时注入，不打包进镜像。
COPY main.py schedule.py demo_publish.py ./
# 默认持续以实时模式运行；回填改为显式手动执行，避免容器重启重复回填历史数据。
# 手动回填命令：docker compose run --rm simulator python main.py --backfill-only
CMD ["python", "main.py", "--skip-backfill"]
