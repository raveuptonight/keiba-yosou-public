# CLAUDE.md - keiba-yosou プロジェクト指示書

## プロジェクト概要

JRA-VANの公式競馬データを活用し、機械学習（XGBoost + LightGBM）による競馬予想システム。
データ分析と統計的手法を組み合わせた予想を提供する。

## リポジトリ情報

- **リモート**: https://github.com/raveuptonight/keiba-yosou
- **ブランチ戦略**: main（本番）、develop（開発）、feature/*（機能開発）

### Git操作のルール

- 作業前に `git pull` で最新化
- コミットは機能単位で細かく
- コミットメッセージは日本語OK、簡潔に
- pushする前に動作確認

## ドキュメント

詳細は以下を参照：

| ファイル | 内容 |
|---------|------|
| `docs/PROJECT_OVERVIEW.md` | システム構成、ディレクトリ構成、開発フェーズ |
| `docs/JRA_VAN_SPEC.md` | JRA-VANデータ仕様、テーブル詳細、SQLクエリ例 |
| `docs/DEVELOPMENT_ROADMAP.md` | 設計思想、特徴量設計、プロンプト設計 |

## 技術スタック

- **言語**: Python 3.11+
- **DB**: PostgreSQL 18（ローカル）→ Neon（将来）
- **データ**: JRA-VAN Data Lab. + mykeibadb
- **ML**: XGBoost + LightGBM（アンサンブル）
- **環境**: WSL2 + VS Code + Docker

## ディレクトリ構成

```
keiba-yosou/
├── CLAUDE.md            # この指示書
├── docs/                # ドキュメント
├── src/
│   ├── db/              # DB接続、クエリ
│   ├── features/        # 特徴量生成
│   ├── models/          # 機械学習モデル
│   ├── api/             # FastAPI
│   └── discord/         # Discord Bot
├── models/              # 学習済みモデル保存
├── scripts/             # ユーティリティ
├── tests/               # テスト
├── .env.example         # 環境変数テンプレート
└── requirements.txt     # Python依存関係
```

## 現在のフェーズ

**Phase 1: データ基盤構築**

- [x] JRA-VAN契約済み
- [x] mykeibadbセットアップ済み
- [x] ローカルPostgreSQL構築済み
- [ ] データ取り込み中（数日かかる）
- [ ] テーブル構造確認
- [ ] 基本クエリ作成

### 次のタスク

1. ディレクトリ構成の作成
2. DB接続モジュール（src/db/connection.py）
3. 基本クエリ（src/db/queries.py）
4. テーブル構造確認スクリプト

## コーディング規約

### Python

- フォーマッター: black
- リンター: ruff
- 型ヒント: 推奨
- docstring: Google style

### 命名規則

- ファイル名: snake_case
- クラス名: PascalCase
- 関数・変数: snake_case
- 定数: UPPER_SNAKE_CASE

### インポート順序

```python
# 標準ライブラリ
import os
from datetime import datetime

# サードパーティ
import pandas as pd
import xgboost as xgb

# ローカル
from src.db.connection import get_connection
```

## DB接続情報

### ローカルPostgreSQL

```
Host: localhost
Port: 5432
Database: keiba_db
User: postgres
```

※パスワードは `.env` で管理（.env.example参照）

### 接続確認

```bash
psql -U postgres -d keiba_db -c "SELECT version();"
```

## よく使うコマンド

```bash
# 仮想環境作成
python -m venv venv
source venv/bin/activate

# 依存関係インストール
pip install -r requirements.txt

# テスト実行
pytest tests/

# フォーマット
black src/

# リント
ruff check src/
```

## 注意事項

1. **JV-LinkはWindows専用** - WSLからは直接使えない、データはmykeibadb経由
2. **データ取り込みに数日かかる** - 1986年からの全データ
3. **.envはコミットしない** - .gitignoreに追加済みか確認
4. **JRA-VANデータの再配布禁止** - ライセンス注意

## 困ったとき

- テーブル名がわからない → `\dt` でテーブル一覧
- カラム名がわからない → `\d テーブル名` で構造確認
- JRA-VAN仕様 → `docs/JRA_VAN_SPEC.md` 参照
