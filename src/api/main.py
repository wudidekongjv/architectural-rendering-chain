"""FastAPI 服务：建筑渲染 Agent · 局域网多用户版

安全架构：
1. 局域网限制：中间件校验来源 IP 必须在私有网段（10/8, 172.16/12, 192.168/16, 127/8）
2. 设备指纹鉴权：所有业务请求必须带 X-Device-Id 头，作为自动登录凭据
3. 设备自动注册：首次访问的设备自动登记，分配角色与存储目录
4. 数据隔离：任务与图片按 角色/设备ID/任务ID 三级隔离，用户只能访问自己的数据

接口清单（与前端严格一一对应）：
- POST   /api/auth/register              设备首次注册（返回角色与用户ID）
- GET    /api/auth/me                    查询当前设备身份
- GET    /api/tasks                      当前设备的渲染记录列表
- GET    /api/tasks/{task_id}            单条渲染记录详情
- POST   /api/v1/render                  提交渲染任务
- POST   /api/v1/render/{id}/approve     人工审批并恢复 Pipeline
- GET    /api/task/{id}/status           任务状态（SSE 断线恢复）
- GET    /api/v1/render/stream           SSE 流式进度推送
- GET    /api/files/{relative_path}      鉴权后的图片/文件访问
- GET    /api/roles                      角色列表（管理用途）

部署约束：仅监听局域网接口，禁止公网暴露。
"""

import asyncio
import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from comfyui_client import ComfyUIClient
from controlnet_builder import ControlNetBuilder
from pipeline import RenderTask, RenderingPipeline
from prompt_optimizer import PromptOptimizer

# ============ 配置 ============
BASE_DIR = Path(os.getenv("ARCHRENDER_HOME", "./archrender_data"))
DB_PATH = BASE_DIR / "archrender.db"
OUTPUT_ROOT = BASE_DIR / "outputs"
UPLOAD_ROOT = BASE_DIR / "uploads"

# 局域网网段白名单（可通过环境变量扩展）
LAN_NETWORKS = [
    ipaddress.ip_network(n) for n in
    os.getenv("ARCHRENDER_LAN", "127.0.0.1/32,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16").split(",")
]
# 设备 ID 允许的字符集（防注入）
DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")

# 默认角色（首次注册设备）
DEFAULT_ROLE = os.getenv("ARCHRENDER_DEFAULT_ROLE", "designer")
ROLE_CONFIG = {
    "designer": {"name": "方案设计师", "quota_per_day": 200},
    "reviewer": {"name": "方案审核", "quota_per_day": 50},
    "admin": {"name": "管理员", "quota_per_day": 1000},
}

BASE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

