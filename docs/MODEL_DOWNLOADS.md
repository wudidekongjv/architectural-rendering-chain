# 模型下载地址清单

> 本仓库不包含任何模型权重文件（体积过大且涉及许可）。请按下列地址自行下载并放到指定目录。
> 下载脚本：`bash scripts/download_models.sh --all`

## 1. SDXL 1.0 Base（初稿底模）

| 项目 | 内容 |
|---|---|
| 用途 | 多候选初稿生成（1024×1024） |
| 显存 | fp16 约 7GB |
| 许可 | OpenRAIL++（商用需遵守使用限制） |
| 地址 | https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0 |
| 文件 | `sd_xl_base_1.0.safetensors` |
| 放置 | `models/checkpoints/` |

```bash
huggingface-cli download stabilityai/stable-diffusion-xl-base-1.0 \
  sd_xl_base_1.0.safetensors --local-dir models/checkpoints
```

## 2. Flux.1-dev（精修底模）

| 项目 | 内容 |
|---|---|
| 用途 | 材质与光影精修（img2img, denoise=0.45） |
| 显存 | fp8 约 12GB / bf16 约 24GB |
| 许可 | Flux.1-dev Non-Commercial License（**商用需申请许可**） |
| 地址 | https://huggingface.co/black-forest-labs/FLUX.1-dev |
| 放置 | `models/checkpoints/`（含 T5-XXL 文本编码器） |

```bash
huggingface-cli download black-forest-labs/FLUX.1-dev --local-dir models/flux
```

> 若需商用，可改用 FLUX.1-schnell（Apache 2.0）：https://huggingface.co/black-forest-labs/FLUX.1-schnell

## 3. ControlNet-SDXL（结构控制）

| 条件类型 | 模型 | 地址 |
|---|---|---|
| 线稿 (Canny) | xinsir/controlnet-canny-sdxl-1.0 | https://huggingface.co/xinsir/controlnet-canny-sdxl-1.0 |
| 深度 (Depth) | diffusers/controlnet-depth-sdxl-1.0 | https://huggingface.co/diffusers/controlnet-depth-sdxl-1.0 |
| 法线 (Normal) | xinsir/controlnet-normal-sdxl-1.0 | https://huggingface.co/xinsir/controlnet-normal-sdxl-1.0 |

放置目录：`models/controlnet/`

## 4. Depth Anything v2（深度图生成）

| 项目 | 内容 |
|---|---|
| 用途 | 从白模/线稿生成深度条件图 |
| 型号 | ViT-L（推荐）/ ViT-B（轻量） |
| 许可 | Apache 2.0 |
| 地址 | https://huggingface.co/depth-anything/Depth-Anything-V2-Large |
| 文件 | `depth_anything_v2_vitl.pth` |
| 放置 | `models/depth/` |

## 5. Qwen3-32B（LLM 提示词优化）

| 项目 | 内容 |
|---|---|
| 用途 | 将用户简短输入优化为结构化建筑效果图提示词 |
| 显存 | fp16 约 64GB / AWQ 4bit 约 20GB |
| 许可 | Apache 2.0 |
| 地址 | https://huggingface.co/Qwen/Qwen3-32B |
| AWQ 量化版 | https://huggingface.co/Qwen/Qwen3-32B-AWQ |
| 部署 | vLLM OpenAI 兼容端点 |

```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3-32B-AWQ \
  --quantization awq --port 8000 --gpu-memory-utilization 0.9
```

## 6. 风格 LoRA（本项目训练产物）

| 项目 | 内容 |
|---|---|
| 用途 | 统一建筑效果图风格 |
| 基座 | SDXL 1.0 |
| 参数 | rank=32, alpha=16, dim=32 |
| 训练数据 | `data/` 目录 140 张建筑效果图 + 英文标签 |
| 许可 | 项目自有 |
| 放置 | `models/lora/` |

> 本仓库**不含**训练好的 LoRA 权重（需自行用 `scripts/train_lora.sh` 训练）。训练数据已随仓库提供。

## 7. Real-ESRGAN（可选超分）

| 项目 | 内容 |
|---|---|
| 用途 | 1024 → 2048 超分放大 |
| 地址 | https://github.com/xinntao/Real-ESRGAN |
| 权重 | https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth |
| 放置 | `models/esrgan/` |

## 模型存放目录总览

```
models/
├── checkpoints/
│   ├── sd_xl_base_1.0.safetensors
│   └── flux1-dev.safetensors
├── controlnet/
│   ├── controlnet-canny-sdxl-1.0.safetensors
│   ├── controlnet-depth-sdxl-1.0.safetensors
│   └── controlnet-normal-sdxl-1.0.safetensors
├── depth/
│   └── depth_anything_v2_vitl.pth
├── lora/               # 训练产物，不随仓库分发
├── esrgan/
│   └── RealESRGAN_x4plus.pth
└── text_encoders/      # Flux 所需 T5-XXL
```

## 硬件要求

| 组件 | 推荐配置 | 最低配置 |
|---|---|---|
| GPU | 2 × RTX 4090 24GB | 1 × RTX 3090 24GB |
| CPU | 16 核 | 8 核 |
| 内存 | 128GB DDR4 ECC | 64GB |
| 存储 | 2TB NVMe（模型约 60GB + 数据集 45MB） | 1TB |
| 系统 | Ubuntu 22.04 + CUDA 12.1 + PyTorch 2.3 | Ubuntu 20.04 + CUDA 11.8 |

> **A100 成本评估**：A100 40GB 云主机约 12–18 元/小时，包月约 1.5–2.5 万元。采用 4bit 量化后 4090 24GB 即可承载，硬件一次性约 1.5 万元，约 1 个月回本。
