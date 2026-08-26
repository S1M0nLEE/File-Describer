# FileKG — Docker 演示镜像（hash 嵌入，快速索引，开箱即用）
FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FILEKG_EMBEDDING_BACKEND=hash \
    FILEKG_INDEX_FAST=1 \
    FILEKG_API_MANUAL_LOAD=false \
    FILEKG_API_PRELOAD_GRAPH=true \
    FILEKG_API_HEARTBEAT_ENABLED=false \
    FILEKG_NO_RELOAD=1 \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1

RUN python scripts/generate_dataset.py \
    && python scripts/index_directory.py data/dataset --clear

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=5)"

CMD ["python", "scripts/run_server.py", "--no-reload"]
