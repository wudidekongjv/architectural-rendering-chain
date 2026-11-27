FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 系统依赖（含中文字体，避免效果图文字乱码）
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3-pip python3.11-venv \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    fonts-noto-cjk fonts-dejavu \
    git wget curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python 依赖
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 应用代码
COPY src/ ./src/
COPY workflows/ ./workflows/
COPY web/dist/ ./web/dist/ 2>/dev/null || true

# 模型权重通过卷挂载，不打入镜像（镜像体积控制）
VOLUME ["/app/models", "/app/outputs", "/app/data"]

EXPOSE 8000 5173 8188

CMD ["python3", "src/api/main.py"]
