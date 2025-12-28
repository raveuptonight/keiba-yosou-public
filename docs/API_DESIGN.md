# API設計書

## 概要

FastAPIベースのRESTful APIサーバー。Discord BotとLLM予想エンジンの橋渡しを行い、JRA-VANデータベースから必要なデータを集約して予想結果を返します。

---

## アーキテクチャ

```
┌─────────────────┐
│  Discord Bot    │
│  (scheduler.py) │
└────────┬────────┘
         │ HTTP Request
         ▼
┌─────────────────────────────────────────┐
│         FastAPI Server                   │
│  ┌─────────────────────────────────┐   │
│  │  Endpoints (src/api/routes/)    │   │
│  ├─────────────────────────────────┤   │
│  │  Business Logic (src/services/) │   │
│  ├─────────────────────────────────┤   │
│  │  DB Queries (src/db/queries/)   │   │
│  └─────────────────────────────────┘   │
└────────┬────────────────────────────────┘
         │ SQL Queries
         ▼
┌─────────────────────────────────────────┐
│       PostgreSQL (keiba_db)             │
│  27 Tables (RA, SE, UM, SK, HC, etc.)   │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│      Claude API (LLM Prediction)        │
└─────────────────────────────────────────┘
```

---

## エンドポイント一覧

### 1. レース情報取得

#### GET /api/v1/races/today
**説明**: 本日開催のレース一覧を取得

**クエリパラメータ**:
| パラメータ | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|-----|-----------|------|
| `grade` | string | ❌ | - | グレードフィルタ（A=G1, B=G2, C=G3） |
| `venue` | string | ❌ | - | 競馬場コード（01=札幌, 02=函館, etc.） |

**レスポンス例**:
```json
{
  "date": "2024-12-28",
  "races": [
    {
      "race_id": "202412280506",
      "race_name": "中山金杯",
      "race_number": "11R",
      "race_time": "15:25",
      "venue": "中山",
      "venue_code": "05",
      "grade": "G3",
      "distance": 2000,
      "track_code": "10",
      "entry_count": 16
    }
  ],
  "total": 12
}
```

**使用テーブル**: RA

---

#### GET /api/v1/races/{race_id}
**説明**: 特定レースの詳細情報を取得

**パスパラメータ**:
- `race_id`: レースID（16桁）

**レスポンス例**:
```json
{
  "race_id": "202412280506",
  "race_name": "中山金杯",
  "race_number": "11R",
  "race_time": "15:25",
  "venue": "中山",
  "grade": "G3",
  "distance": 2000,
  "track_code": "10",
  "track_condition": "良",
  "weather": "晴",
  "prize_money": {
    "first": 40000000,
    "second": 16000000,
    "third": 10000000,
    "fourth": 6000000,
    "fifth": 4000000
  },
  "entries": [
    {
      "horse_number": 1,
      "kettonum": "2019105432",
      "horse_name": "ディープボンド",
      "jockey_code": "01234",
      "jockey_name": "横山武史",
      "trainer_code": "05678",
      "trainer_name": "大竹正博",
      "weight": 56.0,
      "horse_weight": null,
      "odds": 3.5
    }
  ]
}
```

**使用テーブル**: RA, SE, UM, O1

---

### 2. 予想生成

#### POST /api/v1/predictions/generate
**説明**: LLMによる予想を生成

**リクエストボディ**:
```json
{
  "race_id": "202412280506",
  "is_final": false,
  "total_investment": 10000
}
```

**フィールド**:
| フィールド | 型 | 必須 | 説明 |
|-----------|-----|-----|------|
| `race_id` | string | ✅ | レースID（16桁） |
| `is_final` | boolean | ❌ | 最終予想フラグ（デフォルト: false） |
| `total_investment` | integer | ❌ | 総投資額（デフォルト: 10000） |

