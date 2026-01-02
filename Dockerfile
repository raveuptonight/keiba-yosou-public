# FastAPI / Discord Bot 用 Dockerfile (GPU対応)
FROM nvidia/cuda:12.2.2-runtime-ubuntu22.04

WORKDIR /app

# Python 3.11をインストール
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3

# pipをアップグレード
RUN python -m pip install --upgrade pip

# Python依存パッケージ
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコード
COPY src/ ./src/

# モデルディレクトリ作成
RUN mkdir -p /app/models /app/logs /app/backtest_results

# 環境変数
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# FastAPI起動（デフォルト）
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
