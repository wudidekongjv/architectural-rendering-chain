#!/usr/bin/env bash
# 训练 SDXL 风格 LoRA
# 注意：本脚本不随仓库自动执行，需在有 GPU 的环境手动运行
# 数据集：data/ 目录下 140 张建筑效果图 + 同名英文标签 txt（kohya_ss 标准格式）

set -e

echo "=== SDXL Style LoRA Training ==="
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

# kohya_ss 训练参数（关键参数与简历一致）
ACCELERATE_ARGS="--num_processes=1 --mixed_precision=bf16"

TRAIN_ARGS=(
  --pretrained_model_name_or_path="stabilityai/stable-diffusion-xl-base-1.0"
  --train_data_dir="./data"
  --resolution=1024
  --output_dir="./models/lora"
  --network_module=networks.lora
  --network_dim=32
  --network_alpha=16
  --learning_rate=1e-4
  --lr_scheduler=cosine
  --lr_warmup_steps=100
  --train_batch_size=2
  --gradient_accumulation_steps=2
  --max_train_steps=3000
  --save_every_n_steps=500
  --noise_offset=0.1
  --optimizer_type=adamw8bit
  --mixed_precision=bf16
  --enable_bucket
  --min_bucket_reso=768
  --max_bucket_reso=1344
  --seed=42
)

echo ""
echo "Command to run with kohya_ss:"
echo "accelerate launch $ACCELERATE_ARGS train_network.py ${TRAIN_ARGS[@]}"

# 实际执行（取消注释以运行）
# accelerate launch $ACCELERATE_ARGS train_network.py "${TRAIN_ARGS[@]}"

echo ""
echo "Training NOT executed. Uncomment the line above to start training."
echo "Expected: ~2-4 hours on single RTX 4090, output ~50-150MB safetensors"