# ============ 数据库 ============
def init_db():
    """初始化 SQLite：设备表 + 任务表"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                user_id TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL,
                label TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                prompt TEXT NOT NULL,
                stage TEXT NOT NULL,
                draft_images TEXT DEFAULT '[]',
                final_image TEXT DEFAULT '',
                reference_images TEXT DEFAULT '[]',
                error TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (device_id) REFERENCES devices(device_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_device ON tasks(device_id, created_at DESC)")
        conn.commit()


init_db()


@contextmanager
def db_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ============ 安全中间件 ============
app = FastAPI(title="Architectural Rendering Chain API", version="2.0.0")


def is_lan_ip(ip_str: str) -> bool:
    """判断 IP 是否在局域网白名单"""
    try:
        addr = ipaddress.ip_address(ip_str)
        # 优先检查 Docker 网桥：若配置了 ARCHRENDER_TRUST_PROXY，信任 X-Forwarded-For
        return any(addr in net for net in LAN_NETWORKS)
    except ValueError:
        return False


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """全局安全中间件：IP 白名单 + 设备指纹校验

    放行：/docs /openapi.json /api/auth/register（注册时设备尚未登记）
    """
    path = request.url.path

    # 1) 局域网 IP 校验
    client_ip = request.client.host if request.client else ""
    if not is_lan_ip(client_ip):
        return JSONResponse(
            status_code=403,
            content={"detail": f"Access denied: non-LAN address ({client_ip})"},
        )

    # 2) 放行文档端点
    if path in ("/docs", "/openapi.json", "/redoc", "/api/auth/register"):
        return await call_next(request)

    # 3) 设备指纹校验
    # 常规请求从 header 读取；EventSource（SSE）无法设置自定义 header，
    # 因此对 /api/v1/render/stream 允许从 query 参数读取（仅此端点例外）
    device_id = request.headers.get("X-Device-Id", "")
    if not device_id and path == "/api/v1/render/stream":
        device_id = request.query_params.get("device_id", "")
    if not device_id or not DEVICE_ID_RE.match(device_id):
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid X-Device-Id header"},
        )

    with db_conn() as conn:
        device = conn.execute("SELECT * FROM devices WHERE device_id=?", (device_id,)).fetchone()
    if not device:
        return JSONResponse(
            status_code=401,
            content={"detail": "Unregistered device. Call /api/auth/register first."},
        )

    request.state.device_id = device_id
    request.state.user_id = device["user_id"]
    request.state.role = device["role"]

    with db_conn() as conn:
        conn.execute("UPDATE devices SET last_seen=? WHERE device_id=?", (now_str(), device_id))

    return await call_next(request)


def get_identity(request: Request) -> Dict[str, str]:
    """依赖注入：从 request.state 提取设备身份"""
    return {
        "device_id": request.state.device_id,
        "user_id": request.state.user_id,
        "role": request.state.role,
    }


def user_output_dir(identity: Dict[str, str], task_id: Optional[str] = None) -> Path:
    """按 角色/用户ID/任务ID 三级构造隔离目录"""
    path = OUTPUT_ROOT / identity["role"] / identity["user_id"]
    if task_id:
        path = path / task_id
    path.mkdir(parents=True, exist_ok=True)
    return path


# ============ 数据模型 ============
class RegisterReq(BaseModel):
    device_id: str
    label: Optional[str] = ""


class ApproveRequest(BaseModel):
    approved_index: int
    reference_images: Optional[List[str]] = []   # 审批时携带的引用图片路径


class TaskOut(BaseModel):
    task_id: str
    prompt: str
    stage: str
    thumb: str
    final_image: str
    created_at: str
    time_label: str


# ============ 鉴权接口 ============
@app.post("/api/auth/register")
async def register(req: RegisterReq, request: Request):
    """设备首次注册：以设备指纹作为自动登录凭据

    返回用户 ID（如 BZ-0216）与角色。同一 device_id 重复注册返回已有身份。
    """
    if not DEVICE_ID_RE.match(req.device_id):
        raise HTTPException(status_code=400, detail="Invalid device_id format")

    with db_conn() as conn:
        existing = conn.execute("SELECT * FROM devices WHERE device_id=?", (req.device_id,)).fetchone()
        if existing:
            return {
                "device_id": req.device_id,
                "user_id": existing["user_id"],
                "role": existing["role"],
                "role_name": ROLE_CONFIG.get(existing["role"], {}).get("name", existing["role"]),
                "created_at": existing["created_at"],
                "is_new": False,
            }

        # 生成用户 ID：BZ-四位数（按注册序号递增）
        count = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        user_id = f"BZ-{count + 1:04d}"
        role = DEFAULT_ROLE

        conn.execute(
            "INSERT INTO devices(device_id,user_id,role,label,created_at,last_seen) VALUES(?,?,?,?,?,?)",
            (req.device_id, user_id, role, req.label or "", now_str(), now_str()),
        )

    # 创建该用户的存储目录
    (OUTPUT_ROOT / role / user_id).mkdir(parents=True, exist_ok=True)
    (UPLOAD_ROOT / user_id).mkdir(parents=True, exist_ok=True)

    return {
        "device_id": req.device_id,
        "user_id": user_id,
        "role": role,
        "role_name": ROLE_CONFIG.get(role, {}).get("name", role),
        "created_at": now_str(),
        "is_new": True,
    }


@app.get("/api/auth/me")
async def me(identity: Dict[str, str] = Depends(get_identity)):
    """查询当前设备身份"""
    return {
        **identity,
        "role_name": ROLE_CONFIG.get(identity["role"], {}).get("name", identity["role"]),
        "quota_per_day": ROLE_CONFIG.get(identity["role"], {}).get("quota_per_day", 50),
    }


@app.get("/api/roles")
async def roles(identity: Dict[str, str] = Depends(get_identity)):
    """角色列表（当前仅管理员可查看全部）"""
    if identity["role"] != "admin":
        return [{"role": identity["role"], "name": ROLE_CONFIG.get(identity["role"], {}).get("name", "")}]
    return [{"role": k, "name": v["name"], "quota_per_day": v["quota_per_day"]} for k, v in ROLE_CONFIG.items()]


# ============ 渲染记录接口 ============
@app.get("/api/tasks")
async def list_tasks(identity: Dict[str, str] = Depends(get_identity)):
    """当前设备的渲染记录列表（前端侧栏数据源）"""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE device_id=? ORDER BY created_at DESC LIMIT 100",
            (identity["device_id"],),
        ).fetchall()

    result = []
    for r in rows:
        drafts = json.loads(r["draft_images"] or "[]")
        thumb = drafts[0] if drafts else (r["final_image"] or "")
        result.append({
            "task_id": r["task_id"],
            "prompt": r["prompt"],
            "stage": r["stage"],
            "thumb": f"/api/files/{thumb}" if thumb else "",
            "final_image": f"/api/files/{r['final_image']}" if r["final_image"] else "",
            "created_at": r["created_at"],
            "time_label": make_time_label(r["created_at"]),
        })
    return result


def make_time_label(created_at: str) -> str:
    """生成'今天 HH:MM / 昨天 HH:MM / MM-DD HH:MM'标签"""
    try:
        dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        if dt.date() == now.date():
            return f"今天 {dt.strftime('%H:%M')}"
        from datetime import timedelta
        if dt.date() == (now - timedelta(days=1)).date():
            return f"昨天 {dt.strftime('%H:%M')}"
        return dt.strftime("%m-%d %H:%M")
    except Exception:
        return created_at


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str, identity: Dict[str, str] = Depends(get_identity)):
    """单条渲染记录详情（前端点击历史记录时调用）"""
    with db_conn() as conn:
        r = conn.execute(
            "SELECT * FROM tasks WHERE task_id=? AND device_id=?",
            (task_id, identity["device_id"]),
        ).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Task not found or access denied")

    drafts = json.loads(r["draft_images"] or "[]")
    refs = json.loads(r["reference_images"] or "[]")
    return {
        "task_id": r["task_id"],
        "prompt": r["prompt"],
        "stage": r["stage"],
        "draft_images": [f"/api/files/{p}" for p in drafts],
        "final_image": f"/api/files/{r['final_image']}" if r["final_image"] else "",
        "reference_images": [f"/api/files/{p}" for p in refs],
        "error": r["error"],
        "created_at": r["created_at"],
    }


# ============ 图片访问（鉴权 + 隔离） ============
@app.get("/api/files/{relative_path:path}")
async def get_file(relative_path: str, identity: Dict[str, str] = Depends(get_identity)):
    """鉴权后的文件访问：只能访问自己 角色/用户ID 目录下的文件"""
    # 防目录穿越
    if ".." in relative_path or relative_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")

    allowed_root = (OUTPUT_ROOT / identity["role"] / identity["user_id"]).resolve()
    full_path = (OUTPUT_ROOT / relative_path).resolve()

    if not str(full_path).startswith(str(allowed_root)):
        raise HTTPException(status_code=403, detail="Access denied: path outside your directory")

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(full_path)


# ============ 渲染接口 ============
TASKS: Dict[str, RenderTask] = {}
PROGRESS: Dict[str, list] = {}


def get_pipeline(identity: Dict[str, str]) -> RenderingPipeline:
    """Pipeline 依赖：输出到当前用户的隔离目录 outputs/{role}/{user_id}/"""
    return RenderingPipeline(
        comfyui=ComfyUIClient(base_url="http://localhost:8188"),
        optimizer=PromptOptimizer(),
        controlnet=ControlNetBuilder(),
        workflows_dir="workflows",
        output_dir=str(user_output_dir(identity)),
        progress_callback=lambda stage, pct: PROGRESS.setdefault(
            CURRENT_TASK.get("id", "global"), []
        ).append({"stage": stage, "pct": pct, "ts": now_str()}),
    )


CURRENT_TASK: Dict[str, str] = {}


def to_relative_path(abs_or_rel: str) -> str:
    """把绝对路径转成相对 OUTPUT_ROOT 的路径（用于 /api/files/ 访问）"""
    if not abs_or_rel:
        return ""
    p = Path(abs_or_rel)
    if p.is_absolute():
        try:
            return str(p.resolve().relative_to(OUTPUT_ROOT.resolve()))
        except ValueError:
            return str(p)
    return str(p).replace("/api/files/", "")


def save_task(identity: Dict[str, str], task: RenderTask):
    """持久化任务状态到 SQLite"""
    drafts_rel = [to_relative_path(p) for p in task.draft_images]
    final_rel = to_relative_path(task.final_image)

    with db_conn() as conn:
        conn.execute("""
            INSERT INTO tasks(task_id,device_id,user_id,role,prompt,stage,draft_images,final_image,error,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(task_id) DO UPDATE SET
                stage=excluded.stage, draft_images=excluded.draft_images,
                final_image=excluded.final_image, error=excluded.error, updated_at=excluded.updated_at
        """, (
            task.task_id, identity["device_id"], identity["user_id"], identity["role"],
            task.user_input, task.stage, json.dumps(drafts_rel), final_rel,
            task.error, now_str(), now_str(),
        ))


@app.post("/api/v1/render")
async def render(
    request: Request,
    user_input: str = Form(...),
    image: UploadFile = File(...),
    reference_paths: str = Form("[]"),   # JSON 数组：引用的历史图片相对路径
    identity: Dict[str, str] = Depends(get_identity),
):
    """提交渲染任务：图片存入该用户目录，Pipeline 运行到审批卡点"""
    task_id = str(uuid.uuid4())
    CURRENT_TASK["id"] = task_id
    PROGRESS[task_id] = []

    # 上传图片存到用户隔离目录
    user_upload = UPLOAD_ROOT / identity["user_id"]
    user_upload.mkdir(parents=True, exist_ok=True)
    image_path = user_upload / f"{task_id}_{image.filename}"
    image_path.write_bytes(await image.read())

    # 校验引用图片路径归属
    refs = json.loads(reference_paths or "[]")
    safe_refs = []
    allowed_root = (OUTPUT_ROOT / identity["role"] / identity["user_id"]).resolve()
    for ref in refs:
        ref_rel = ref.replace("/api/files/", "")
        full = (OUTPUT_ROOT / ref_rel).resolve()
        if str(full).startswith(str(allowed_root)) and full.exists():
            safe_refs.append(ref_rel)

    task = RenderTask(task_id=task_id, user_input=user_input, image_path=str(image_path))
    TASKS[task_id] = task

    try:
        pipeline = get_pipeline(identity)
        task = pipeline.run_until_approval(task)
        save_task(identity, task)

        return {
            "task_id": task_id,
            "status": task.stage,
            "message": "Drafts ready, awaiting human approval",
            "draft_images": [f"/api/files/{to_relative_path(p)}" for p in task.draft_images],
            "reference_images": [f"/api/files/{p}" for p in safe_refs],
        }
    except Exception as e:
        task.error = str(e)
        save_task(identity, task)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/render/{task_id}/approve")
async def approve(
    task_id: str,
    req: ApproveRequest,
    identity: Dict[str, str] = Depends(get_identity),
):
    """人工审批并恢复 Pipeline：校验任务归属后继续精修"""
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found in memory")

    # 归属校验：任务必须属于当前设备
    with db_conn() as conn:
        row = conn.execute(
            "SELECT device_id FROM tasks WHERE task_id=?", (task_id,)
        ).fetchone()
    if not row or row["device_id"] != identity["device_id"]:
        raise HTTPException(status_code=403, detail="Access denied: task belongs to another device")

    if task.stage != "awaiting_approval":
        raise HTTPException(status_code=400, detail=f"Task not awaiting approval: {task.stage}")

    CURRENT_TASK["id"] = task_id
    try:
        pipeline = get_pipeline(identity)
        task = pipeline.resume_from_approval(task, req.approved_index)
        save_task(identity, task)
        return {"task_id": task_id, "status": task.stage, "message": "Render complete"}
    except Exception as e:
        task.error = str(e)
        save_task(identity, task)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/task/{task_id}/status")
async def task_status(task_id: str, identity: Dict[str, str] = Depends(get_identity)):
    """任务状态（SSE 断线恢复）"""
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE task_id=? AND device_id=?",
            (task_id, identity["device_id"]),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found or access denied")

    drafts = json.loads(row["draft_images"] or "[]")
    return {
        "task_id": task_id,
        "stage": row["stage"],
        "draft_images": [f"/api/files/{p}" for p in drafts],
        "final_image": f"/api/files/{row['final_image']}" if row["final_image"] else "",
        "error": row["error"],
    }


@app.get("/api/v1/render/stream")
async def stream(task_id: str, request: Request, identity: Dict[str, str] = Depends(get_identity)):
    """SSE 流式进度推送

    事件格式：
        event: progress
        data: {"stage":"sdxl_draft","pct":40}

        : heartbeat
    """
    # 归属校验
    with db_conn() as conn:
        row = conn.execute(
            "SELECT device_id FROM tasks WHERE task_id=?", (task_id,)
        ).fetchone()
    if not row or row["device_id"] != identity["device_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    async def event_generator() -> AsyncGenerator[str, None]:
        last_idx = 0
        heartbeat = 0
        while True:
            if await request.is_disconnected():
                break

            events = PROGRESS.get(task_id, [])[last_idx:]
            for evt in events:
                yield f"event: progress\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n"
                last_idx += 1

            heartbeat += 1
            if heartbeat % 15 == 0:
                yield ": heartbeat\n\n"

            with db_conn() as conn:
                row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if row and row["stage"] == "done":
                final_path = row["final_image"]
                final_url = f"/api/files/{final_path}" if final_path else ""
                yield f"event: done\ndata: {json.dumps({'final_image': final_url}, ensure_ascii=False)}\n\n"
                break
            if row and row["error"]:
                yield f"event: error\ndata: {json.dumps({'error': row['error']}, ensure_ascii=False)}\n\n"
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    # 仅监听局域网：0.0.0.0 绑定所有网卡，但中间件拒绝非私网 IP
    uvicorn.run(app, host="0.0.0.0", port=8000)