**レスポンス例**:
```json
{
  "prediction_id": "abc123def456",
  "race_id": "202412280506",
  "race_name": "中山金杯",
  "race_date": "2024-12-28",
  "venue": "中山",
  "race_number": "11R",
  "race_time": "15:25",
  "prediction_result": {
    "win_prediction": {
      "first": {
        "horse_number": 3,
        "horse_name": "ディープボンド",
        "expected_odds": 3.5,
        "confidence": 0.85
      },
      "second": {
        "horse_number": 7,
        "horse_name": "エフフォーリア",
        "expected_odds": 5.2,
        "confidence": 0.72
      },
      "third": {
        "horse_number": 12,
        "horse_name": "タイトルホルダー",
        "expected_odds": 8.1,
        "confidence": 0.65
      },
      "fourth": {
        "horse_number": 5,
        "horse_name": "パンサラッサ",
        "expected_odds": 12.0,
        "confidence": 0.58
      },
      "fifth": {
        "horse_number": 9,
        "horse_name": "イクイノックス",
        "expected_odds": 15.0,
        "confidence": 0.52
      },
      "excluded": [
        {
          "horse_number": 1,
          "horse_name": "ダメウマ",
          "reason": "調教時計不良"
        }
      ]
    },
    "betting_strategy": {
      "recommended_tickets": [
        {
          "ticket_type": "3連複",
          "numbers": [3, 7, 12],
          "amount": 1000,
          "expected_payout": 8500
        }
      ]
    }
  },
  "total_investment": 10000,
  "expected_return": 15000,
  "expected_roi": 1.5,
  "predicted_at": "2024-12-28T09:00:00+09:00",
  "is_final": false
}
```

**使用テーブル**: RA, SE, UM, SK, HN, HC, WC, CK, O1-O6

**処理フロー**:
```
1. レース情報取得（RA）
2. 出走馬情報取得（SE, UM）
3. 各馬の過去成績取得（SE: 過去10走）
4. 血統情報取得（SK, HN）
5. 調教情報取得（HC, WC: 最新1ヶ月）
6. 着度数統計取得（CK）
7. オッズ情報取得（O1-O6）
8. データをプロンプトに整形
9. Claude APIでLLM予想実行
10. 予想結果をDBに保存
11. レスポンス返却
```

**レート制限**: 1分あたり5リクエスト（Claude API制限に準拠）

---

#### GET /api/v1/predictions/{prediction_id}
**説明**: 保存済み予想結果を取得

**パスパラメータ**:
- `prediction_id`: 予想ID

**レスポンス**: POST /api/v1/predictions/generateと同じ

**使用テーブル**: predictions（予想結果保存用テーブル）

---

#### GET /api/v1/predictions/race/{race_id}
**説明**: 特定レースの予想履歴を取得

**パスパラメータ**:
- `race_id`: レースID

**クエリパラメータ**:
| パラメータ | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|-----|-----------|------|
| `is_final` | boolean | ❌ | - | 最終予想のみ取得 |

**レスポンス例**:
```json
{
  "race_id": "202412280506",
  "predictions": [
    {
      "prediction_id": "abc123",
      "predicted_at": "2024-12-28T09:00:00+09:00",
      "is_final": false,
      "expected_roi": 1.5
    },
    {
      "prediction_id": "def456",
      "predicted_at": "2024-12-28T14:25:00+09:00",
      "is_final": true,
      "expected_roi": 1.7
    }
  ]
}
```

---

### 3. 馬情報取得

#### GET /api/v1/horses/{kettonum}
**説明**: 馬の詳細情報と過去成績を取得

**パスパラメータ**:
- `kettonum`: 血統登録番号（10桁）

**クエリパラメータ**:
| パラメータ | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|-----|-----------|------|
| `history_limit` | integer | ❌ | 10 | 過去成績取得件数 |

**レスポンス例**:
```json
{
  "kettonum": "2019105432",
  "horse_name": "ディープボンド",
  "birth_date": "2019-05-10",
  "sex": "牡",
  "coat_color": "鹿毛",
  "sire": "キズナ",
  "dam": "ゼフィランサス",
  "breeder": "ノーザンファーム",
  "owner": "（株）シルクレーシング",
  "trainer": {
    "code": "05678",
    "name": "大竹正博",
    "affiliation": "美浦"
  },
  "total_races": 18,
  "wins": 6,
  "win_rate": 0.333,
  "prize_money": 450000000,
  "running_style": "先行",
  "pedigree": {
    "sire": "キズナ",
    "dam": "ゼフィランサス",
    "sire_sire": "ディープインパクト",
    "sire_dam": "キャットクイル",
    "dam_sire": "ゼンノロブロイ",
    "dam_dam": "フサイチエアデール"
  },
  "recent_races": [
    {
      "race_id": "202411300610",
      "race_name": "ジャパンカップ",
      "race_date": "2024-11-30",
      "venue": "東京",
      "distance": 2400,
      "track_condition": "良",
      "finish_position": 2,
      "time": "2:22.3",
      "jockey": "横山武史",
      "weight": 56.0,
      "horse_weight": 484,
      "odds": 5.2,
      "prize_money": 80000000
    }
  ]
}
```

