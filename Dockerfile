# FastAPI / Discord Bot 用 Dockerfile
FROM python:3.11-slim

WORKDIR /app

# システム依存パッケージ
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python依存パッケージ
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコード
COPY src/ ./src/
COPY prompts/ ./prompts/

# モデルディレクトリ作成
RUN mkdir -p /app/models /app/logs

# 環境変数
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# FastAPI起動（デフォルト）
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
