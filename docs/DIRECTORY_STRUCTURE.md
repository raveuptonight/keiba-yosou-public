# ディレクトリ構造

## 概要

keiba-yosouプロジェクトのディレクトリ構造と各ディレクトリの役割を説明します。

---

## ルートディレクトリ

```
keiba-yosou/
├── .env                      # 環境変数（gitignore、機密情報含む）
├── .env.example              # 環境変数テンプレート
├── .gitignore                # Git除外設定
├── CLAUDE.md                 # Claude Code用プロジェクト指示書
├── README.md                 # プロジェクト概要
├── requirements.txt          # Python依存パッケージ
│
├── docs/                     # ドキュメント
├── scripts/                  # ユーティリティスクリプト
├── data/                     # データファイル（gitignore推奨）
├── models/                   # 学習済みモデル（.pkl等、gitignore推奨）
├── results/                  # 実行結果（gitignore推奨）
├── prompts/                  # LLMプロンプトテンプレート
├── notebooks/                # Jupyter Notebook（実験用）
├── sql/                      # アドホックSQLスクリプト
├── tests/                    # テストコード
└── src/                      # メインソースコード
```

---

## docs/ - ドキュメント

| ファイル | 説明 |
|---------|------|
| `API_DESIGN.md` | FastAPI設計書（エンドポイント、スキーマ、クエリ） |
| `API_SETUP.md` | API起動手順（セットアップガイド） |
| `ER_DIAGRAM.md` | データベースER図（27テーブル） |
| `INDEX_DESIGN.md` | インデックス設計（パフォーマンス最適化） |
| `JRA_VAN_SPEC.md` | JRA-VANデータ仕様（27データ種別） |
| `PREDICTION_FORMAT.md` | 予想結果JSONフォーマット仕様 |
| `SCHEDULER.md` | 自動予想スケジューラー仕様 |
| `DIRECTORY_STRUCTURE.md` | このファイル（ディレクトリ構造説明） |

---

## scripts/ - ユーティリティスクリプト

| ファイル | 説明 |
|---------|------|
| `start_api.sh` | FastAPI起動スクリプト |
| `check_db_data.py` | データベース接続確認 |

---

## src/ - メインソースコード

```
src/
├── __init__.py
├── config.py                # システム全体設定
├── exceptions.py            # システム全体の例外定義
│
├── api/                     # FastAPI（REST API）
│   ├── main.py              # FastAPIアプリエントリーポイント
│   ├── exceptions.py        # HTTP例外（FastAPI用）
│   ├── middleware/          # ミドルウェア（レート制限等）
│   ├── routes/              # エンドポイント
│   │   ├── races.py         # レース情報API
│   │   ├── predictions.py   # 予想生成API
│   │   ├── horses.py        # 馬情報API
│   │   ├── odds.py          # オッズ情報API
│   │   └── health.py        # ヘルスチェック
│   └── schemas/             # Pydanticスキーマ
│       ├── race.py
│       ├── prediction.py
│       ├── horse.py
│       ├── odds.py
│       └── common.py
│
├── db/                      # データベース層
│   ├── connection.py        # 同期DB接続（Discord Bot用）
│   ├── async_connection.py # 非同期DB接続（FastAPI用）
│   ├── table_names.py       # テーブル名マッピング（27テーブル）
│   ├── queries/             # SQLクエリ
│   │   ├── race_queries.py      # レース情報取得
│   │   ├── horse_queries.py     # 馬情報取得
│   │   ├── odds_queries.py      # オッズ情報取得
│   │   └── prediction_data.py   # 予想データ集約（最重要）
│   └── migrations/          # DBマイグレーション
│       └── 001_create_predictions_table.sql
│
├── services/                # ビジネスロジック層
│   ├── claude_client.py     # Claude API クライアント
│   ├── prediction_service.py # 予想生成サービス
│   ├── rate_limiter.py      # レート制限（5 req/min）
│   └── race_resolver.py     # レース仕様解決
│
├── discord/                 # Discord Bot
│   ├── bot.py               # Botメイン
│   ├── commands/            # コマンド（分割構成）
│   │   ├── __init__.py      # Cog一括登録
│   │   ├── prediction.py    # 予想関連（!predict, !today）
│   │   ├── stats.py         # 統計関連（!stats, !roi）
│   │   ├── betting.py       # 馬券推奨（!baken）
│   │   └── help.py          # ヘルプ（!help）
│   ├── decorators.py        # エラーハンドリングデコレーター
│   ├── scheduler.py         # 自動予想スケジューラー
│   └── formatters.py        # メッセージフォーマット
│
├── betting/                 # 馬券最適化
│   └── ticket_optimizer.py  # 馬券購入最適化
│
├── predict/                 # 予想パイプライン
│   ├── pipeline.py          # 基本予想パイプライン
│   ├── hybrid_pipeline.py   # ハイブリッド予想（ML+LLM）
│   └── reflection_pipeline.py # リフレクション予想
│
├── features/                # 特徴量生成（ML用）
│   └── feature_pipeline.py  # 特徴量生成パイプライン
│
└── models/                  # MLモデル（Pythonコード）
    ├── xgboost_model.py     # XGBoostモデル
    └── incremental_learning.py # 増分学習
```

