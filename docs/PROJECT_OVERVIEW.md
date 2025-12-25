# keiba-yosou: 競馬予想AIプロジェクト

## プロジェクト概要

JRA-VANの公式データを活用し、LLM（Claude）による競馬予想システムを構築するプロジェクト。

### 目標

- JRA-VANデータを分析し、レース予想を行うAIシステムの開発
- データ分析とLLMの推論能力を組み合わせたハイブリッド予想
- 将来的にはクラウド（Neon）へのDB移行を視野に入れた設計

## システム構成

```
┌─────────────────────────────┐
│  ローカルWindows            │
│  ・JV-Link（JRA-VAN API）   │
│  ・mykeibadb               │
│  ・PostgreSQL              │
└──────────┬──────────────────┘
           │ SQLクエリ
           ▼
┌─────────────────────────────┐
│  Python アプリケーション     │
│  ・データ抽出・整形          │
│  ・特徴量生成               │
│  ・LLMプロンプト生成         │
└──────────┬──────────────────┘
           │ API呼び出し
           ▼
┌─────────────────────────────┐
│  Claude API                 │
│  ・予想生成                  │
│  ・展開予想                  │
└─────────────────────────────┘
```

### 将来構成（クラウド移行後）

```
[ローカルWindows]
  JV-Link → mykeibadb → PostgreSQL (ローカル)
      ↓ 週次で同期
[Neon]
  PostgreSQL ← 予想botはここを参照
```

## 技術スタック

- **言語**: Python 3.11+
- **データベース**: PostgreSQL 18.x（ローカル）、Neon（将来）
- **データソース**: JRA-VAN Data Lab. + mykeibadb
- **LLM**: Claude API（Anthropic）
- **開発環境**: WSL2 + VS Code + Claude Code

## ディレクトリ構成

```
keiba-yosou/
├── src/
│   ├── db/              # DB接続、クエリ関連
│   │   ├── connection.py    # DB接続管理
│   │   ├── queries.py       # SQLクエリ定義
│   │   └── models.py        # データモデル
│   ├── features/        # 特徴量生成
│   │   ├── speed.py         # スピード指数
│   │   ├── jockey.py        # 騎手成績
│   │   └── course.py        # コース適性
│   └── predict/         # 予想ロジック
│       ├── llm.py           # LLM呼び出し
│       └── formatter.py     # 出力整形
├── prompts/             # LLMプロンプトテンプレート
│   ├── race_prediction.md
│   └── pace_analysis.md
├── scripts/             # ユーティリティ
│   ├── sync_to_neon.py      # Neon同期
│   └── fetch_race.py        # レースデータ取得
├── tests/               # テスト
├── docs/                # ドキュメント
├── .env.example         # 環境変数テンプレート
├── requirements.txt     # Python依存関係
└── README.md
```

## 開発フェーズ

### Phase 1: データ基盤構築（現在）

- [x] JRA-VAN契約
- [x] mykeibadbセットアップ
- [x] ローカルPostgreSQLセットアップ
- [ ] データ取り込み完了（数日かかる）
- [ ] テーブル構造確認
- [ ] 基本クエリ作成

### Phase 2: データ抽出・整形

- [ ] 出馬表データ取得
- [ ] 過去走データ取得（直近5走）
- [ ] 騎手・調教師成績取得
- [ ] コース別成績取得

### Phase 3: 特徴量生成

- [ ] スピード指数計算
- [ ] 上がり3F順位
- [ ] 馬場差補正
- [ ] クラス補正

### Phase 4: LLM予想機能

- [ ] プロンプト設計
- [ ] Claude API連携
- [ ] 予想生成・出力

### Phase 5: 運用・改善

- [ ] Neonへの同期
- [ ] 回収率検証
- [ ] プロンプト改善

## DB接続情報

### ローカルPostgreSQL

```
Host: localhost
Port: 5432
Database: keiba_db
User: postgres
Password: （設定したパスワード）
```

### Neon（将来）

```
Host: xxx.neon.tech
Database: keiba_db
接続文字列: postgres://user:pass@xxx.neon.tech/keiba_db
```

## 環境変数（.env）

```env
# ローカルDB
LOCAL_DB_HOST=localhost
LOCAL_DB_PORT=5432
LOCAL_DB_NAME=keiba_db
LOCAL_DB_USER=postgres
LOCAL_DB_PASSWORD=your_password

# Neon（将来）
NEON_DATABASE_URL=postgres://user:pass@xxx.neon.tech/keiba_db

# Claude API
ANTHROPIC_API_KEY=your_api_key
```

## 参考リンク

- [JRA-VAN Data Lab.](https://jra-van.jp/dlb/)
- [JRA-VAN SDK](https://jra-van.jp/dlb/sdv/sdk.html)
- [mykeibadb](https://keough.watson.jp/wp/mykeibadb/)
- [Neon](https://neon.tech/)
- [Anthropic API](https://docs.anthropic.com/)
