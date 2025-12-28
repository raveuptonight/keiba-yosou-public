# JRA-VAN Data Lab. データ仕様リファレンス

## 概要

JRA-VAN Data Lab.は、JRA公式の競馬データを提供するサービス。1986年からの全レースデータが取得可能。

## データ取得の仕組み

```
JRA-VAN サーバー
    ↓ JV-Link（ActiveX COM）
ローカルWindows
    ↓ mykeibadb
PostgreSQL / MySQL
```

- **JV-Link**: JRA-VANのデータ取得インターフェース（Windows専用）
- **mykeibadb**: JV-DataをPostgreSQL/MySQLに格納するツール

## 主要データ種別（JV-Data）

### 蓄積系データ（セットアップで取得）

| 記号 | テーブル名 | 説明 | 予想での用途 |
|------|-----------|------|-------------|
| **RA** | race / race_shosai | レース詳細 | 距離、馬場、グレード、天候、馬場状態 |
| **SE** | uma_race / umagoto_race_joho | 馬毎レース情報 | 着順、タイム、上がり、通過順位、馬体重、着差 |
| **HR** | haraimodoshi | 払戻 | 配当金、的中馬番 |
| **UM** | uma | 競走馬マスタ | 馬名、生年月日、性別、毛色、血統 |
| **KS** | kishu | 騎手マスタ | 騎手名、所属、成績 |
| **CH** | chokyoshi | 調教師マスタ | 調教師名、所属、成績 |
| **BR** | seisansha | 生産者マスタ | 生産者情報 |
| **BN** | banushi | 馬主マスタ | 馬主情報 |
| **HN** | hansyokuba | 繁殖馬マスタ | 血統情報 |
| **SK** | sanku | 産駒マスタ | 産駒情報 |
| **RC** | record | レコードマスタ | コースレコード |
| **TK** | tokubetsu_toroku | 特別登録馬 | 週末の出走予定馬 |

### 調教系データ

| 記号 | 説明 | 内容 |
|------|------|------|
| **HC** | 坂路調教 | 美浦・栗東トレセンでの坂路（上り坂）調教データ |
| **WC** | ウッドチップ調教 | 美浦・栗東トレセンでのウッドチップ調教データ |

### オッズ系データ

| 記号 | 説明 | 内容 |
|------|------|------|
| **O1** | オッズ1 | 単勝、複勝、枠連 |
| **O2** | オッズ2 | 馬連 |
| **O3** | オッズ3 | ワイド |
| **O4** | オッズ4 | 馬単 |
| **O5** | オッズ5 | 三連複 |
| **O6** | オッズ6 | 三連単 |

### 票数系データ（容量大）

| 記号 | 説明 |
|------|------|
| **H1** | 票数1（三連単以外） |
| **H6** | 票数6（三連単） |

## 重要なテーブル詳細

### SE（馬毎レース情報）- 最重要

予想に必要な情報のほとんどがこのテーブルに集約。

```
主要カラム:
- race_id          : レースID
- umaban           : 馬番
- wakuban          : 枠番
- kettonum         : 血統登録番号（馬の一意ID）
- kishucode        : 騎手コード
- futan            : 斤量
- bataiju          : 馬体重
- zogen            : 馬体重増減
- kakuteijyuni     : 確定着順
- time             : 走破タイム（秒×10）
- kohan3f          : 後半3Fタイム（秒×10）
- corner1-4        : 各コーナー通過順位
- chakusa          : 着差
- ninki            : 人気
- odds             : 単勝オッズ
```

### RA（レース詳細）

```
主要カラム:
- race_id          : レースID
- year             : 開催年
- jyocd            : 競馬場コード
- kaession         : 開催回
- nichession       : 開催日
- racenum          : レース番号
- kyori            : 距離
- trackcd          : トラックコード（芝/ダ/障害）
- courseinout      : コース（内/外）
- babajyotaicd     : 馬場状態コード
- tenko            : 天候
- grade            : グレード
```

### UM（競走馬マスタ）

```
主要カラム:
- kettonum         : 血統登録番号
- bamei            : 馬名
- birthdate        : 生年月日
- sexcd            : 性別コード
- keirocd          : 毛色コード
- ketto3info       : 血統情報（父、母、母父など）
```

### HC（坂路調教）

レコード長: 60バイト

