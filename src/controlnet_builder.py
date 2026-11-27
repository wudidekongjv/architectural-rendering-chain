"""ControlNet 条件图生成模块

从用户上传的白模/线稿/参考图生成三类结构条件图：
- Canny 线稿：锁定轮廓
- Depth Anything v2 深度图：锁定空间层次
- 法线图：锁定材质朝向

这些是确定性图像转换，非 Agent 决策。
"""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ControlNetBuilder:
    """ControlNet 结构条件图生成器"""

    def __init__(
        self,
        depth_model_path: str = "models/depth/depth_anything_v2_vitl.pth",
        depth_script: str = "third_party/Depth-Anything-V2/inference.py",
        canny_low: int = 100,
        canny_high: int = 200,
    ):
        self.depth_model_path = depth_model_path
        self.depth_script = depth_script
        self.canny_low = canny_low
        self.canny_high = canny_high

    def build_canny(self, image_path: str, output_path: Optional[str] = None) -> str:
        """生成 Canny 线稿条件图

        Args:
            image_path: 输入图片路径
            output_path: 输出路径，不传则自动生成

        Returns:
            线稿图路径
        """
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Cannot read image: {image_path}")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(blurred, self.canny_low, self.canny_high)

        if output_path is None:
            output_path = str(Path(tempfile.gettempdir()) / f"canny_{Path(image_path).stem}.png")
        cv2.imwrite(output_path, edges)
        logger.info(f"Canny map saved: {output_path}")
        return output_path

    def build_depth(self, image_path: str, output_path: Optional[str] = None) -> str:
        """生成深度条件图（调用 Depth Anything v2）

        Args:
            image_path: 输入图片路径
            output_path: 输出路径

        Returns:
            深度图路径
        """
        if output_path is None:
            output_path = str(Path(tempfile.gettempdir()) / f"depth_{Path(image_path).stem}.png")

        cmd = [
            "python", self.depth_script,
            "--model", self.depth_model_path,
            "--img-path", image_path,
            "--pred-only",
            "--outdir", str(Path(output_path).parent),
        ]
        logger.info(f"Running depth estimation: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f"Depth Anything failed ({e}), using grayscale fallback")
            # 降级：用灰度图近似深度，保证 Pipeline 不中断
            self._grayscale_fallback(image_path, output_path)
        return output_path

    def build_normal(self, depth_path: str, output_path: Optional[str] = None) -> str:
        """从深度图生成法线图（梯度换算）

        Args:
            depth_path: 深度图路径
            output_path: 输出路径

        Returns:
            法线图路径
        """
        depth = cv2.imread(depth_path, cv2.IMREAD_GRAYSCALE)
        if depth is None:
            raise ValueError(f"Cannot read depth map: {depth_path}")

        # Sobel 梯度 → 法线向量
        dzdx = cv2.Sobel(depth.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
        dzdy = cv2.Sobel(depth.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
        normal = np.dstack([-dzdx, -dzdy, np.ones_like(depth, dtype=np.float32)])
        normal /= np.linalg.norm(normal, axis=2, keepdims=True)
        normal = ((normal + 1) * 127.5).astype(np.uint8)

        if output_path is None:
            output_path = str(Path(tempfile.gettempdir()) / f"normal_{Path(depth_path).stem}.png")
        cv2.imwrite(output_path, normal)
        logger.info(f"Normal map saved: {output_path}")
        return output_path

    def build_all(self, image_path: str, output_dir: Optional[str] = None) -> Dict[str, str]:
        """生成全部三类条件图

        Returns:
            {"canny": path, "depth": path, "normal": path}
        """
        out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="controlnet_"))
        out.mkdir(parents=True, exist_ok=True)
        stem = Path(image_path).stem

        canny = self.build_canny(image_path, str(out / f"{stem}_canny.png"))
        depth = self.build_depth(image_path, str(out / f"{stem}_depth.png"))
        normal = self.build_normal(depth, str(out / f"{stem}_normal.png"))

        return {"canny": canny, "depth": depth, "normal": normal}

    @staticmethod
    def _grayscale_fallback(image_path: str, output_path: str):
        """深度模型不可用时的灰度降级"""
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        cv2.imwrite(output_path, img)


if __name__ == "__main__":
    import sys
    builder = ControlNetBuilder()
    print(builder.build_all(sys.argv[1]))
