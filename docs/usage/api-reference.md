# API Reference

keiba-yosou REST APIの仕様書です。

## Base URL

```
http://localhost:8000/api/v1
```

後方互換性のため `/api` プレフィックスも利用可能です。

## 認証

現在、認証は不要です。（将来的にAPI Key認証を導入予定）

## エンドポイント一覧

### Health Check

#### GET /health

システムの稼働状態を確認します。

**Response**

```json
{
  "status": "healthy",
  "timestamp": "2025-01-30T15:00:00+09:00"
}
```

---

### Predictions

#### POST /api/v1/predictions/generate

レースの予想を生成します。

**Request Body**

```json
{
  "race_id": "2025012506010911",
  "is_final": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| race_id | string | Yes | 16桁のレースID |
| is_final | boolean | No | 最終予想フラグ（馬体重発表後） |

**Response** (200 OK)

```json
{
  "prediction_id": "abc123",
  "race_id": "2025012506010911",
  "race_name": "アメリカジョッキークラブカップ",
  "race_number": 11,
  "track_name": "中山",
  "prediction_result": {
    "ranked_horses": [
      {
        "rank": 1,
        "horse_number": 5,
        "horse_name": "サンプルホース",
        "win_probability": 0.25,
        "place_probability": 0.55
      }
    ],
    "prediction_confidence": 0.72,
    "axis_horse": {
      "horse_number": 5,
      "horse_name": "サンプルホース",
      "place_probability": 0.55
    }
  },
  "ev_recommendations": {
    "win_recommendations": [],
    "place_recommendations": [],
    "odds_source": "realtime"
  },
  "is_final": false,
  "created_at": "2025-01-30T15:00:00+09:00"
}
```

**Error Responses**

| Status | Description |
|--------|-------------|
| 404 | レースが見つからない |
| 422 | バリデーションエラー |
| 500 | 予想生成エラー |

---

### Races

#### GET /api/v1/races

レース一覧を取得します。

**Query Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| date | string | today | 日付（YYYY-MM-DD） |
| track | string | - | 競馬場コード |
| limit | integer | 10 | 最大件数 |

**Response**

```json
{
  "races": [
    {
      "race_id": "2025012506010911",
      "race_name": "アメリカジョッキークラブカップ",
      "race_number": 11,
      "track_code": "06",
      "track_name": "中山",
      "start_time": "15:40",
      "distance": 2200,
      "surface": "turf"
    }
  ],
  "total": 1
}
```

---

### Odds

#### GET /api/v1/odds/{race_id}

レースのオッズを取得します。

**Response**

```json
{
  "race_id": "2025012506010911",
  "tansho": {
    "1": 3.5,
    "2": 5.0,
    "3": 8.2
  },
  "fukusho": {
    "1": 1.5,
    "2": 2.0,
    "3": 2.8
  },
  "odds_time": "2025-01-30 15:00",
  "source": "realtime"
}
```

---

## エラーレスポンス形式

すべてのエラーは以下の形式で返されます:

```json
{
  "detail": "エラーメッセージ",
  "error_code": "ERROR_CODE"
}
```

## OpenAPI仕様

完全なAPIドキュメントは Swagger UI で確認できます:

```
http://localhost:8000/docs
```

ReDoc形式:

```
http://localhost:8000/redoc
```
