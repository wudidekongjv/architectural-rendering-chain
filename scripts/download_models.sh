#!/usr/bin/env bash
# 下载模型权重（本仓库不含模型文件）
# 用法: bash download_models.sh --all  或  bash download_models.sh sdxl flux

set -e

MODEL_ROOT="${MODEL_ROOT:-./models}"
# HuggingFace CLI check
if ! command -v huggingface-cli &> /dev/null; then
  echo "Installing huggingface-hub..."
  pip install -U huggingface-hub
fi

download_sdxl() {
  echo "=== Downloading SDXL 1.0 Base ==="
  mkdir -p "$MODEL_ROOT/checkpoints"
  huggingface-cli download stabilityai/stable-diffusion-xl-base-1.0 \
    sd_xl_base_1.0.safetensors --local-dir "$MODEL_ROOT/checkpoints"
}

download_flux() {
  echo "=== Downloading Flux.1-dev ==="
  mkdir -p "$MODEL_ROOT/flux" "$MODEL_ROOT/text_encoders"
  huggingface-cli download black-forest-labs/FLUX.1-dev --local-dir "$MODEL_ROOT/flux"
  echo "NOTE: Flux.1-dev requires license acceptance on HuggingFace"
}

download_controlnet() {
  echo "=== Downloading ControlNet-SDXL ==="
  mkdir -p "$MODEL_ROOT/controlnet"
  huggingface-cli download xinsir/controlnet-canny-sdxl-1.0 \
    --local-dir "$MODEL_ROOT/controlnet/canny"
  huggingface-cli download diffusers/controlnet-depth-sdxl-1.0 \
    --local-dir "$MODEL_ROOT/controlnet/depth"
  huggingface-cli download xinsir/controlnet-normal-sdxl-1.0 \
    --local-dir "$MODEL_ROOT/controlnet/normal"
}

download_depth() {
  echo "=== Downloading Depth Anything v2 ==="
  mkdir -p "$MODEL_ROOT/depth"
  huggingface-cli download depth-anything/Depth-Anything-V2-Large \
    depth_anything_v2_vitl.pth --local-dir "$MODEL_ROOT/depth"
}

download_qwen() {
  echo "=== Downloading Qwen3-32B-AWQ (for vLLM) ==="
  mkdir -p "$MODEL_ROOT/Qwen3-32B-AWQ"
  huggingface-cli download Qwen/Qwen3-32B-AWQ \
    --local-dir "$MODEL_ROOT/Qwen3-32B-AWQ"
}

download_esrgan() {
  echo "=== Downloading Real-ESRGAN ==="
  mkdir -p "$MODEL_ROOT/esrgan"
  wget -O "$MODEL_ROOT/esrgan/RealESRGAN_x4plus.pth" \
    https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth
}

case "${1:-}" in
  --all)
    download_sdxl
    download_flux
    download_controlnet
    download_depth
    download_qwen
    download_esrgan
    ;;
  sdxl)       download_sdxl ;;
  flux)       download_flux ;;
  controlnet) download_controlnet ;;
  depth)      download_depth ;;
  qwen)       download_qwen ;;
  esrgan)     download_esrgan ;;
  *)
    echo "Usage: $0 [--all|sdxl|flux|controlnet|depth|qwen|esrgan]"
    exit 1
    ;;
esac

echo "=== Download complete ==="
echo "Total disk space needed: ~60GB"
