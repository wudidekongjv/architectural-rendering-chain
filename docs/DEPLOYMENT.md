# 部署文档

## 前置条件

1. NVIDIA GPU（推荐 2 × RTX 4090 24GB） + 驱动 ≥ 535
2. Docker + Docker Compose + nvidia-container-toolkit
3. 约 60GB 磁盘空间（模型权重）
4. Ubuntu 22.04 LTS

```bash
# 验证 GPU 透传
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

## 部署步骤

### 1. 克隆并下载模型

```bash
git clone https://github.com/wudidekongjv/architectural-rendering-chain.git
cd architectural-rendering-chain

# 下载模型（约 60GB，详见 MODEL_DOWNLOADS.md）
bash scripts/download_models.sh --all
```

### 2. 启动服务

```bash
cd docker
docker compose up -d
```

服务清单：
| 服务 | 端口 | 说明 |
|---|---|---|
| api | 8000 | FastAPI 服务（SSE 进度推送） |
| comfyui | 8188 | ComfyUI 工作流引擎 |
| vllm | 8001 | Qwen3-32B 提示词优化端点 |
| redis | 6379 | 任务状态/缓存 |
| frontend | 5173 | Vue3 前端 |

### 3. 验证

```bash
curl http://localhost:8000/docs          # API 文档
curl http://localhost:8188/system_stats  # ComfyUI 状态
curl http://localhost:8001/v1/models     # vLLM 模型
```

访问前端：http://localhost:5173

## 生产环境注意事项

### SSE 配置
Nginx 反代必须关闭缓冲，否则进度推送会被批量延迟：
```nginx
location /api/v1/render/stream {
    proxy_pass http://api:8000;
    proxy_buffering off;
    proxy_http_version 1.1;
    proxy_set_header Connection '';
    chunked_transfer_encoding off;
}
```
FastAPI 侧已设 `X-Accel-Buffering: no` 响应头。

### 任务队列
示例代码中渲染任务同步执行。生产环境应接入 Celery + Redis：
```python
# 将 run_until_approval 放入后台任务
task = run_until_approval.delay(task_id)
```

### 断线恢复
SSE 断线后前端应用 `GET /api/task/{id}/status` 查询当前阶段，增量恢复渲染，不依赖长连接状态。

### 数据持久化
- 任务状态：Redis（`SET answer:{hash} {json} EX 300`）
- 上传图片：对象存储（MinIO / 阿里云 OSS）
- 审计日志：MySQL

## 常见问题

| 问题 | 原因 | 解决 |
|---|---|---|
| 容器无法识别 GPU | 未装 nvidia-container-toolkit | 安装后重启 Docker |
| 生成图中文乱码 | 缺少中文字体 | 镜像已装 fonts-noto-cjk |
| SSE 不逐条推送 | Nginx 缓冲 | 设 proxy_buffering off |
| Flux OOM | 显存不足 | 改用 fp8 量化版或降低分辨率 |
| 提示词优化无响应 | vLLM 未启动 | 检查 8001 端口与模型路径 |

## 多服务器扩展

单机 Docker Compose 适用于 10 人以内设计组。跨机部署建议：
- Kubernetes + NVIDIA Device Plugin
- ComfyUI 作为独立 GPU 节点池
- vLLM 作为共享推理服务
- Redis Cluster 做任务队列与状态共享

本项目未实施多机方案（评估过，单机足够）。
