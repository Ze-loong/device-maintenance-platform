#!/usr/bin/env bash
# 一键部署脚本：先自检环境，再启动 Compose 全部服务。对应 FR-15、NFR-04。
# 自检失败时给出中文原因；健康状态以 Compose 返回的容器状态为准。
set -euo pipefail
cd "$(dirname "$0")"

echo "== 设备预测性维护平台 · 一键部署自检 =="

# 检查 Docker CLI、Compose 插件和 Docker 守护进程，避免构建到一半才暴露环境问题。
if ! command -v docker >/dev/null 2>&1; then
  echo "[失败] 未找到命令：docker，请先安装 Docker Desktop（含 Compose 插件）。"
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "[失败] 未检测到 docker compose 插件，请升级 Docker Desktop。"
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "[失败] Docker 守护进程不可用，请先启动 Docker Desktop。"
  exit 1
fi
echo "[通过] docker / docker compose / Docker 守护进程可用。"

# 三份真实配置均不进入镜像，缺少任何一份都不能安全启动完整服务。
missing_env=()
for f in "../backend/.env" "../simulator/.env" ".env"; do
  [ -f "$f" ] || missing_env+=("$f")
done
if [ ${#missing_env[@]} -gt 0 ]; then
  echo "[失败] 缺少配置文件：${missing_env[*]}"
  echo "        请先在项目根目录运行：<python解释器> deploy/init_local.py"
  exit 1
fi
echo "[通过] backend/.env、simulator/.env、deploy/.env 均已存在。"

# 在 WSL/Git Bash 中优先调用 Windows PowerShell 检查真正的宿主机端口；
# 纯 Linux 部署环境没有 PowerShell 时再使用 lsof。
for port in 1884 18084 5544 8001; do
  occupied=0
  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >/dev/null 2>&1 && occupied=1
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 && occupied=1
  else
    echo "[失败] 当前环境缺少 lsof 和 powershell.exe，无法完成端口自检。"
    exit 1
  fi
  if [ "$occupied" -eq 1 ]; then
    echo "[失败] 端口 $port 已被占用，请先释放或修改 docker-compose.yml 里的映射端口。"
    exit 1
  fi
done
echo "[通过] 1884 / 18084 / 5544 / 8001 端口均未被占用。"

# 部署目录所在分区至少预留 2GB，避免镜像层或数据库写到一半耗尽空间。
avail_kb=$(df -Pk . | tail -1 | awk '{print $4}')
if [ "$avail_kb" -lt $((2 * 1024 * 1024)) ]; then
  echo "[失败] 当前磁盘可用空间不足 2GB，镜像构建与数据库数据可能无法正常写入。"
  exit 1
fi
echo "[通过] 磁盘可用空间充足。"

# 只验证密钥已填写，不在部署阶段制造额外收费调用，也不打印密钥内容。
if grep -q "DEEPSEEK_API_KEY=$" ../backend/.env || grep -q "DEEPSEEK_API_KEY=change_me" ../backend/.env; then
  echo "[失败] backend/.env 中 DEEPSEEK_API_KEY 未配置，请先填写有效密钥。"
  exit 1
fi
echo "[通过] DEEPSEEK_API_KEY 已配置（未在部署脚本中发起真实调用校验连通性）。"

echo "== 自检全部通过，开始构建并启动全部服务 =="
docker compose up -d --build

echo "== 等待全部服务进入就绪状态（最多等待 3 分钟）=="
deadline=$((SECONDS + 180))
while [ "$SECONDS" -lt "$deadline" ]; do
  # 有 healthcheck 的服务必须 healthy；没有 healthcheck 的 simulator 只需处于 running。
  not_ready=$(docker compose ps --format '{{.Name}}|{{.State}}|{{.Health}}' | awk -F'|' '$2 != "running" || ($3 != "" && $3 != "healthy")')
  service_count=$(docker compose ps --services --status running | wc -l | tr -d ' ')
  if [ -z "$not_ready" ] && [ "$service_count" -eq 4 ]; then
    echo "[通过] 全部服务已就绪。"
    docker compose ps
    echo "管理端地址：http://127.0.0.1:8001    EMQX 控制台：http://127.0.0.1:18084"
    echo "首次部署如尚未创建管理员账号，请执行："
    echo "  docker compose run --rm platform python scripts/init_db.py"
    echo "  docker compose run --rm platform python scripts/create_admin.py"
    exit 0
  fi
  sleep 5
done
echo "[失败] 3 分钟内未全部转为就绪状态，当前状态："
docker compose ps
exit 1
