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

## 注意事項

1. **テーブル名・カラム名はmykeibadbのバージョンで異なる可能性あり**
   - 実際のスキーマは `\dt` と `\d テーブル名` で確認すること

2. **タイムは10倍された整数で格納**
   - 例: 1:34.5 → 945（94.5秒 × 10）

3. **着差は馬身単位で格納**
   - コード体系は仕様書参照

4. **日付・時刻は文字列で格納されている場合が多い**
   - 必要に応じてキャストが必要
