"""手动集成验收：先请求 DeepSeek，再验证正常和错误 Key 两条 MQTT 链路。
要求 Broker 已启动且 8000 空闲，会真实产生模型调用用量。
临时修改 backend/.env，常规退出或异常时在 finally 中恢复；强制结束进程无法保证恢复。"""
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from dotenv import dotenv_values
import httpx
from openai import OpenAI

PROJECT = Path(__file__).resolve().parents[2]
BACKEND = PROJECT / "backend"


def main():
    # 避免误连用户已启动的另一个 8000 服务。
    """执行版本记录、最小请求和正常/错误 Key 集成验收。
    两轮分别启动独立 uvicorn 子进程；结束时关闭子进程并恢复原配置字节。"""
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8000)) == 0:
            raise RuntimeError("Port 8000 already occupied")
    config = dotenv_values(BACKEND / ".env")
    print("VERSIONS=" + json.dumps({name: importlib.metadata.version(name) for name in ["fastapi", "uvicorn", "paho-mqtt", "sqlalchemy", "psycopg", "pydantic-settings", "apscheduler", "jinja2", "python-multipart", "openai", "python-dotenv", "pyyaml", "pytest", "httpx"]}), flush=True)
    # 先用极短请求独立检查 API 连通性并记录用量，避免 MQTT 故障与 Key 故障混淆。
    with OpenAI(api_key=config["DEEPSEEK_API_KEY"], base_url=config["DEEPSEEK_BASE_URL"], timeout=20, max_retries=2) as llm:
        started = time.monotonic()
        response = llm.chat.completions.create(model=config["LLM_MODEL"], messages=[{"role": "user", "content": "Reply only OK"}], max_tokens=5)
        print("MINIMAL=" + json.dumps({"elapsed_seconds": round(time.monotonic()-started, 3), "response": response.choices[0].message.content, "usage": response.usage.model_dump()}, ensure_ascii=False), flush=True)
    # 按文件路径导入独立模拟器，复用真实发报逻辑，不复制一套测试用实现。
    spec = importlib.util.spec_from_file_location("demo", PROJECT / "simulator/demo_publish.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    env_path = BACKEND / ".env"
    # 按字节保存，结束时连同换行与格式一起恢复，不在控制台打印文件内容。
    original = env_path.read_bytes()
    try:
        for mode in ("normal", "invalid_key"):
            if mode == "invalid_key":
                from dotenv import set_key
                set_key(env_path, "DEEPSEEK_API_KEY", "invalid-demo-key")
            child_env = os.environ.copy()
            # 去掉继承环境里的同名 Key，确保子进程实际读取被演练修改的 .env。
            child_env.pop("DEEPSEEK_API_KEY", None)
            child_env["PYTHONUTF8"] = "1"
            process = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=BACKEND, env=child_env)
            try:
                # 本机健康检查不继承系统代理，避免 localhost 请求被送往代理服务器。
                with httpx.Client(trust_env=False) as client:
                    # 每轮检查子进程状态与 HTTP 响应；等待间隔不是对启动成功的判断依据。
                    for attempt in range(40):
                        if process.poll() is not None:
                            raise RuntimeError("Backend exited during startup")
                        try:
                            health = client.get("http://127.0.0.1:8000/health", timeout=1)
                            if health.status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(0.5)
                    else:
                        raise TimeoutError("Health check timed out")
                print("MODE=" + mode + " HEALTH=" + health.text, flush=True)
                result = demo.run()
                prediction = result["prediction"]
                assert prediction["confidence"] == "low"
                if mode == "invalid_key":
                    assert prediction["next_behavior"] == "暂无法判断，建议保持当前状态"
                    assert "AuthenticationError" in prediction["reasoning"]
                else:
                    assert prediction["next_behavior"] != "暂无法判断，建议保持当前状态"
                # 等待已回推日志落盘。
                time.sleep(0.5)
            finally:
                # 只结束本轮创建的子进程；强制终止不等于验证应用优雅退出流程。
                process.terminate()
                process.wait(timeout=15)
    finally:
        # 正常异常传播也会到这里；若整个验收进程被强杀，需人工检查配置是否恢复。
        env_path.write_bytes(original)
        print("BACKEND_ENV_RESTORED=" + str(env_path.read_bytes() == original), flush=True)


if __name__ == "__main__":
    main()
