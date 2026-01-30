# 機械学習用 Dockerfile
FROM python:3.11-slim

WORKDIR /app

# システム依存パッケージ（ML用 + git）
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    git \
    git-lfs \
    && rm -rf /var/lib/apt/lists/* \
    && git lfs install

# Python依存パッケージ
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコード
COPY src/ ./src/
COPY scripts/ ./scripts/

# モデルディレクトリ作成
RUN mkdir -p /app/models /app/logs

# 環境変数
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# デフォルトは学習スクリプト実行
CMD ["python", "-m", "src.models.train"]
