# システム設計書 - keiba-yosou

**目標: 回収率200%達成のための競馬予想システム**

## 1. システムアーキテクチャ

### 全体構成

```
┌─────────────────────────────────────────────────────────┐
│                    フロントエンド層                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐         ┌────────────────┐          │
│  │ Streamlit UI │         │  Discord Bot   │          │
│  │              │         │                │          │
│  │ ・レース選択  │         │ ・予想通知      │          │
│  │ ・予想実行    │         │ ・結果報告      │          │
│  │ ・結果表示    │         │ ・統計表示      │          │
│  └──────┬───────┘         └────────┬───────┘          │
│         │                          │                  │
└─────────┼──────────────────────────┼──────────────────┘
          │                          │
          ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│                   アプリケーション層                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │           FastAPI (REST API)                     │  │
│  │                                                  │  │
│  │  GET  /races              - レース一覧取得        │  │
│  │  GET  /races/{id}         - レース詳細取得        │  │
│  │  POST /predict            - 予想実行             │  │
│  │  GET  /predictions        - 予想履歴一覧          │  │
│  │  GET  /predictions/{id}   - 予想詳細取得          │  │
│  │  POST /reflect            - 反省実行             │  │
│  │  GET  /stats              - 統計情報取得          │  │
│  └────────────────┬─────────────────────────────────┘  │
│                   │                                     │
│         ┌─────────┼─────────┬──────────────┐           │
│         ▼         ▼         ▼              ▼           │
│  ┌──────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Pipeline │ │ LLM     │ │ DB       │ │ Discord  │  │
│  │ Service  │ │ Client  │ │ Service  │ │ Service  │  │
│  └──────────┘ └─────────┘ └──────────┘ └──────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
          │                          │
          ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│                      データ層                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │             PostgreSQL (統合管理)                 │  │
│  │                                                  │  │
│  │  スキーマ: jravan                                │  │
│  │    ・レースデータ                                │  │
│  │    ・馬データ                                    │  │
│  │    ・騎手データ                                  │  │
│  │                                                  │  │
│  │  スキーマ: predictions                           │  │
│  │    ・予想履歴                                    │  │
│  │    ・的中結果                                    │  │
│  │    ・回収率統計                                  │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 技術スタック

### フロントエンド
- **Streamlit**: Web UI（Pythonだけで実装可能、学習コスト低）
- **discord.py**: Discord Bot

### バックエンド
- **FastAPI**: REST API（高速、非同期対応、自動ドキュメント生成）
- **Pydantic**: データバリデーション
- **既存モジュール**:
  - `src/pipeline.py`: 予想パイプライン
  - `src/predict/llm.py`: LLMクライアント
  - `src/db/connection.py`: DB接続

### データベース
- **PostgreSQL**: JRA-VANデータ + 予想結果・履歴（統合管理）
  - スキーマ分離: `jravan`（JRA-VAN）、`predictions`（予想システム）

### その他
- **APScheduler**: 定期実行（毎日の予想自動化）
- **python-dotenv**: 環境変数管理

---

## 3. データフロー

### 3.1 予想実行フロー

```
[UI/Bot] → [POST /predict]
           ↓
    [FastAPI Controller]
           ↓
    [Pipeline Service]
           ↓
    ┌──────┴──────┐
    ▼             ▼
[DB Service]  [LLM Client]
    │             │
    ▼             ▼
[PostgreSQL]  [Gemini API]
    │             │
    └──────┬──────┘
           ▼
    [分析→予想→保存]
           ↓
    [Discord Service]
           ↓
    [Discord通知]
           ↓
    [UI/Botに結果返却]
```

### 3.2 反省実行フロー

```
[レース結果確定]
      ↓
[POST /reflect]
      ↓
[Pipeline Service]
      ↓
[分析→反省→学習内容保存]
      ↓
[Discord通知（的中報告/改善点）]
```

---

## 4. DB設計（予想結果DB - PostgreSQL）

### 4.0 スキーマ作成

```sql
-- 予想システム用スキーマ
CREATE SCHEMA IF NOT EXISTS predictions;