---

## ディレクトリの役割

### api/ - REST APIサーバー

**目的**: FastAPIベースのREST APIサーバー

**主要機能**:
- レース情報取得（`GET /api/v1/races/today`）
- 予想生成（`POST /api/v1/predictions/generate`）
- 馬詳細情報取得（`GET /api/v1/horses/{kettonum}`）

**技術**:
- FastAPI + uvicorn
- asyncpg（非同期PostgreSQL）
- Pydantic（データバリデーション）

---

### db/ - データベース層

**目的**: PostgreSQL接続とクエリ管理

**主要機能**:
- 同期/非同期接続プール管理
- 27テーブルの統一的なクエリインターフェース
- 予想に必要な全データの効率的な集約

**重要ファイル**:
- `table_names.py`: テーブル名を一元管理（実際のテーブル名に簡単に対応可能）
- `queries/prediction_data.py`: 27テーブルから予想データを集約

---

### services/ - ビジネスロジック層

**目的**: 複数のモジュールにまたがる処理を統合

**主要機能**:
- Claude APIとの通信（`claude_client.py`）
- 予想生成ワークフロー（`prediction_service.py`）
- レート制限管理（`rate_limiter.py`）

---

### discord/ - Discord Bot

**目的**: Discord上での予想結果通知と対話

**主要機能**:
- コマンド処理（`!predict`, `!today`, `!stats`, `!baken`, `!help`）
- 自動予想スケジューラー（朝9時、レース1時間前）
- 予想結果のフォーマット表示

**アーキテクチャ**:
- `bot.py`: メインエントリーポイント、Cog管理
- `commands/`: コマンドCogを機能別に分割（保守性向上）
- `decorators.py`: エラーハンドリング共通化
- `formatters.py`: Discord メッセージフォーマット

---

### predict/ - 予想パイプライン

**目的**: 各種予想ロジックの実装

**種類**:
- **pipeline.py**: 基本予想（LLMのみ）
- **hybrid_pipeline.py**: ハイブリッド予想（ML前処理 → LLM）
- **reflection_pipeline.py**: リフレクション予想（失敗分析 → 改善）

---

### betting/ - 馬券最適化

**目的**: 予想結果から最適な馬券購入戦略を計算

**主要機能**:
- 期待値計算
- リスク分散
- 投資額配分

---

## 設計原則

### 1. 関心の分離（Separation of Concerns）

- **api/**: HTTP通信、リクエスト/レスポンス処理
- **db/**: データベース操作
- **services/**: ビジネスロジック
- **discord/**: UI/通知
- **predict/**: 予想アルゴリズム

### 2. 依存関係の方向

```
api/routes → services → db/queries
                ↓
         claude_client
```

### 3. テーブル名の柔軟性

`src/db/table_names.py`で一元管理することで、実際のテーブル名が変わっても簡単に対応可能。

---

## gitignore設定

以下のディレクトリ/ファイルはgit管理対象外：

```
.env                # 環境変数（APIキー等）
venv/               # 仮想環境
__pycache__/        # Python キャッシュ
*.pyc               # コンパイル済みPython
data/               # データファイル
models/*.pkl        # 学習済みモデル
results/            # 実行結果
*.log               # ログファイル
```

---

## 更新履歴

- **2024-12-28**: Discord Commands リファクタリング
  - `src/discord/commands.py` → `src/discord/commands/` ディレクトリに分割
  - 4つのCog: prediction, stats, betting, help
  - エラーハンドリング共通化（`decorators.py`）
- **2024-12-28**: ディレクトリ構造整理
  - `src/race_resolver.py` → `src/services/race_resolver.py`
  - `src/pipeline.py` → `src/predict/pipeline.py`
  - `src/hybrid_pipeline.py` → `src/predict/hybrid_pipeline.py`
  - `src/reflection_pipeline.py` → `src/predict/reflection_pipeline.py`
- **2024-12-28**: FastAPI実装完了
- **2024-12-27**: Discord Bot実装完了
- **2024-12-26**: プロジェクト開始