```
主要カラム:
- tresen_kubun     : トレセン区分（0:美浦, 1:栗東）
- chokyo_date      : 調教年月日（yyyymmdd）
- chokyo_time      : 調教時刻（hhmm）
- kettonum         : 血統登録番号

<4ハロン800M>
- time_4f          : 4ハロンタイム合計(800M～0M) 単位:0.1秒
- lap_800_600      : ラップタイム(800M～600M) 単位:0.1秒

<3ハロン600M>
- time_3f          : 3ハロンタイム合計(600M～0M) 単位:0.1秒
- lap_600_400      : ラップタイム(600M～400M) 単位:0.1秒

<2ハロン400M>
- time_2f          : 2ハロンタイム合計(400M～0M) 単位:0.1秒
- lap_400_200      : ラップタイム(400M～200M) 単位:0.1秒

<1ハロン200M>
- lap_200_0        : ラップタイム(200M～0M) 単位:0.1秒
```

**注意**: 測定不良時は 0 がセットされる。予想時は 0 のデータを除外する必要がある。

### WC（ウッドチップ調教）

レコード長: 105バイト

```
主要カラム:
- tresen_kubun     : トレセン区分（0:美浦, 1:栗東）
- chokyo_date      : 調教年月日（yyyymmdd）
- chokyo_time      : 調教時刻（hhmm）
- kettonum         : 血統登録番号
- course           : コース（0:A, 1:B, 2:C, 3:D, 4:E）
- mawari           : 馬場周り（0:右, 1:左）

<10ハロン2000M>
- time_10f         : 10ハロンタイム合計(2000M～0M) 単位:0.1秒
- lap_2000_1800    : ラップタイム(2000M～1800M) 単位:0.1秒

<9ハロン1800M>
- time_9f          : 9ハロンタイム合計(1800M～0M) 単位:0.1秒
- lap_1800_1600    : ラップタイム(1800M～1600M) 単位:0.1秒

<8ハロン1600M>
- time_8f          : 8ハロンタイム合計(1600M～0M) 単位:0.1秒
- lap_1600_1400    : ラップタイム(1600M～1400M) 単位:0.1秒

<7ハロン1400M>
- time_7f          : 7ハロンタイム合計(1400M～0M) 単位:0.1秒
- lap_1400_1200    : ラップタイム(1400M～1200M) 単位:0.1秒

<6ハロン1200M>
- time_6f          : 6ハロンタイム合計(1200M～0M) 単位:0.1秒
- lap_1200_1000    : ラップタイム(1200M～1000M) 単位:0.1秒

<5ハロン1000M>
- time_5f          : 5ハロンタイム合計(1000M～0M) 単位:0.1秒
- lap_1000_800     : ラップタイム(1000M～800M) 単位:0.1秒

<4ハロン800M>
- time_4f          : 4ハロンタイム合計(800M～0M) 単位:0.1秒
- lap_800_600      : ラップタイム(800M～600M) 単位:0.1秒

<3ハロン600M>
- time_3f          : 3ハロンタイム合計(600M～0M) 単位:0.1秒
- lap_600_400      : ラップタイム(600M～400M) 単位:0.1秒

<2ハロン400M>
- time_2f          : 2ハロンタイム合計(400M～0M) 単位:0.1秒
- lap_400_200      : ラップタイム(400M～200M) 単位:0.1秒

<1ハロン200M>
- lap_200_0        : ラップタイム(200M～0M) 単位:0.1秒
```

**注意**:
- 測定不良時は 0 がセットされる
- 999.9秒以上の場合は 9999 がセット
- ウッドチップは最大10ハロン（2000M）まで計測可能
- 坂路（HC）に比べて長距離の調教が可能

## 競馬場コード

```
01: 札幌    06: 中山
02: 函館    07: 中京
03: 福島    08: 京都
04: 新潟    09: 阪神
05: 東京    10: 小倉
```

## 馬場状態コード

```
1: 良
2: 稍重
3: 重
4: 不良
```

## トラックコード

```
1: 芝
2: ダート
3: 障害
```

## グレードコード

```
A: G1
B: G2
C: G3
D: リステッド
E: オープン特別
F: 1600万下
G: 1000万下
H: 500万下
1: 新馬
2: 未勝利
```

## mykeibadbのテーブル対応

mykeibadbで生成されるテーブル名は、JV-Data仕様書の記号と若干異なる場合がある。
実際のテーブル名は、データ取り込み後に以下で確認：

