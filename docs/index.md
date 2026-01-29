# keiba-yosou Documentation

競馬予想システム - JRA-VAN公式データを使用した機械学習ベースの予想システム

## Overview

keiba-yosoはXGBoost、LightGBM、CatBoostのアンサンブルモデルを使用した競馬予想システムです。

### 主な機能

- **機械学習予想**: アンサンブルモデルによる確率ベースの順位予想
- **期待値推奨**: EV >= 1.5の馬を自動推奨
- **Discord Bot**: レース30分前に自動通知
- **REST API**: FastAPIベースのWeb API
- **ダッシュボード**: Streamlitによるパフォーマンス可視化

### システム構成

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Discord Bot   │────│   FastAPI API   │────│   PostgreSQL    │
└─────────────────┘    └─────────────────┘    │   (mykeibadb)   │
                              │               └─────────────────┘
                              │
                       ┌──────┴──────┐
                       │ ML Ensemble │
                       │ XGB+LGB+CB  │
                       └─────────────┘
```

## Quick Start

```bash
# リポジトリをクローン
git clone https://github.com/raveuptonight/keiba-yosou.git
cd keiba-yosou

# 初期セットアップ
make setup

# サービス起動
make up

# API確認
curl http://localhost:8000/health
```

## 技術スタック

| カテゴリ | 技術 |
|---------|------|
| 言語 | Python 3.11+ |
| API | FastAPI |
| ML | XGBoost, LightGBM, CatBoost |
| DB | PostgreSQL |
| Bot | discord.py |
| UI | Streamlit |
| Container | Docker Compose |

## ドキュメント構成

- [Getting Started](getting-started.md) - 初回セットアップ
- [API Reference](usage/api-reference.md) - REST API仕様
- [Architecture](architecture/system-design.md) - システム設計

## ライセンス

MIT License

!!! warning "JRA-VANデータに関する注意"
    JRA-VANのデータは再配布が禁止されています。本システムを使用するにはJRA-VANとの契約が必要です。