-- JRA-VANデータ用スキーマ（mykeibadbが自動作成）
-- CREATE SCHEMA IF NOT EXISTS jravan;
```

### 4.1 predictions テーブル

```sql
CREATE TABLE predictions.predictions (
    id SERIAL PRIMARY KEY,
    race_id VARCHAR(20) NOT NULL,       -- レースID（JRA-VAN）
    race_name VARCHAR(100) NOT NULL,    -- レース名
    race_date DATE NOT NULL,            -- レース日
    venue VARCHAR(50),                  -- 競馬場

    -- 予想内容（JSON）
    analysis_result JSONB,              -- フェーズ1分析結果（JSON）
    prediction_result JSONB,            -- フェーズ2予想結果（JSON）

    -- 投資・期待値
    total_investment INTEGER,           -- 総投資額（円）
    expected_return INTEGER,            -- 期待回収額（円）
    expected_roi NUMERIC(5,2),          -- 期待ROI

    -- 実行情報
    llm_model VARCHAR(50),              -- 使用LLMモデル
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_race_id UNIQUE(race_id)
);

-- インデックス作成
CREATE INDEX idx_predictions_race_date ON predictions.predictions(race_date);
CREATE INDEX idx_predictions_venue ON predictions.predictions(venue);
```

### 4.2 results テーブル

```sql
CREATE TABLE predictions.results (
    id SERIAL PRIMARY KEY,
    prediction_id INTEGER NOT NULL,     -- predictionsテーブルの外部キー

    -- 実際の結果
    actual_result JSONB,                -- 実際のレース結果（JSON）

    -- 収支
    total_return INTEGER,               -- 実際の回収額（円）
    profit INTEGER,                     -- 収支（円）
    actual_roi NUMERIC(5,2),            -- 実際のROI

    -- 精度
    prediction_accuracy NUMERIC(3,2),   -- 予想精度（0.0-1.0）

    -- 反省内容
    reflection_result JSONB,            -- フェーズ3反省結果（JSON）

    -- 更新日時
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_prediction FOREIGN KEY (prediction_id)
        REFERENCES predictions.predictions(id) ON DELETE CASCADE
);

-- インデックス作成
CREATE INDEX idx_results_prediction_id ON predictions.results(prediction_id);
```

### 4.3 stats テーブル（統計情報）

```sql
CREATE TABLE predictions.stats (
    id SERIAL PRIMARY KEY,
    period VARCHAR(20) NOT NULL,        -- 集計期間（daily/weekly/monthly/all）
    start_date DATE,
    end_date DATE,

    -- 基本統計
    total_races INTEGER,                -- 予想レース数
    total_investment INTEGER,           -- 総投資額
    total_return INTEGER,               -- 総回収額
    total_profit INTEGER,               -- 総収支
    roi NUMERIC(5,2),                   -- 回収率

    -- 的中率
    hit_count INTEGER,                  -- 的中数
    hit_rate NUMERIC(3,2),              -- 的中率

    -- その他
    best_roi NUMERIC(5,2),              -- 最高ROI
    worst_roi NUMERIC(5,2),             -- 最低ROI

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_period UNIQUE(period, start_date, end_date)
);

-- インデックス作成
CREATE INDEX idx_stats_period ON predictions.stats(period);
CREATE INDEX idx_stats_date_range ON predictions.stats(start_date, end_date);
```

---

## 5. API設計（FastAPI）

### 5.1 エンドポイント一覧

#### レース関連

```python
GET /api/races
  - クエリパラメータ:
    - date: レース日（YYYY-MM-DD）
    - venue: 競馬場
  - レスポンス: レース一覧

GET /api/races/{race_id}
  - レスポンス: レース詳細
```

#### 予想関連

```python
POST /api/predict
  - ボディ:
    {
      "race_id": "202412280506",
      "temperature": 0.3,
      "phase": "all"  // analyze, predict, all
    }
  - レスポンス: 予想結果

GET /api/predictions
  - クエリパラメータ:
    - limit: 取得件数
    - offset: オフセット
    - date: 日付フィルター
  - レスポンス: 予想履歴一覧

GET /api/predictions/{prediction_id}
  - レスポンス: 予想詳細