```sql
-- テーブル一覧
\dt

-- テーブル構造
\d テーブル名
```

## 主要なクエリパターン

### 坂路調教データ取得（直近の追い切り）

```sql
-- 特定の馬の直近5回の坂路調教データ
SELECT
    chokyo_date,
    chokyo_time,
    tresen_kubun,
    time_4f,
    time_3f,
    time_2f,
    lap_200_0
FROM hanro_chokyo  -- テーブル名は実際のスキーマで確認
WHERE kettonum = '対象馬のkettonum'
  AND time_4f > 0  -- 測定不良データを除外
ORDER BY chokyo_date DESC, chokyo_time DESC
LIMIT 5;
```

### レース前週の調教評価

```sql
-- レース出走馬の直近1週間の調教タイム
SELECT
    u.bamei,
    s.umaban,
    hc.chokyo_date,
    hc.time_4f / 10.0 as time_4f_sec,  -- 0.1秒単位を秒に変換
    hc.time_3f / 10.0 as time_3f_sec,
    hc.lap_200_0 / 10.0 as last_lap_sec
FROM uma_race s
JOIN uma u ON s.kettonum = u.kettonum
LEFT JOIN hanro_chokyo hc ON s.kettonum = hc.kettonum
    AND hc.chokyo_date >= '対象レース日 - 7日'
    AND hc.chokyo_date < '対象レース日'
    AND hc.time_4f > 0
WHERE s.race_id = '対象レースID'
ORDER BY s.umaban, hc.chokyo_date DESC;
```

### 調教タイムランキング（レース内比較）

```sql
-- レース出走馬の直近調教タイムを比較
WITH latest_training AS (
    SELECT DISTINCT ON (s.kettonum)
        s.umaban,
        u.bamei,
        hc.chokyo_date,
        hc.time_4f,
        hc.time_3f,
        hc.lap_200_0
    FROM uma_race s
    JOIN uma u ON s.kettonum = u.kettonum
    LEFT JOIN hanro_chokyo hc ON s.kettonum = hc.kettonum
        AND hc.chokyo_date >= '対象レース日 - 14日'
        AND hc.time_4f > 0
    WHERE s.race_id = '対象レースID'
    ORDER BY s.kettonum, hc.chokyo_date DESC, hc.chokyo_time DESC
)
SELECT
    umaban,
    bamei,
    chokyo_date,
    time_4f / 10.0 as time_4f_sec,
    RANK() OVER (ORDER BY time_4f) as rank_4f,
    lap_200_0 / 10.0 as last_lap_sec,
    RANK() OVER (ORDER BY lap_200_0) as rank_last_lap
FROM latest_training
WHERE time_4f > 0
ORDER BY time_4f;
```

### 出馬表取得（今週のレース）

```sql
SELECT 
    r.race_id,
    r.kyori,
    r.trackcd,
    s.umaban,
    s.kettonum,
    u.bamei,
    s.kishucode,
    s.futan
FROM race r
JOIN uma_race s ON r.race_id = s.race_id
JOIN uma u ON s.kettonum = u.kettonum
WHERE r.year = '2025'
  AND r.monthday = '1228'
ORDER BY r.race_id, s.umaban;
```

### 過去走取得（直近5走）

```sql
SELECT 
    s.race_id,
    r.kyori,
    r.trackcd,
    r.jyocd,
    r.babajyotaicd,
    s.kakuteijyuni,
    s.time,
    s.kohan3f,
    s.chakusa,
    s.ninki
FROM uma_race s
JOIN race r ON s.race_id = r.race_id
WHERE s.kettonum = '対象馬のkettonum'
ORDER BY r.race_id DESC
LIMIT 5;
```

### 騎手成績

```sql
SELECT 
    k.kishumei,
    COUNT(*) as rides,
    SUM(CASE WHEN s.kakuteijyuni = 1 THEN 1 ELSE 0 END) as wins,
    ROUND(SUM(CASE WHEN s.kakuteijyuni = 1 THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100, 1) as win_rate
FROM uma_race s
JOIN kishu k ON s.kishucode = k.kishucode
JOIN race r ON s.race_id = r.race_id
WHERE r.year >= '2024'
GROUP BY k.kishumei
ORDER BY wins DESC;
```

## 参考資料

