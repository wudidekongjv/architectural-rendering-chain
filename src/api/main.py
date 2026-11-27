"""FastAPI 服务：建筑渲染 Agent HTTP 接口

提供：
- POST /api/v1/render         提交渲染任务（运行到审批卡点）
- POST /api/v1/render/{id}/approve  人工审批并恢复 Pipeline
- GET  /api/task/{id}/status  查询任务状态（断线重连用）
- GET  /api/v1/render/stream  SSE 流式进度推送

关键点：
- 依赖注入（Depends）管理 DB/Redis/Pipeline 生命周期
- SSE 设 X-Accel-Buffering: no 禁用 Nginx 缓冲
- 任务状态持久化到 Redis，支持断线恢复
"""

import asyncio
import json
import uuid
from pathlib import Path
from typing import AsyncGenerator, Dict, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from comfyui_client import ComfyUIClient
from controlnet_builder import ControlNetBuilder
from pipeline import RenderTask, RenderingPipeline
from prompt_optimizer import PromptOptimizer

app = FastAPI(title="Architectural Rendering Chain API", version="1.0.0")

# 全局任务状态存储（生产用 Redis，此处用内存演示）
TASKS: Dict[str, RenderTask] = {}
PROGRESS: Dict[str, list] = {}


# ---------- 依赖注入 ----------

def get_pipeline() -> RenderingPipeline:
    """Pipeline 依赖（生产环境可加缓存复用）"""
    pipeline = RenderingPipeline(
        comfyui=ComfyUIClient(base_url="http://localhost:8188"),
        optimizer=PromptOptimizer(),
        controlnet=ControlNetBuilder(),
        workflows_dir="workflows",
        output_dir="outputs",
        progress_callback=lambda stage, pct: PROGRESS.setdefault(
            CURRENT_TASK.get("id", "global"), []
        ).append({"stage": stage, "pct": pct}),
    )
    return pipeline


CURRENT_TASK: Dict[str, str] = {}


# ---------- 数据模型 ----------

class RenderResponse(BaseModel):
    task_id: str
    status: str
    message: str


class ApproveRequest(BaseModel):
    approved_index: int


class TaskStatus(BaseModel):
    task_id: str
    stage: str
    draft_images: list
    final_image: str
    error: str


# ---------- 接口 ----------

@app.post("/api/v1/render", response_model=RenderResponse)
async def render(
    user_input: str = Form(...),
    image: UploadFile = File(...),
    pipeline: RenderingPipeline = Depends(get_pipeline),
):
    """提交渲染任务，运行到人工审批卡点"""
    task_id = str(uuid.uuid4())
    CURRENT_TASK["id"] = task_id
    PROGRESS[task_id] = []

    # 保存上传图片
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    image_path = upload_dir / f"{task_id}_{image.filename}"
    image_path.write_bytes(await image.read())

    task = RenderTask(task_id=task_id, user_input=user_input, image_path=str(image_path))
    TASKS[task_id] = task

    try:
        # 同步执行到审批卡点（生产环境应放入 Celery 任务队列）
        task = pipeline.run_until_approval(task)
        return RenderResponse(
            task_id=task_id,
            status=task.stage,
            message="Drafts ready, awaiting human approval",
        )
    except Exception as e:
        task.error = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/render/{task_id}/approve", response_model=RenderResponse)
async def approve(
    task_id: str,
    req: ApproveRequest,
    pipeline: RenderingPipeline = Depends(get_pipeline),
):
    """人工审批并恢复 Pipeline 继续精修"""
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.stage != "awaiting_approval":
        raise HTTPException(status_code=400, detail=f"Task not awaiting approval: {task.stage}")

    CURRENT_TASK["id"] = task_id
    try:
        task = pipeline.resume_from_approval(task, req.approved_index)
        return RenderResponse(task_id=task_id, status=task.stage, message="Render complete")
    except Exception as e:
        task.error = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/task/{task_id}/status", response_model=TaskStatus)
async def task_status(task_id: str):
    """查询任务状态（SSE 断线重连后用此接口恢复）"""
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatus(
        task_id=task_id,
        stage=task.stage,
        draft_images=task.draft_images,
        final_image=task.final_image,
        error=task.error,
    )


@app.get("/api/v1/render/stream")
async def stream(task_id: str, request: Request) -> StreamingResponse:
    """SSE 流式进度推送

    Event format:
        event: progress
        data: {"stage":"sdxl_draft","pct":40}

        : heartbeat
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        last_idx = 0
        heartbeat_count = 0
        while True:
            if await request.is_disconnected():
                break

            events = PROGRESS.get(task_id, [])[last_idx:]
            for evt in events:
                yield f"event: progress\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n"
                last_idx += 1

            # 心跳保活（每 15 次轮询 ≈ 15 秒）
            heartbeat_count += 1
            if heartbeat_count % 15 == 0:
                yield ": heartbeat\n\n"

            task = TASKS.get(task_id)
            if task and task.stage == "done":
                yield f"event: done\ndata: {json.dumps({'final_image': task.final_image}, ensure_ascii=False)}\n\n"
                break
            if task and task.error:
                yield f"event: error\ndata: {json.dumps({'error': task.error}, ensure_ascii=False)}\n\n"
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲，保证逐条推送
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
