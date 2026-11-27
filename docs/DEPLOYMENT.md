# 部署文档 · 局域网多用户版

## 架构与边界

本系统部署在**局域网服务器**上，供多名设计师同时使用。安全边界由三层构成：

1. **网络层**：FastAPI 中间件校验每个请求的来源 IP，仅允许私有网段
   （`127.0.0.0/8`、`10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16`）。
   公网 IP 直接返回 403。
2. **身份层**：设备指纹码作为自动登录凭据。浏览器首次访问生成
   `dev_xxxxxxxx...` 存入 localStorage，通过 `X-Device-Id` 头随每次请求发送；
   后端自动注册该设备并分配用户 ID（如 `BZ-0216`）。无需账密。
3. **数据层**：任务与生成图片按 `outputs/{role}/{user_id}/{task_id}/` 三级隔离。
   所有文件访问经 `/api/files/` 鉴权，用户只能访问自己目录下的文件。

> **重要**：本系统不面向公网。请在防火墙层面确认 8000/5173 端口未映射到公网。

## 前置条件

- NVIDIA GPU（推荐 2 × RTX 4090 24GB）+ 驱动 ≥ 535
- Docker + Docker Compose + nvidia-container-toolkit
- 服务器与用户处于同一局域网
- 约 60GB 磁盘（模型权重）+ 输出存储空间

## 部署步骤

### 1. 克隆并下载模型

```bash
git clone https://github.com/wudidekongjv/architectural-rendering-chain.git
cd architectural-rendering-chain
bash scripts/download_models.sh --all
```

### 2. 启动服务

```bash
cd docker
docker compose up -d
```

服务与端口：

| 服务 | 端口 | 暴露范围 | 说明 |
|---|---|---|---|
| frontend | 5173 | 局域网 | Vue3 前端 |
| api | 8000 | 局域网 | FastAPI（含鉴权中间件） |
| comfyui | 8188 | 仅本机 | 工作流引擎，不对外 |
| vllm | 8001 | 仅本机 | 提示词优化推理 |
| redis | 6379 | 仅本机 | 缓存与任务队列 |

### 3. 用户访问

设计师在局域网内浏览器打开 `http://<服务器IP>:5173`：

- 首次访问：前端自动生成设备指纹并调用 `/api/auth/register` 注册，
  后端分配用户 ID（左下角显示，如 `BZ-0216`）与角色
- 后续访问：设备指纹从 localStorage 读取，无感登录
- 更换浏览器/设备：视为新用户，会分配新的用户 ID

### 4. 验证鉴权

```bash
# 无设备头访问（期望 401）
curl http://localhost:8000/api/tasks

# 注册设备
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"device_id":"dev_test1234567890abcdef"}'

# 带设备头访问（期望 200）
curl http://localhost:8000/api/tasks -H "X-Device-Id: dev_test1234567890abcdef"
```

## 数据目录结构

```
archrender_data/
├── archrender.db                      # SQLite：设备表 + 任务表
├── uploads/
│   └── BZ-0216/                       # 上传的白模/线稿（按用户隔离）
│       └── {task_id}_{filename}.png
└── outputs/
    └── designer/                      # 角色
        └── BZ-0216/                   # 用户
            └── {task_id}/             # 任务
                ├── controlnet/
                ├── drafts/            # 4 张候选初稿
                └── final_render.png   # 最终效果图
```

## 角色管理

默认角色由 `ARCHRENDER_DEFAULT_ROLE` 环境变量配置（默认 `designer`）。
角色配置在 `src/api/main.py` 的 `ROLE_CONFIG` 中：

| 角色 | 名称 | 每日配额 |
|---|---|---|
| designer | 方案设计师 | 200 次 |
| reviewer | 方案审核 | 50 次 |
| admin | 管理员 | 1000 次 |

管理员可通过 `/api/roles` 查看角色列表。生产环境建议由管理员在数据库中
调整设备的 role 字段来变更用户角色。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ARCHRENDER_HOME` | `./archrender_data` | 数据根目录（DB + 输出 + 上传） |
| `ARCHRENDER_LAN` | `127.0.0.1/32,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16` | 允许的局域网网段（逗号分隔） |
| `ARCHRENDER_DEFAULT_ROLE` | `designer` | 新注册设备的默认角色 |

## 前后端接口对照（一致性保证）

| UI 功能 | 后端接口 |
|---|---|
| 左下角用户 ID / 角色 | `POST /api/auth/register` + `GET /api/auth/me` |
| 左侧渲染记录列表 | `GET /api/tasks` |
| 点击历史记录加载详情 | `GET /api/tasks/{task_id}` |
| 拖拽上传 + 提交渲染 | `POST /api/v1/render` |
| 候选图审批 | `POST /api/v1/render/{id}/approve` |
| 进度时间线 / 结果推送 | `GET /api/v1/render/stream`（SSE） |
| 图片显示 / 下载 | `GET /api/files/{path}` |
| 图片点击引用 | 路径作为 `reference_paths` 随下次渲染提交 |

> 所有 UI 功能均有对应后端实现，无伪造数据。连接失败时界面明确报错，不展示演示内容。

## 常见问题

| 问题 | 原因 | 解决 |
|---|---|---|
| 界面显示"无法连接到渲染服务" | 非局域网 / 后端未启动 | 检查 IP 网段与容器状态 |
| 401 Unregistered device | 设备未注册 | 刷新页面触发自动注册 |
| 403 non-LAN address | IP 不在白名单 | 管理员扩展 `ARCHRENDER_LAN` |
| 403 path outside your directory | 越权访问他人文件 | 前端仅展示本人数据，不应出现 |
| SSE 进度不更新 | EventSource 用 query 传 device_id | 已实现该例外，检查后端版本 |
| Flux OOM | 显存不足 | 改用 fp8 量化版 |

## 安全建议

1. 服务器防火墙仅放行 5173/8000 给内网段
2. 定期备份 `archrender_data/archrender.db` 与 `outputs/`
3. 角色变更通过数据库直接调整 `devices.role` 字段
4. 如需审计，任务表已记录每次渲染的 prompt、时间、设备