- [JV-Data仕様書（PDF）](https://jra-van.jp/dlb/sdv/sdk/JV-Data4901.pdf)
- [JV-Data仕様書（Excel）](https://jra-van.jp/dlb/sdv/sdk/JV-Data4901.xlsx)
- [JV-Linkインターフェース仕様書](https://jra-van.jp/dlb/sdv/sdk/JV-Link4901.pdf)
- [JRA-VAN Data Lab.開発ガイド](https://jra-van.jp/dlb/sdv/sdk/DataLab422.pdf)

## 調教データの予想への活用方法

### 1. 調教タイム評価

#### 坂路調教（HC）の基準値

**4ハロンタイム（time_4f）**:
- 優秀: 52秒台以下（520以下）
- 良好: 53秒台（530-539）
- 普通: 54秒台（540-549）
- やや遅い: 55秒以上（550以上）

**ラスト1ハロン（lap_200_0）**:
- 優秀: 12秒台以下（120以下）
- 良好: 13秒台前半（130-134）
- 普通: 13秒台後半（135-139）
- やや遅い: 14秒以上（140以上）

#### ウッドチップ調教（WC）の基準値

**6ハロンタイム（time_6f）** - 最も参考になる距離:
- 優秀: 82秒台以下（820以下）
- 良好: 83秒台（830-839）
- 普通: 84秒台（840-849）
- やや遅い: 85秒以上（850以上）

**4ハロンタイム（time_4f）**:
- 優秀: 53秒台以下（530以下）
- 良好: 54秒台（540-549）
- 普通: 55秒台（550-559）
- やや遅い: 56秒以上（560以上）

**調教コース・周り**:
- 美浦: コースA-E、栗東: コースA-E
- 右回り/左回りは本番レースに合わせて評価

### 2. 調教パターン分析

#### HC（坂路）とWC（ウッド）の使い分け

**坂路調教（HC）**:
- 短距離～マイル馬の仕上げに使用
- 上り坂で負荷をかけた調教
- ラスト1ハロンの切れが重要
- データの信頼性: 高い（ほぼ全馬が実施）

**ウッドチップ調教（WC）**:
- 中距離～長距離馬の調教に使用
- 平坦コースで持続力を養う
- 6-8ハロンのタイムが参考になる
- データの信頼性: 中（実施頻度は坂路より低い）

#### 理想的な追い切りパターン

**短距離～マイルレース**:
1. レース1週間前: HC 4F 52-53秒台（強め）
2. レース3-4日前: HC 4F 55秒前後（軽め）
3. ラスト1ハロン: 12秒台の切れ

**中距離～長距離レース**:
1. レース1週間前: WC 6F 82-83秒台 または HC 4F 53秒台
2. レース3-4日前: 軽めの調整
3. 持続力重視: 各ハロンが均等なペース

**注意すべきパターン**:
- 2週間以上調教データがない → 体調不安の可能性
- 直前の追い切りが異常に遅い → 状態悪化
- ラスト1ハロンが極端に速い → 叩かれすぎ
- HC/WC両方のデータがない → 調整不足

### 3. レース内比較

出走馬全体で調教タイムをランキングし、相対評価：
- 上位3位以内 → プラス評価
- 中位 → ニュートラル
- 下位 → マイナス評価

### 4. LLMプロンプトへの組み込み

```python
# 調教評価をプロンプトに含める例
prompt = f"""
{horse_name}の調教評価:
- 直近追い切り: {chokyo_date}
- 4ハロンタイム: {time_4f}秒
- ラスト1ハロン: {lap_200_0}秒
- レース内ランキング: {rank}位/{total}頭中

この調教タイムから、馬の仕上がり状態を評価してください。
"""
```

## 注意事項

1. **テーブル名・カラム名はmykeibadbのバージョンで異なる可能性あり**
   - 実際のスキーマは `\dt` と `\d テーブル名` で確認すること

2. **タイムは10倍された整数で格納**
   - 例: 1:34.5 → 945（94.5秒 × 10）
   - 調教タイム: 52.3秒 → 523（52.3秒 × 10）

3. **調教データの測定不良**
   - タイムが 0 の場合は測定不良
   - クエリで `WHERE time_4f > 0` で除外が必要

4. **着差は馬身単位で格納**
   - コード体系は仕様書参照

5. **日付・時刻は文字列で格納されている場合が多い**
   - 必要に応じてキャストが必要

6. **調教データの更新タイミング**
   - 毎日不規則（天候・休日により変動）
   - 基本的に月曜日は提供なし