```

#### 反省関連

```python
POST /api/reflect
  - ボディ:
    {
      "prediction_id": 123,
      "actual_result": {...}
    }
  - レスポンス: 反省結果
```

#### 統計関連

```python
GET /api/stats
  - クエリパラメータ:
    - period: daily/weekly/monthly/all
  - レスポンス: 統計情報

GET /api/stats/roi-history
  - レスポンス: ROI推移グラフ用データ
```

---

## 6. Discord Bot設計

### 6.1 通知フォーマット

#### 予想完了通知

```
🏇 【予想完了】有馬記念

📅 2024/12/28 (日) 15:25 中山11R

◎本命: 3番 サンプルホース3
○対抗: 2番 サンプルホース2
▲単穴: 5番 サンプルホース5

💰 推奨馬券
・3連複 [2-3-5] 500円
・ワイド [2-3] 300円

投資額: 800円
期待回収: 1,600円
期待ROI: 200.0%

📊 詳細: https://your-app/predictions/123
```

#### 的中報告

```
🎉 【的中！】有馬記念

3連複 [2-5-1] 的中！
払戻: 2,150円

投資: 800円
回収: 2,150円
ROI: 268.8%

今月の成績:
的中率: 45.5% (5/11)
回収率: 183.2%
```

### 6.2 Botコマンド

```
!predict {race_id}     - 予想実行
!today                 - 本日のレース一覧
!stats [期間]          - 統計表示
!roi                   - 回収率グラフ
!help                  - ヘルプ
```

---

## 7. Streamlit UI設計

### 7.1 画面構成

```
┌─────────────────────────────────────┐
│  🏇 競馬予想システム（回収率200%目標） │
├─────────────────────────────────────┤
│                                     │
│  サイドバー                          │
│  ├ 📅 レース選択                    │
│  ├ ⚙️  予想設定                     │
│  └ 📊 統計情報                      │
│                                     │
│  メインエリア                        │
│  ┌─────────────────────────────┐   │
│  │ タブ1: 予想実行                │   │
│  │  - レース情報表示              │   │
│  │  - 予想実行ボタン              │   │
│  │  - 結果表示エリア              │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │ タブ2: 予想履歴                │   │
│  │  - 過去の予想一覧              │   │
│  │  - フィルター機能              │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │ タブ3: 統計・分析              │   │
│  │  - ROI推移グラフ               │   │
│  │  - 的中率統計                  │   │
│  │  - 馬場別成績                  │   │
│  └─────────────────────────────┘   │
│                                     │
└─────────────────────────────────────┘
```

### 7.2 主要機能

1. **レース選択**
   - 日付カレンダー
   - 競馬場選択
   - レース一覧表示

2. **予想実行**
   - フェーズ選択（分析のみ/予想まで/全フェーズ）
   - Temperature調整スライダー
   - 実行ボタン
   - プログレスバー

3. **結果表示**
   - 予想内容（本命・対抗・穴馬）
   - 推奨馬券
   - 期待値・ROI
   - JSON詳細（折りたたみ可）

4. **統計ダッシュボード**
   - 回収率グラフ（Plotly）
   - 的中率円グラフ
   - 馬場別/距離別成績

---

## 8. ディレクトリ構成（拡張版）

```
keiba-yosou/
├── CLAUDE.md
├── README.md
├── README_USAGE.md
├── requirements.txt
├── .env
├── .gitignore
│
├── docs/                      # ドキュメント
│   ├── PROJECT_OVERVIEW.md
│   ├── JRA_VAN_SPEC.md
│   ├── DEVELOPMENT_ROADMAP.md
│   └── SYSTEM_DESIGN.md       # ← このファイル
│
├── src/
│   ├── __init__.py
│   ├── pipeline.py            # 既存: 予想パイプライン
│   │
│   ├── api/                   # 【新規】FastAPI
│   │   ├── __init__.py
│   │   ├── main.py            # FastAPIアプリ
│   │   ├── routes/            # ルーティング
│   │   │   ├── races.py
│   │   │   ├── predictions.py
│   │   │   └── stats.py
│   │   ├── schemas/           # Pydanticスキーマ
│   │   │   ├── race.py
│   │   │   ├── prediction.py
│   │   │   └── stats.py
│   │   └── dependencies.py    # 依存性注入
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py      # 既存: PostgreSQL接続
│   │   ├── queries.py         # 【新規】クエリ集
│   │   └── results.py         # 【新規】予想結果DB（SQLite）
│   │
│   ├── features/              # 特徴量生成（未実装）
│   │   └── __init__.py
│   │
│   ├── predict/
│   │   ├── __init__.py
│   │   └── llm.py             # 既存: LLMクライアント
│   │
│   ├── services/              # 【新規】ビジネスロジック
│   │   ├── __init__.py
│   │   ├── pipeline_service.py   # パイプライン実行
│   │   ├── race_service.py       # レース情報取得
│   │   ├── prediction_service.py # 予想管理
│   │   └── stats_service.py      # 統計計算
│   │
│   └── discord/               # 【新規】Discord Bot
│       ├── __init__.py
│       ├── bot.py             # Botメイン
│       ├── commands.py        # コマンド定義
│       └── formatters.py      # 通知フォーマット
│
├── app.py                     # 【新規】Streamlit UI
│
├── scripts/
│   ├── run_prediction.py      # 既存: CLI実行
│   ├── explore_db.py          # 【新規】DB探索
│   ├── init_results_db.py     # 【新規】結果DB初期化
│   └── run_bot.py             # 【新規】Bot起動
│
├── prompts/                   # 既存: プロンプト
│   ├── analyze.txt
│   ├── predict.txt
│   └── reflect.txt
│
├── tests/
│   ├── mock_data/
│   │   ├── sample_race.json
│   │   └── sample_result.json
│   └── test_*.py              # 【新規】テストコード
│
├── data/                      # 【新規】データ保存
│   └── predictions.db         # SQLite（予想結果）
│
└── results/                   # 既存: 予想結果JSON
    └── prediction_*.json