**使用テーブル**: UM, SE, SK, CH

---

### 4. 統計・分析

#### GET /api/v1/stats/jockey/{jockey_code}
**説明**: 騎手の成績統計

**パスパラメータ**:
- `jockey_code`: 騎手コード

**クエリパラメータ**:
| パラメータ | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|-----|-----------|------|
| `year` | integer | ❌ | 現在年 | 集計年 |
| `venue` | string | ❌ | - | 競馬場コード |

**レスポンス例**:
```json
{
  "jockey_code": "01234",
  "jockey_name": "横山武史",
  "year": 2024,
  "stats": {
    "total_races": 850,
    "wins": 120,
    "places": 95,
    "shows": 85,
    "win_rate": 0.141,
    "place_rate": 0.353,
    "prize_money": 2500000000
  },
  "by_venue": [
    {
      "venue": "東京",
      "races": 250,
      "wins": 45,
      "win_rate": 0.180
    }
  ],
  "by_distance": [
    {
      "range": "1200-1600",
      "races": 300,
      "wins": 50,
      "win_rate": 0.167
    }
  ]
}
```

**使用テーブル**: KS, SE

---

#### GET /api/v1/stats/trainer/{trainer_code}
**説明**: 調教師の成績統計

**レスポンス形式**: 騎手統計と同様

**使用テーブル**: CH, SE

---

### 5. オッズ情報

#### GET /api/v1/odds/{race_id}
**説明**: レースのオッズ情報取得

**パスパラメータ**:
- `race_id`: レースID

**クエリパラメータ**:
| パラメータ | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|-----|-----------|------|
| `ticket_type` | string | ❌ | "win" | 券種（win, place, quinella, exacta, trio, trifecta） |

**レスポンス例（単勝）**:
```json
{
  "race_id": "202412280506",
  "ticket_type": "win",
  "updated_at": "2024-12-28T15:20:00+09:00",
  "odds": [
    {
      "horse_number": 1,
      "odds": 8.5
    },
    {
      "horse_number": 2,
      "odds": 15.2
    },
    {
      "horse_number": 3,
      "odds": 3.5
    }
  ]
}
```

**レスポンス例（馬連）**:
```json
{
  "race_id": "202412280506",
  "ticket_type": "quinella",
  "updated_at": "2024-12-28T15:20:00+09:00",
  "odds": [
    {
      "numbers": [3, 7],
      "odds": 18.5
    },
    {
      "numbers": [3, 12],
      "odds": 45.2
    }
  ]
}
```

**使用テーブル**: O1（単勝・複勝）, O2（枠連）, O3（馬連）, O4（ワイド）, O5（馬単）, O6（3連複・3連単）

---

### 6. ヘルスチェック

#### GET /api/health
**説明**: APIサーバーの稼働状態確認

**レスポンス例**:
```json
{
  "status": "ok",
  "timestamp": "2024-12-28T10:00:00+09:00",
  "database": "connected",
  "claude_api": "available"
}
```

---

## データモデル（Pydantic）

### src/api/schemas/race.py

```python
from pydantic import BaseModel, Field
from datetime import date, time
from typing import Optional, List

class RaceBase(BaseModel):
    race_id: str = Field(..., min_length=16, max_length=16)
    race_name: str
    race_number: str
    race_time: str
    venue: str
    venue_code: str
    grade: Optional[str] = None
    distance: int
    track_code: str

class RaceEntry(BaseModel):
    horse_number: int = Field(..., ge=1, le=18)
    kettonum: str = Field(..., min_length=10, max_length=10)
    horse_name: str
    jockey_code: str
    jockey_name: str
    trainer_code: str
    trainer_name: str
    weight: float
    horse_weight: Optional[int] = None
    odds: Optional[float] = None

class RaceDetail(RaceBase):
    track_condition: Optional[str] = None
    weather: Optional[str] = None
    prize_money: dict
    entries: List[RaceEntry]

class RaceListResponse(BaseModel):
    date: str
    races: List[RaceBase]
    total: int
```

### src/api/schemas/prediction.py

