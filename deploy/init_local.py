"""首次部署的本地配置生成器：读取根目录 Key，生成四份本地凭据文件。
已有任何目标文件就拒绝覆盖，避免已运行的 Broker 与客户端密码不一致。
不启动容器、不打印秘密；生成的配置与认证 CSV 不应提交仓库。"""
from pathlib import Path
import secrets

from dotenv import dotenv_values


def main():
    """从示例模板生成后端、模拟器、部署配置及 Broker 初始用户表。
    缺少根 Key 或已有目标文件时退出；写文件过程不是事务，中断后需检查部分文件。"""
    project = Path(__file__).resolve().parents[1]
    targets = [project / "backend/.env", project / "simulator/.env", project / "deploy/.env", project / "deploy/emqx/auth-users.csv"]
    if any(path.exists() for path in targets):
        raise SystemExit("Configuration exists; refusing to overwrite")
    # 项目位于根目录 projects 下，project.parents[1] 因而是共享 .env 所在的工作区根目录。
    key = dotenv_values(project.parents[1] / ".env").get("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY not found in workspace .env")
    # 每个用途使用独立随机密码；token_urlsafe 适合写入 URL、CSV 与配置值。
    platform, simulator, postgres, dashboard = [secrets.token_urlsafe(24) for _ in range(4)]
    backend = (project / "backend/.env.example").read_text(encoding="utf-8")
    # 通过模板占位文本替换；模板中的占位值必须与这里保持一致。
    backend = backend.replace("iot:change_me@", f"iot:{postgres}@").replace("MQTT_PASSWORD=change_me", f"MQTT_PASSWORD={platform}").replace("DEEPSEEK_API_KEY=", f"DEEPSEEK_API_KEY={key}")
    simulator_env = (project / "simulator/.env.example").read_text(encoding="utf-8").replace("change_me", simulator)
    # CSV 的 false 表示两个 MQTT 用户都不是超级用户；文件本身含明文密码，必须保密。
    contents = [backend, simulator_env, f"EMQX_DASHBOARD_PASSWORD={dashboard}\nPOSTGRES_PASSWORD={postgres}\nEMQX_NODE_COOKIE={secrets.token_urlsafe(32)}\n", f"user_id,password,is_superuser\nplatform,{platform},false\nsimulator,{simulator},false\n"]
    # targets 与 contents 按同一顺序一一对应，只把真实凭据写入指定本地文件。
    for path, content in zip(targets, contents):
        path.write_text(content, encoding="utf-8")
    print("Local configuration created; credentials were not displayed")


if __name__ == "__main__":
    main()
