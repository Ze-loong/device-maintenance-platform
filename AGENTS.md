# 设备预测性维护平台 — 开发说明

> 给接手本项目本机开发的 AI 编程工具（Claude Code / Codex，可能交替使用）。`CLAUDE.md` 与 `AGENTS.md` 内容完全相同，改一份必须同步另一份。
> 进入项目先读本文件 → 有背景疑问翻 `设计文档/00-业务设计.md`。不要凭空猜测项目状态。

## 一、项目是什么

- 工业风机预测性维护平台（车间通风机/冷却塔风机场景），个人作品集项目。业务设计定稿见 [`设计文档/00-业务设计.md`](设计文档/00-业务设计.md)，里面有完整的业务实体设计、五维画像方案、故障模式定义、MQTT topic 设计。
- 一句话：风机联网上报运行数据（振动/温度/启停）→ 平台校验/归档/入库 → 每日用大模型为每台风机生成健康度画像 → 新事件到来时结合画像实时推理"设备是否需要维护"（带置信度与推理依据）→ 平台向运维人员/网关推送维护建议；从零数据冷启动，置信度随数据积累提升。
- 业务设计文档把关键判断都记录清楚了，日常开发是把定稿的设计转化成代码并持续验证。

## 二、开发分工原则

- **架构层保持稳定**：`api/`（controller）、`repository/`（persistence）、`schemas/`、`core/`、`tasks/`（APScheduler）五层分层、置信度规则引擎、MQTT client 连接/重连逻辑一旦定型不轻易大改，改动要有明确理由并记录。
- **判断性工作与机械性工作分开处理**：字段/命名这类机械性强的改动可以批量执行 + 人工抽查；prompt 设计、置信度规则这类判断性强的工作需要仔细推敲，不要单方面改动设计；MQTT topic 下行粒度这类涉及业务语义的改造，动手前先确认设计文档里的结论。
- 具体每一轮做什么，按当前实际进度临场判断，不依赖固定模板。

## 三、协作规则

1. **验证再交付**：任何改动都要真实跑通（pytest / 真实 Docker 环境端到端验证），把关键输出记下来，不接受"应该能跑"。
2. **不要凭空重新讨论已定稿的设计**：业务实体、五维画像、故障模式、MQTT topic 逻辑均已在业务设计文档中定稿。遇到分歧先翻业务设计文档，不要在代码层面自行改动设计判断；如果实现中发现设计文档有遗漏或矛盾，明确指出，不要悄悄改设计。
3. **红线**（不可违反）：密钥只经 `.env` 注入，禁止写进代码或提交仓库；MQTT Broker 禁止匿名接入；LLM/数据库故障时事件照常接收存储并回推兜底结果，管理端不出现 500；界面/日志/注释全部中文。
4. **同步双文件**：改了本文件必须同步 `AGENTS.md`（内容一致）。
5. **中文代码注释规范**：能让人快速读懂但不写成教材，重点讲职责/设计原因/数据流向，语境统一为"产线/风机健康度"场景，不要留混杂语境的注释；注释只讲技术判断本身，不记录决策过程或工具分工。

## 四、本机环境（已知事实）

- Python 解释器：`D:\Claude\Project\ai\ai\.venv\Scripts\python.exe`（Python 3.14），多个项目共享。装包：`<解释器> -m pip install <包> -i https://mirrors.aliyun.com/pypi/simple/`。不锁老版本号，先装最新版。
- 密钥：`backend/.env` 从 `backend/.env.example` 复制后填写 `DEEPSEEK_API_KEY`（主）/`DASHSCOPE_API_KEY`（通义备选）；`simulator/.env`、`deploy/.env` 同理各自从对应 `.env.example` 复制生成。**这几个 `.env` 都不入库**。
- 端口与 Compose 项目名：Postgres=5544、EMQX=1884/18084、平台=8001，Compose 项目名 `device-maintenance`，写在 `deploy/docker-compose.yml`/`deploy/deploy.sh` 里。
- Docker：Windows 宿主机 Docker Desktop 可用。
- 本机无独立显卡，全部大模型调用走云端 API。

## 五、代码分层规范

`backend/app/` 采用 controller → service → models → repository(persistence) → schemas 五层，外加横切层：

| 目录 | 层 | 只做什么 |
| --- | --- | --- |
| `api/` | controller（HTTP 入口） | 接请求、校验参数（用 schemas）、调 service、返回。**不写业务规则、不直接查库** |
| `mqtt/` | controller（消息入口） | 连接 Broker、订阅上行、解析载荷（用 schemas）、调 `service.event_service.handle_event()`；发布下行。**同样不写业务规则** |
| `service/` | 业务逻辑 | 归属校验、归档、入库编排、推理、置信度、降级、画像生成与抽样。只依赖 repository / ai / core |
| `models/` | ORM 表定义 | SQLAlchemy 模型，一表一类 |
| `repository/` | 持久化 | 每张表一个 repository，所有 SQL/ORM 查询只在这里 |
| `schemas/` | 数据校验 | Pydantic：MQTT 上下行载荷、REST 请求/响应 |
| `core/` | 横切 | config（pydantic-settings）、logging、exceptions、security（密码哈希/会话）、deps（DB 会话依赖） |
| `ai/` | 大模型适配 | LLM 客户端（重试/超时）、提示词模板、输出解析。不含业务编排 |
| `tasks/` | 定时任务 | APScheduler 注册与每日画像 job，job 内只调 service |
| `templates/` `static/` | 管理端页面 | Jinja2 模板 + 原生 JS + Chart.js，由 `api/pages.py` 渲染 |

**关键约束**：REST 预测调试接口与 MQTT 订阅端必须调用**同一个** `event_service.handle_event()`，保证调试链路与生产链路行为一致。

`simulator/` 是独立 MQTT 客户端程序（模拟风机网关），不 import backend 代码。`deploy/` 放 docker-compose、部署脚本、EMQX 配置。

## 六、文档索引

| 文件 | 内容 |
| --- | --- |
| `设计文档/00-业务设计.md` | 本项目的业务设计依据：业务实体、五维画像方案、故障模式定义、MQTT topic 设计、置信度三档规则，改动判断以此为准 |

---
*本文件同时存为 `CLAUDE.md`（Claude Code 自动加载）和 `AGENTS.md`（Codex 等工具自动加载），内容一致。*