```python
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class HorseRanking(BaseModel):
    horse_number: int = Field(..., ge=1, le=18)
    horse_name: str
    expected_odds: Optional[float] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)

class ExcludedHorse(BaseModel):
    horse_number: int = Field(..., ge=1, le=18)
    horse_name: str
    reason: Optional[str] = None

class WinPrediction(BaseModel):
    first: HorseRanking
    second: HorseRanking
    third: HorseRanking
    fourth: Optional[HorseRanking] = None
    fifth: Optional[HorseRanking] = None
    excluded: Optional[List[ExcludedHorse]] = None

class RecommendedTicket(BaseModel):
    ticket_type: str
    numbers: List[int]
    amount: int = Field(..., gt=0)
    expected_payout: Optional[int] = None

class BettingStrategy(BaseModel):
    recommended_tickets: List[RecommendedTicket]

class PredictionResult(BaseModel):
    win_prediction: WinPrediction
    betting_strategy: BettingStrategy

class PredictionRequest(BaseModel):
    race_id: str = Field(..., min_length=16, max_length=16)
    is_final: bool = False
    total_investment: int = Field(default=10000, gt=0)

class PredictionResponse(BaseModel):
    prediction_id: str
    race_id: str
    race_name: str
    race_date: str
    venue: str
    race_number: str
    race_time: str
    prediction_result: PredictionResult
    total_investment: int
    expected_return: int
    expected_roi: float
    predicted_at: datetime
    is_final: bool
```

### src/api/schemas/horse.py

```python
from pydantic import BaseModel
from typing import Optional, List
from datetime import date

class Trainer(BaseModel):
    code: str
    name: str
    affiliation: str

class Pedigree(BaseModel):
    sire: str
    dam: str
    sire_sire: str
    sire_dam: str
    dam_sire: str
    dam_dam: str

class RecentRace(BaseModel):
    race_id: str
    race_name: str
    race_date: date
    venue: str
    distance: int
    track_condition: str
    finish_position: int
    time: str
    jockey: str
    weight: float
    horse_weight: Optional[int] = None
    odds: Optional[float] = None
    prize_money: int

class HorseDetail(BaseModel):
    kettonum: str
    horse_name: str
    birth_date: date
    sex: str
    coat_color: str
    sire: str
    dam: str
    breeder: str
    owner: str
    trainer: Trainer
    total_races: int
    wins: int
    win_rate: float
    prize_money: int
    running_style: Optional[str] = None
    pedigree: Pedigree
    recent_races: List[RecentRace]
```

---

## エラーハンドリング

### エラーレスポンス形式

```json
{
  "error": {
    "code": "RACE_NOT_FOUND",
    "message": "指定されたレースが見つかりません",
    "details": {
      "race_id": "202412280506"
    }
  }
}
```

### エラーコード一覧

| HTTPステータス | エラーコード | 説明 |
|--------------|-------------|------|
| 400 | INVALID_REQUEST | リクエストパラメータが不正 |
| 404 | RACE_NOT_FOUND | レースが見つからない |
| 404 | HORSE_NOT_FOUND | 馬が見つからない |
| 404 | PREDICTION_NOT_FOUND | 予想結果が見つからない |
| 429 | RATE_LIMIT_EXCEEDED | レート制限超過 |
| 500 | DATABASE_ERROR | データベースエラー |
| 503 | CLAUDE_API_UNAVAILABLE | Claude API利用不可 |
| 504 | PREDICTION_TIMEOUT | 予想生成タイムアウト |

### src/api/exceptions.py

```python
from fastapi import HTTPException, status

class RaceNotFoundException(HTTPException):
    def __init__(self, race_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RACE_NOT_FOUND",
                "message": "指定されたレースが見つかりません",
                "details": {"race_id": race_id}
            }
        )

class RateLimitExceededException(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "リクエスト数が制限を超えています。しばらく待ってから再試行してください。",
                "details": {"retry_after": 60}
            }
        )

class ClaudeAPIUnavailableException(HTTPException):
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "CLAUDE_API_UNAVAILABLE",
                "message": f"Claude APIが利用できません: {message}",
                "details": {}
            }
        )
```

---

## レート制限

### Claude API呼び出し制限

```python
# src/services/rate_limiter.py
from datetime import datetime, timedelta
from collections import deque

class RateLimiter:
    """シンプルなレート制限実装（スライディングウィンドウ）"""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: deque = deque()

    def is_allowed(self) -> bool:
        """リクエストが許可されるかチェック"""
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.window_seconds)

        # 古いリクエストを削除
        while self.requests and self.requests[0] < cutoff:
            self.requests.popleft()

        # 制限チェック
        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True
        return False

# 使用例
claude_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)
```

