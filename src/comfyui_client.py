"""ComfyUI API 客户端

通过 HTTP API 提交工作流 JSON 到 ComfyUI，轮询获取生成结果。
所有图像生成步骤都通过此类驱动。
"""

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)


class ComfyUIClient:
    """ComfyUI API 客户端"""

    def __init__(self, base_url: str = "http://localhost:8188", timeout: int = 600):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client_id = str(uuid.uuid4())

    def submit(self, workflow: Dict[str, Any]) -> str:
        """提交工作流

        Args:
            workflow: ComfyUI 工作流 JSON（节点 ID -> 节点定义）

        Returns:
            prompt_id
        """
        resp = requests.post(
            f"{self.base_url}/prompt",
            json={"prompt": workflow, "client_id": self.client_id},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"No prompt_id in response: {result}")
        logger.info(f"Workflow submitted: {prompt_id}")
        return prompt_id

    def wait_for_result(self, prompt_id: str, poll_interval: float = 1.0) -> Dict[str, Any]:
        """轮询等待生成完成

        Args:
            prompt_id: 提交时返回的 ID
            poll_interval: 轮询间隔（秒）

        Returns:
            历史记录（含输出图片信息）
        """
        start = time.time()
        while time.time() - start < self.timeout:
            resp = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=10)
            resp.raise_for_status()
            history = resp.json()
            if prompt_id in history:
                entry = history[prompt_id]
                if entry.get("status", {}).get("completed"):
                    logger.info(f"Workflow completed: {prompt_id}")
                    return entry
                if entry.get("status", {}).get("status_str") == "error":
                    raise RuntimeError(f"Workflow failed: {entry['status']}")
            time.sleep(poll_interval)
        raise TimeoutError(f"Workflow timeout after {self.timeout}s: {prompt_id}")

    def generate(
        self,
        workflow: Dict[str, Any],
        output_dir: Optional[str] = None,
    ) -> list:
        """提交工作流并下载生成结果

        Returns:
            生成的图片文件路径列表
        """
        prompt_id = self.submit(workflow)
        history = self.wait_for_result(prompt_id)

        output_dir = Path(output_dir) if output_dir else Path("outputs")
        output_dir.mkdir(parents=True, exist_ok=True)

        images = []
        for node_id, node_output in history.get("outputs", {}).items():
            for img_info in node_output.get("images", []):
                filename = img_info["filename"]
                # 从 ComfyUI 下载
                resp = requests.get(
                    f"{self.base_url}/view",
                    params={
                        "filename": filename,
                        "subfolder": img_info.get("subfolder", ""),
                        "type": img_info.get("type", "output"),
                    },
                    timeout=60,
                )
                resp.raise_for_status()
                save_path = output_dir / filename
                save_path.write_bytes(resp.content)
                images.append(str(save_path))
                logger.info(f"Downloaded: {save_path}")

        return images

    def load_workflow(self, path: str) -> Dict[str, Any]:
        """从 JSON 文件加载工作流"""
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


if __name__ == "__main__":
    import sys
    client = ComfyUIClient()
    workflow = client.load_workflow(sys.argv[1])
    print(client.generate(workflow))
