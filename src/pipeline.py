"""单线确定性 Pipeline 编排

建筑渲染图像生成的完整链路：
    input → prompt_optimize → controlnet → sdxl_draft → (HITL) → flux_refine → postprocess

设计说明：
- 这是确定性 DAG，不是多 Agent 状态机
- 节点内的 LLM / 深度模型是确定性转换，无决策权、无路由、无循环
- 人工审批（HITL）由外部触发，Pipeline 在此暂停等待，不自动推进
"""

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from comfyui_client import ComfyUIClient
from controlnet_builder import ControlNetBuilder
from prompt_optimizer import PromptOptimizer

logger = logging.getLogger(__name__)


@dataclass
class RenderTask:
    """渲染任务状态"""
    task_id: str
    user_input: str
    image_path: str
    optimized_prompt: str = ""
    controlnet_maps: Dict[str, str] = field(default_factory=dict)
    draft_images: List[str] = field(default_factory=list)
    approved_index: Optional[int] = None
    final_image: str = ""
    stage: str = "queued"
    error: str = ""


class RenderingPipeline:
    """建筑渲染 Pipeline"""

    def __init__(
        self,
        comfyui: ComfyUIClient,
        optimizer: PromptOptimizer,
        controlnet: ControlNetBuilder,
        workflows_dir: str = "workflows",
        output_dir: str = "outputs",
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ):
        self.comfyui = comfyui
        self.optimizer = optimizer
        self.controlnet = controlnet
        self.workflows_dir = Path(workflows_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.progress_callback = progress_callback

    def _progress(self, stage: str, pct: int):
        logger.info(f"[{stage}] {pct}%")
        if self.progress_callback:
            self.progress_callback(stage, pct)

    def step1_optimize_prompt(self, task: RenderTask) -> RenderTask:
        """Step 1: LLM 提示词优化"""
        self._progress("prompt_optimize", 10)
        task.optimized_prompt = self.optimizer.optimize(task.user_input)
        task.stage = "prompt_optimized"
        self._progress("prompt_optimize", 20)
        return task

    def step2_build_controlnet(self, task: RenderTask) -> RenderTask:
        """Step 2: ControlNet 条件图生成"""
        self._progress("controlnet", 25)
        out = self.output_dir / task.task_id / "controlnet"
        task.controlnet_maps = self.controlnet.build_all(task.image_path, str(out))
        task.stage = "controlnet_ready"
        self._progress("controlnet", 35)
        return task

    def step3_sdxl_draft(self, task: RenderTask) -> RenderTask:
        """Step 3: SDXL 多候选初稿生成"""
        self._progress("sdxl_draft", 40)
        workflow = self.comfyui.load_workflow(
            str(self.workflows_dir / "sdxl_draft.json")
        )
        # 注入动态参数
        workflow["6"]["inputs"]["text"] = task.optimized_prompt
        workflow["3"]["inputs"]["image"] = Path(task.controlnet_maps["depth"]).name
        # 复制图片到 ComfyUI input 目录（实际部署时挂载共享卷）
        task.draft_images = self.comfyui.generate(
            workflow, str(self.output_dir / task.task_id / "drafts")
        )
        task.stage = "awaiting_approval"
        self._progress("sdxl_draft", 60)
        return task

    def step4_human_approval(self, task: RenderTask, approved_index: int) -> RenderTask:
        """Step 4: 人工审批卡点（由外部调用）

        这是人的决策，不是 Agent 决策 —— Pipeline 在此暂停，
        等待设计师选择候选图或标注修改意见。
        """
        if not 0 <= approved_index < len(task.draft_images):
            raise ValueError(f"Invalid approved_index: {approved_index}")
        task.approved_index = approved_index
        task.stage = "approved"
        self._progress("human_approval", 70)
        return task

    def step5_flux_refine(self, task: RenderTask) -> RenderTask:
        """Step 5: Flux.1-dev 精修"""
        self._progress("flux_refine", 75)
        workflow = self.comfyui.load_workflow(
            str(self.workflows_dir / "flux_refine.json")
        )
        approved = task.draft_images[task.approved_index]
        workflow["1"]["inputs"]["image_path"] = approved
        workflow["4"]["inputs"]["text"] = task.optimized_prompt
        results = self.comfyui.generate(
            workflow, str(self.output_dir / task.task_id / "final")
        )
        task.final_image = results[0] if results else ""
        task.stage = "refined"
        self._progress("flux_refine", 90)
        return task

    def step6_postprocess(self, task: RenderTask) -> RenderTask:
        """Step 6: 后处理与交付"""
        self._progress("postprocess", 95)
        final = Path(self.output_dir) / task.task_id / "final_render.png"
        if task.final_image and Path(task.final_image).exists():
            shutil.copy(task.final_image, final)
            task.final_image = str(final)
        task.stage = "done"
        self._progress("done", 100)
        return task

    def run_until_approval(self, task: RenderTask) -> RenderTask:
        """运行到人工审批卡点为止"""
        task = self.step1_optimize_prompt(task)
        task = self.step2_build_controlnet(task)
        task = self.step3_sdxl_draft(task)
        return task

    def resume_from_approval(self, task: RenderTask, approved_index: int) -> RenderTask:
        """从人工审批恢复，继续到完成"""
        task = self.step4_human_approval(task, approved_index)
        task = self.step5_flux_refine(task)
        task = self.step6_postprocess(task)
        return task
