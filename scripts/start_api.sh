#!/bin/bash
# FastAPI起動スクリプト

cd "$(dirname "$0")/.."

source venv/bin/activate

echo "======================================"
echo "FastAPI サーバーを起動します"
echo "======================================"
echo "URL: http://localhost:8000"
echo "Docs: http://localhost:8000/docs"
echo "======================================"

python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