```

---

## 9. 実装フェーズ

### Phase 1: データ層（1-2日）
- [ ] 予想結果DB設計・実装（SQLite）
- [ ] DBサービス実装（`src/db/results.py`）
- [ ] 初期化スクリプト（`scripts/init_results_db.py`）

### Phase 2: API層（2-3日）
- [ ] FastAPIセットアップ
- [ ] 予想エンドポイント実装
- [ ] 統計エンドポイント実装
- [ ] Pydanticスキーマ定義

### Phase 3: Discord Bot（1-2日）
- [ ] Bot基本実装
- [ ] 予想通知機能
- [ ] コマンド実装
- [ ] フォーマッター実装

### Phase 4: Streamlit UI（2-3日）
- [ ] 基本レイアウト
- [ ] レース選択機能
- [ ] 予想実行機能
- [ ] 統計ダッシュボード

### Phase 5: 統合・テスト（1-2日）
- [ ] 全体結合テスト
- [ ] エラーハンドリング
- [ ] ログ出力
- [ ] ドキュメント整備

---

## 10. 環境変数（.env追加分）

```bash
# 既存のPostgreSQL設定をそのまま使用
# LOCAL_DB_HOST=localhost
# LOCAL_DB_PORT=5432
# LOCAL_DB_NAME=keiba_db  ← JRA-VANデータ + 予想結果を統合管理
# LOCAL_DB_USER=postgres
# LOCAL_DB_PASSWORD=your_password_here

# Discord Bot
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_CHANNEL_ID=123456789

# FastAPI
API_HOST=0.0.0.0
API_PORT=8000

# その他
ENABLE_DISCORD_NOTIFICATION=true
AUTO_PREDICT_ENABLED=false
```

---

## 11. まとめ

このシステム設計により：

✅ **UI**: Streamlitで直感的な操作
✅ **通知**: Discord Botで自動通知
✅ **API**: FastAPIで拡張性確保
✅ **DB**: PostgreSQLで予想履歴とJRA-VANデータを統合管理
✅ **統計**: 回収率200%達成に向けた分析基盤

**PostgreSQLのメリット:**
- JRA-VANデータと予想結果を1つのDBで管理
- スキーマ分離で論理的に整理
- 強力なJOIN機能で高度な分析が可能
- 同時アクセス・トランザクション対応

データ到着後すぐに本格運用できる体制が整います！
