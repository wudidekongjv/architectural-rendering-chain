#!/usr/bin/env bash
# 训练 SDXL 风格 LoRA（使用 SD-Trainer）
# 注意：本脚本不随仓库自动执行，需在有 GPU 的环境手动运行
# 数据集：data/ 目录下 140 张建筑效果图 + 同名英文标签 txt（SD-Trainer 标准格式）

set -e

echo "=== SDXL Style LoRA Training (SD-Trainer) ==="
echo "Dataset: ./data (140 images + 140 captions)"
echo "Base model: stabilityai/sdxl-base-1.0"
echo "Hardware: single RTX 4090 24GB"
echo ""

# 前置检查
if [ ! -d ./data ]; then
  echo "ERROR: data/ directory not found"
  exit 1
fi

IMG_COUNT=$(find ./data -type f \( -iname "*.jpg" -o -iname "*.png" -o -iname "*.webp" \) | wc -l)
CAP_COUNT=$(find ./data -type f -iname "*.txt" | wc -l)
echo "Images: $IMG_COUNT, Captions: $CAP_COUNT"

if [ "$IMG_COUNT" -ne "$CAP_COUNT" ]; then
  echo "WARNING: image/caption count mismatch!"
fi

# 生成 SD-Trainer 配置（JSON 格式，由 WebUI 导出的同款配置）
cat > ./sd_trainer_config.json << 'JSON'
{
  "pretrained_model_name_or_path": "stabilityai/stable-diffusion-xl-base-1.0",
  "train_data_dir": "./data",
  "output_dir": "./models/lora",
  "resolution": 1024,
  "network_dim": 32,
  "network_alpha": 16,
  "learning_rate": 0.0001,
  "lr_scheduler": "cosine",
  "lr_warmup_steps": 100,
  "train_batch_size": 2,
  "gradient_accumulation_steps": 2,
  "max_train_steps": 3000,
  "save_every_n_steps": 500,
  "noise_offset": 0.1,
  "optimizer_type": "adamw8bit",
  "mixed_precision": "bf16",
  "enable_bucket": true,
  "min_bucket_reso": 768,
  "max_bucket_reso": 1344,
  "seed": 42
}
JSON

echo ""
echo "SD-Trainer config written to ./sd_trainer_config.json"
echo ""
echo "方式一：WebUI 训练（推荐）"
echo "  1. 启动 SD-Trainer:  python app.py"
echo "  2. 打开 Gradio 界面，LoRA 标签页"
echo "  3. 填写训练集目录 ./data，参数按 config 设置"
echo "  4. 点击开始训练"
echo ""
echo "方式二：命令行训练"
echo "  accelerate launch --num_processes=1 --mixed_precision=bf16 sd_trainer.py --config ./sd_trainer_config.json"

# 实际执行（取消注释以运行）
# accelerate launch --num_processes=1 --mixed_precision=bf16 sd_trainer.py --config ./sd_trainer_config.json

echo ""
echo "Training NOT executed. Uncomment the line above to start training."
echo "Expected: ~2-4 hours on single RTX 4090, output ~50-150MB safetensors"