### ミドルウェアでの適用

```python
# src/api/middleware/rate_limit.py
from fastapi import Request
from src.services.rate_limiter import claude_rate_limiter
from src.api.exceptions import RateLimitExceededException

async def rate_limit_middleware(request: Request, call_next):
    """予想生成エンドポイントのレート制限"""
    if request.url.path == "/api/v1/predictions/generate":
        if not claude_rate_limiter.is_allowed():
            raise RateLimitExceededException()

    response = await call_next(request)
    return response
```

---

## 認証・認可

### 将来実装予定（Phase 5以降）

```python
# src/api/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """JWTトークン検証"""
    token = credentials.credentials
    # TODO: トークン検証ロジック
    return token

# 使用例
@router.post("/api/v1/predictions/generate")
async def generate_prediction(
    request: PredictionRequest,
    token: str = Depends(verify_token)
):
    # 認証済みユーザーのみアクセス可
    pass
```

**Phase 4では認証なし**（ローカル環境のみ）

---

## データ集約クエリ

### 予想生成用データ取得

```python
# src/db/queries/prediction_data.py
from typing import Dict, Any, List
from src.db.connection import get_connection

async def get_race_prediction_data(race_id: str) -> Dict[str, Any]:
    """
    予想生成に必要な全データを集約

    Returns:
        {
            "race": {...},           # レース情報（RA）
            "horses": [...],         # 出走馬情報（SE, UM）
            "histories": {...},      # 各馬の過去10走（SE）
            "pedigrees": {...},      # 血統情報（SK, HN）
            "training": {...},       # 調教情報（HC, WC）
            "statistics": {...},     # 着度数統計（CK）
            "odds": {...}            # オッズ情報（O1-O6）
        }
    """
    conn = await get_connection()

    # 1. レース基本情報
    race = await get_race_info(conn, race_id)

    # 2. 出走馬一覧
    horses = await get_race_entries(conn, race_id)

    # 3. 各馬の詳細データを並列取得
    kettonums = [h["kettonum"] for h in horses]

    histories = await get_horses_recent_races(conn, kettonums, limit=10)
    pedigrees = await get_horses_pedigree(conn, kettonums)
    training = await get_horses_training(conn, kettonums)
    statistics = await get_horses_statistics(conn, race_id, kettonums)

    # 4. オッズ情報
    odds = await get_race_odds(conn, race_id)

    await conn.close()

    return {
        "race": race,
        "horses": horses,
        "histories": histories,
        "pedigrees": pedigrees,
        "training": training,
        "statistics": statistics,
        "odds": odds
    }
```

### レース情報取得

```sql
-- get_race_info(race_id)
SELECT
    race_id,
    race_name,
    grade_cd,
    jyocd,
    track_cd,
    kyori,
    honsyokin_1,
    honsyokin_2,
    honsyokin_3,
    honsyokin_4,
    honsyokin_5,
    baba_jotai,
    tenkocode
FROM race
WHERE race_id = $1
  AND data_kubun = '7';  -- 確定データのみ
```

### 出走馬一覧取得

```sql
-- get_race_entries(race_id)
SELECT
    se.umaban,
    se.kettonum,
    um.bamei,
    se.kisyucode,
    ks.kisyu_name,
    se.chokyosicode,
    ch.chokyosi_name,
    se.futan,
    se.bataiju,
    o1.tansyo_odds
FROM uma_race se
INNER JOIN uma um ON se.kettonum = um.kettonum
LEFT JOIN kisyu ks ON se.kisyucode = ks.kisyucode
LEFT JOIN chokyosi ch ON se.chokyosicode = ch.chokyosicode
LEFT JOIN odds_tanfuku o1 ON se.race_id = o1.race_id AND se.umaban = o1.umaban
WHERE se.race_id = $1
  AND se.data_kubun = '7'
ORDER BY se.umaban;
```

### 過去成績取得

