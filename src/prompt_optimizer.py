"""LLM 提示词优化模块

将用户的简短中文/英文输入改写为结构化的建筑效果图英文提示词。
使用本地部署的 Qwen3-32B（vLLM OpenAI 兼容端点），纯文本转换，数据不出网。

设计要点：
- 这是 Pipeline 中的确定性节点，不是 Agent —— 无决策权、无路由、无循环
- 输出固定结构：主体 + 材质 + 光照 + 镜头 + 风格
- temperature=0.3 保证稳定性
"""

import json
import logging
import requests
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class OptimizeConfig:
    vllm_endpoint: str = "http://localhost:8000/v1/chat/completions"
    model: str = "Qwen/Qwen3-32B-AWQ"
    temperature: float = 0.3
    max_tokens: int = 512
    timeout: int = 60


SYSTEM_PROMPT = """You are an architectural rendering prompt optimizer for a professional architecture firm.

Convert the user's brief description into a structured English prompt for an architectural image generation model.

Output MUST follow this exact structure, comma-separated, no explanation:
[subject/building type], [architectural style], [materials], [lighting], [camera/lens], [environment], [color palette], [key details], architectural photography, professional rendering

Rules:
1. Expand vague terms into professional architectural vocabulary (e.g. "modern house" -> "contemporary minimalist villa with flat roof and floor-to-ceiling glazing")
2. Infer plausible lighting and camera details if not specified (e.g. "soft natural daylight", "wide-angle 24mm architectural lens")
3. Keep it concrete and visual, avoid abstract adjectives
4. Output in English only, one line, comma-separated
5. Do NOT include negative prompts or technical parameters

Example input: "现代别墅 带泳池"
Example output: contemporary minimalist villa with flat roof, clean Scandinavian modern style, white stucco walls and teal wooden shutters, soft diffused natural daylight, wide-angle 24mm architectural lens, coastal pine forest setting with infinity pool and wooden pergolas, white and teal with warm wood accents, rectangular pool with lounge chairs and ornamental grasses, architectural photography, professional rendering"""


class PromptOptimizer:
    """LLM 提示词优化器"""

    def __init__(self, config: Optional[OptimizeConfig] = None):
        self.config = config or OptimizeConfig()

    def optimize(self, user_input: str, image_hint: Optional[str] = None) -> str:
        """将用户输入优化为结构化英文提示词

        Args:
            user_input: 用户的简短描述（中英文均可）
            image_hint: 可选的图像类型提示（如 "interior" / "exterior"）

        Returns:
            结构化英文提示词
        """
        user_msg = user_input
        if image_hint:
            user_msg = f"{user_input}\n[Image context: {image_hint}]"

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        try:
            resp = requests.post(
                self.config.vllm_endpoint,
                json=payload,
                timeout=self.config.timeout,
            )
            resp.raise_for_status()
            result = resp.json()
            prompt = result["choices"][0]["message"]["content"].strip()
            logger.info(f"Prompt optimized: {user_input[:50]}... -> {prompt[:100]}...")
            return prompt
        except Exception as e:
            logger.error(f"Prompt optimization failed: {e}, falling back to original input")
            # 降级：LLM 不可用时直接使用原始输入，保证 Pipeline 不中断
            return user_input


# CLI 测试入口
if __name__ == "__main__":
    import sys
    text = sys.argv[1] if len(sys.argv) > 1 else "现代风格别墅 带泳池 庭院"
    opt = PromptOptimizer()
    print(opt.optimize(text))