```sql
-- get_horses_recent_races(kettonums, limit=10)
WITH ranked_races AS (
    SELECT
        se.kettonum,
        se.race_id,
        ra.race_name,
        ra.kaisai_year,
        ra.kaisai_monthday,
        ra.jyocd,
        ra.kyori,
        ra.baba_jotai,
        se.kakutei_chakujun,
        se.time,
        se.kisyucode,
        se.futan,
        se.bataiju,
        se.tansyo_odds,
        se.syogkin,
        ROW_NUMBER() OVER (
            PARTITION BY se.kettonum
            ORDER BY ra.kaisai_year DESC, ra.kaisai_monthday DESC
        ) AS rn
    FROM uma_race se
    INNER JOIN race ra ON se.race_id = ra.race_id
    WHERE se.kettonum = ANY($1)
      AND se.data_kubun = '7'
      AND ra.kaisai_year >= EXTRACT(YEAR FROM CURRENT_DATE) - 10  -- 10年以内
)
SELECT *
FROM ranked_races
WHERE rn <= $2  -- limit
ORDER BY kettonum, rn;
```

### 血統情報取得

```sql
-- get_horses_pedigree(kettonums)
SELECT
    sk.kettonum,
    sk.sandai_ketto[1] AS chichi,        -- 父
    sk.sandai_ketto[2] AS haha,          -- 母
    sk.sandai_ketto[3] AS chichi_chichi, -- 父父
    sk.sandai_ketto[4] AS chichi_haha,   -- 父母
    sk.sandai_ketto[5] AS haha_chichi,   -- 母父（重要）
    sk.sandai_ketto[6] AS haha_haha,     -- 母母
    hn_f.hansyokuba_name AS chichi_name,
    hn_m.hansyokuba_name AS haha_name,
    hn_ff.hansyokuba_name AS chichi_chichi_name,
    hn_mf.hansyokuba_name AS haha_chichi_name
FROM sanku sk
LEFT JOIN hansyoku_meigara hn_f ON sk.sandai_ketto[1] = hn_f.hansyoku_num
LEFT JOIN hansyoku_meigara hn_m ON sk.sandai_ketto[2] = hn_m.hansyoku_num
LEFT JOIN hansyoku_meigara hn_ff ON sk.sandai_ketto[3] = hn_ff.hansyoku_num
LEFT JOIN hansyoku_meigara hn_mf ON sk.sandai_ketto[5] = hn_mf.hansyoku_num
WHERE sk.kettonum = ANY($1);
```

### 調教情報取得

```sql
-- get_horses_training(kettonums)
WITH latest_training AS (
    SELECT
        kettonum,
        chokyo_date,
        han_name,
        baba_jotai,
        time_4f,
        time_3f,
        han_type,
        ROW_NUMBER() OVER (
            PARTITION BY kettonum
            ORDER BY chokyo_date DESC
        ) AS rn
    FROM hanro_chokyo
    WHERE kettonum = ANY($1)
      AND chokyo_date >= CURRENT_DATE - INTERVAL '1 month'
      AND time_4f > 0  -- 測定不良除外
)
SELECT *
FROM latest_training
WHERE rn <= 5  -- 最新5本
ORDER BY kettonum, rn;
```

### 着度数統計取得

```sql
-- get_horses_statistics(race_id, kettonums)
SELECT
    ck.kettonum,
    ck.kyori_chakudo,     -- 距離別着度数（6870バイトの巨大配列）
    ck.baba_chakudo,      -- 馬場別着度数
    ck.jyocd_chakudo,     -- 競馬場別着度数
    ck.kisyu_chakudo      -- 騎手別着度数
FROM shutuba_chakudo ck
WHERE ck.race_id = $1
  AND ck.kettonum = ANY($2);
```

---

## ファイル構成

```
src/
├── api/
│   ├── main.py                    # FastAPIアプリエントリーポイント
│   ├── routes/
│   │   ├── races.py               # レース関連エンドポイント
│   │   ├── predictions.py         # 予想生成エンドポイント
│   │   ├── horses.py              # 馬情報エンドポイント
│   │   ├── stats.py               # 統計エンドポイント
│   │   └── odds.py                # オッズエンドポイント
│   ├── schemas/
│   │   ├── race.py                # レース関連スキーマ
│   │   ├── prediction.py          # 予想関連スキーマ
│   │   ├── horse.py               # 馬情報スキーマ
│   │   └── common.py              # 共通スキーマ
│   ├── middleware/
│   │   ├── rate_limit.py          # レート制限ミドルウェア
│   │   └── error_handler.py       # エラーハンドリング
│   └── exceptions.py              # カスタム例外
├── services/
│   ├── prediction_service.py      # 予想生成ビジネスロジック
│   ├── rate_limiter.py            # レート制限実装
│   └── claude_client.py           # Claude API クライアント
├── db/
│   ├── connection.py              # DB接続管理
│   └── queries/
│       ├── race_queries.py        # レース取得クエリ
│       ├── horse_queries.py       # 馬情報取得クエリ
│       ├── prediction_data.py     # 予想用データ集約
│       └── stats_queries.py       # 統計クエリ
└── models/
    └── prediction_db.py           # 予想結果保存用モデル
```

---

## 起動方法

### 開発環境

```bash
# FastAPI開発サーバー起動
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# APIドキュメント確認
# http://localhost:8000/docs (Swagger UI)
# http://localhost:8000/redoc (ReDoc)
```

### 本番環境

```bash
# Gunicorn + Uvicorn Worker
gunicorn src.api.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 300
```

---

## テスト

### src/tests/api/test_predictions.py

```python
import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_generate_prediction_success():
    """予想生成APIの正常系テスト"""
    response = client.post(
        "/api/v1/predictions/generate",
        json={
            "race_id": "202412280506",
            "is_final": False,
            "total_investment": 10000
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["race_id"] == "202412280506"
    assert "prediction_result" in data
    assert "win_prediction" in data["prediction_result"]

def test_generate_prediction_invalid_race():
    """存在しないレースIDでの予想生成"""
    response = client.post(
        "/api/v1/predictions/generate",
        json={
            "race_id": "999999999999",
            "is_final": False
        }
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RACE_NOT_FOUND"

def test_rate_limit_exceeded():
    """レート制限テスト"""
    # 5回連続でリクエスト（制限: 5req/min）
    for i in range(5):
        response = client.post(
            "/api/v1/predictions/generate",
            json={"race_id": "202412280506"}
        )
        assert response.status_code == 200

    # 6回目はエラー
    response = client.post(
        "/api/v1/predictions/generate",
        json={"race_id": "202412280506"}
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
```

---

## 今後の拡張予定

### Phase 5以降

- [ ] **認証・認可**: JWT認証実装
- [ ] **リアルタイム通知**: WebSocket対応（オッズ変動通知）
- [ ] **キャッシング**: Redis導入（オッズ、レース一覧）
- [ ] **バッチAPI**: 複数レース一括予想
- [ ] **結果検証API**: 予想結果と実際の結果を比較
- [ ] **統計ダッシュボード**: 予想精度の可視化
- [ ] **A/Bテスト**: 複数プロンプトの比較
- [ ] **外部連携**: PAT（即PAT）API統合（実際の馬券購入）

---

## パフォーマンス目標

| エンドポイント | 目標レスポンスタイム | 備考 |
|--------------|------------------|------|
| GET /races/today | < 100ms | インデックス活用 |
| GET /races/{race_id} | < 150ms | JOIN 3テーブル |
| POST /predictions/generate | < 30秒 | LLM呼び出し含む |
| GET /horses/{kettonum} | < 200ms | 過去10走取得 |
| GET /odds/{race_id} | < 50ms | 単純SELECT |

---

## ログ設計

### ログレベル

- **DEBUG**: SQL クエリ、詳細なデータフロー
- **INFO**: API リクエスト、予想生成開始/完了
- **WARNING**: レート制限警告、データ欠損
- **ERROR**: DB エラー、Claude API エラー
- **CRITICAL**: サーバークラッシュ

### ログフォーマット

```json
{
  "timestamp": "2024-12-28T15:30:00+09:00",
  "level": "INFO",
  "service": "prediction-api",
  "endpoint": "/api/v1/predictions/generate",
  "race_id": "202412280506",
  "execution_time_ms": 25340,
  "message": "Prediction generated successfully"
}
```

---

## まとめ

このAPI設計により、以下が実現されます：

1. ✅ Discord Botからシンプルに呼び出せるRESTful API
2. ✅ 27テーブルのデータを効率的に集約
3. ✅ Claude APIのレート制限を考慮した予想生成
4. ✅ エラーハンドリングとログ設計
5. ✅ Pydanticによる型安全なリクエスト/レスポンス
6. ✅ スケーラビリティを考慮した設計（認証、キャッシング等は将来対応）

**次のステップ**: データダウンロード完了後、実際のテーブル名に合わせてクエリを調整し、API実装を開始します。
