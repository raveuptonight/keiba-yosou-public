# ER図（Entity Relationship Diagram）

## 概要

JRA-VAN Data Lab.の27種類のテーブル間の関係性を定義します。

---

## 主要エンティティの関係

```
┌─────────────────────────────────────────────────────────────────┐
│                         レース中心の関係                          │
└─────────────────────────────────────────────────────────────────┘

                         ┌──────────────┐
                         │  RA (レース)  │
                         │  race_id (PK) │
                         └───────┬──────┘
                                 │ 1
                                 │
                                 │ N
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
          ▼                      ▼                      ▼
  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
  │ SE (馬毎成績) │      │ HR (払戻)     │      │ CK (着度数)   │
  │ race_id (FK) │      │ race_id (FK) │      │ race_id (FK) │
  │ kettonum (FK)│      └──────────────┘      │ kettonum (FK)│
  └──────┬───────┘                            └──────┬───────┘
         │                                            │
         │                                            │
         ▼                                            ▼
  ┌──────────────┐                            ┌──────────────┐
  │ UM (競走馬)   │◄───────────────────────────│  騎手・調教師 │
  │ kettonum (PK)│                            │  成績情報    │
  └──────┬───────┘                            └──────────────┘
         │
         │
         ▼
  ┌──────────────┐
  │ SK (産駒)     │
  │ kettonum (PK)│
  │ 3代血統      │
  └──────┬───────┘
         │
         │
         ▼
  ┌──────────────┐
  │ HN (繁殖馬)   │
  │ hansyoku (PK)│
  │ 父母(FK)再帰 │
  └──────────────┘
```

---

## 詳細ER図

### 1. レース関連テーブル

#### 主テーブル: RA (レース詳細)

```
RA (race)
├─ race_id (PK): kaisai_year(4) + kaisai_monthday(4) + jyocd(2)
│                + kaisai_kai(2) + kaisai_nichime(2) + race_num(2)
├─ kyoso_hondai: 競走名
├─ grade_cd: グレードコード
├─ kyori: 距離
├─ track_cd: トラックコード
├─ tenko_cd: 天候
├─ shiba_baba_cd: 芝馬場状態
└─ dirt_baba_cd: ダート馬場状態

1 ─┬─ N
   │
   ├─> SE (uma_race) - 馬毎レース情報
   │   └─ race_id + umaban (PK)
   │
   ├─> HR (haraimodoshi) - 払戻
   │   └─ race_id (PK)
   │
   ├─> CK (chakudo) - 出走別着度数
   │   └─ race_id + kettonum (PK)
   │
   ├─> O1～O6 (odds) - オッズ
   │   └─ race_id (PK/FK)
   │
   ├─> WE (tenkou_baba) - 天候馬場状態
   │   └─ race_id + happyo_jifun (PK)
   │
   ├─> AV (torikeshi) - 出走取消
   │   └─ race_id + umaban (PK)
   │
   ├─> JC (kishu_henkou) - 騎手変更
   │   └─ race_id + umaban (PK)
   │
   ├─> TC (jikoku_henkou) - 発走時刻変更
   │   └─ race_id (PK)
   │
   └─> CC (course_henkou) - コース変更
       └─ race_id (PK)
```

#### SE (馬毎レース情報) の外部キー

```
SE (uma_race)
├─ race_id (FK) ───────────> RA.race_id
├─ kettonum (FK) ──────────> UM.kettonum
├─ kishu_cd (FK) ──────────> KS.kishu_cd
├─ chokyoshi_cd (FK) ──────> CH.chokyoshi_cd
└─ banushi_cd (FK) ────────> BN.banushi_cd (馬主マスタ)
```

---

### 2. 競走馬・血統関連テーブル

```
UM (uma - 競走馬マスタ)
├─ kettonum (PK): 血統登録番号
├─ bamei: 馬名
├─ birth_date: 生年月日
├─ sex_cd: 性別
└─ heichi_shutoku: 平地収得賞金（クラス分け基準）

1 ─┬─ 1
   │
   ├─> SK (sanku - 産駒マスタ)
   │   ├─ kettonum (PK/FK)
   │   └─ sandai_ketto[14] (FK) ───> HN.hansyoku_num (14頭分)
   │
   └─> HN (hansyoku - 繁殖馬マスタ) ※UMから直接参照する場合
       ├─ hansyoku_num (PK)
       ├─ chichi_hansyoku_num (FK) ──> HN.hansyoku_num (再帰)
       ├─ haha_hansyoku_num (FK) ───> HN.hansyoku_num (再帰)
       └─ kettonum

HN (繁殖馬マスタ) - 再帰構造
┌──────────────────────────────┐
│  HN (hansyoku_num=A)         │
│  ├─ chichi (父) = B          │◄─┐
│  └─ haha (母) = C            │  │
└──────────────────────────────┘  │
         │                        │
         └─> 再帰参照 ─────────────┘
             HN (hansyoku_num=B)  ※父馬
             HN (hansyoku_num=C)  ※母馬
                 └─> さらに父母を遡れる（5代血統）

BT (系統情報)
├─ hansyoku_num (PK/FK) ──────> HN.hansyoku_num
├─ keitou_id: 系統ID（30桁、2桁ごとに階層）
├─ keitou_mei: 系統名
└─ keitou_setumei: 系統説明（6800バイト）
```

---

### 3. 人物マスタ

```
KS (kishu - 騎手マスタ)
├─ kishu_cd (PK): 騎手コード
├─ kishu_mei: 騎手名
├─ shozoku: 所属
└─ seiseki: 本年・前年・累計成績

CH (chokyoshi - 調教師マスタ)
├─ chokyoshi_cd (PK): 調教師コード
├─ chokyoshi_mei: 調教師名
├─ shozoku: 所属
└─ seiseki: 本年・前年・累計成績

※CK（出走別着度数）に騎手・調教師の詳細成績も含まれる
```

---

### 4. 調教データ

```
HC (hanro_chokyo - 坂路調教)
├─ chokyo_date + kettonum (PK)
├─ kettonum (FK) ──────────> UM.kettonum
├─ time_4f: 4ハロンタイム
└─ lap_200_0: ラスト1ハロン

WC (wood_chokyo - ウッドチップ調教)
├─ chokyo_date + kettonum (PK)
├─ kettonum (FK) ──────────> UM.kettonum
├─ time_10f～time_3f: 各距離タイム
└─ course: コース（A-E）
```

---

### 5. スケジュール・運用データ

```
TK (tokubetsu_toroku - 特別登録馬)
├─ race_id + kettonum (PK)
├─ race_id ───────────────> RA.race_id
├─ kettonum ──────────────> UM.kettonum
└─ kyoso_joken_cd: 競走条件

YS (kaisai_schedule - 開催スケジュール)
├─ kaisai_date + jyocd (PK)
└─ jusho_info[3]: 重賞情報（最大3レース）

CS (course_info - コース情報)
├─ jyocd + kyori + track_cd + kaishu_ymd (PK)
├─ course_setumei: コース説明（6800バイト）
└─ kaishu_ymd: コース改修年月日

RC (record - レコードマスタ)
├─ record_shikibetsu + jyocd + kyori + track_cd (PK)
├─ record_time: レコードタイム
└─ record保持馬[3]: 保持馬情報
```

---

### 6. オッズ・払戻

```
O1 (odds_tanpuku - 単勝・複勝・枠連)
├─ race_id (PK/FK) ──────> RA.race_id
├─ data_kubun: 1:中間 2:前日 3:最終 4:確定
└─ tansho/fukusho/wakuren オッズ

O2～O6 (馬連、ワイド、馬単、3連複、3連単)
├─ race_id (PK/FK) ──────> RA.race_id
└─ 各馬券種のオッズ・人気順

HR (haraimodoshi - 払戻)
├─ race_id (PK/FK) ──────> RA.race_id
└─ 各馬券種の払戻金額・的中馬番
```

---

## 主キー・外部キー一覧

### 主キー (Primary Key)

| テーブル | 主キー構成 | 桁数 |
|---------|-----------|------|
| **RA** | kaisai_year + kaisai_monthday + jyocd + kaisai_kai + kaisai_nichime + race_num | 16桁 |
| **SE** | race_id + umaban | 18桁 |
| **UM** | kettonum | 10桁 |
| **KS** | kishu_cd | 5桁 |
| **CH** | chokyoshi_cd | 5桁 |
| **HN** | hansyoku_num | 10桁 |
| **SK** | kettonum | 10桁 |
| **CK** | race_id + kettonum | 26桁 |
| **HR** | race_id | 16桁 |
| **HC** | chokyo_date + kettonum | 18桁 |
| **WC** | chokyo_date + kettonum | 18桁 |
| **O1～O6** | race_id (+ happyo_jifun※中間のみ) | 16桁(+8桁) |
| **TK** | race_id + kettonum | 26桁 |
| **YS** | kaisai_date + jyocd + kaisai_kai + kaisai_nichime | 12桁 |
| **CS** | jyocd + kyori + track_cd + kaishu_ymd | 18桁 |
| **RC** | record_shikibetsu + jyocd + kyoso_shubetsu + kyori + track_cd | - |
| **BT** | hansyoku_num | 10桁 |
| **WE** | race_date + jyocd + kaisai_kai + kaisai_nichime + happyo_jifun + henkou_shikibetsu | - |
| **AV** | race_id + umaban | 18桁 |
| **JC** | race_id + happyo_jifun + umaban | 26桁 |
| **TC** | race_id + happyo_jifun | 24桁 |
| **CC** | race_id + happyo_jifun | 24桁 |

### 外部キー (Foreign Key)

| 子テーブル | 外部キー | 親テーブル | 参照キー |
|-----------|---------|-----------|---------|
| **SE** | race_id | RA | race_id |
| **SE** | kettonum | UM | kettonum |
| **SE** | kishu_cd | KS | kishu_cd |
| **SE** | chokyoshi_cd | CH | chokyoshi_cd |
| **CK** | race_id | RA | race_id |
| **CK** | kettonum | UM | kettonum |
| **SK** | kettonum | UM | kettonum |
| **SK** | sandai_ketto[i] | HN | hansyoku_num |
| **HN** | chichi_hansyoku_num | HN | hansyoku_num (再帰) |
| **HN** | haha_hansyoku_num | HN | hansyoku_num (再帰) |
| **BT** | hansyoku_num | HN | hansyoku_num |
| **HC** | kettonum | UM | kettonum |
| **WC** | kettonum | UM | kettonum |
| **HR** | race_id | RA | race_id |
| **O1～O6** | race_id | RA | race_id |
| **TK** | race_id | RA | race_id |
| **TK** | kettonum | UM | kettonum |
| **WE** | race_id | RA | race_id |
| **AV** | race_id | RA | race_id |
| **JC** | race_id | RA | race_id |
| **TC** | race_id | RA | race_id |
| **CC** | race_id | RA | race_id |

---

## データの流れ（予想時）

```
┌──────────────────────────────────────────────────────────┐
│  1. レース基本情報の取得                                   │
└──────────────────────────────────────────────────────────┘

TK (特別登録馬) ─> 今後のレース一覧取得
    │
    ▼
RA (レース詳細) ─> レース条件（距離、トラック、天候等）
    │
    ▼
YS (開催スケジュール) ─> 重賞レース情報

┌──────────────────────────────────────────────────────────┐
│  2. 出走馬情報の取得                                       │
└──────────────────────────────────────────────────────────┘

SE (馬毎レース情報) ─> 出走馬リスト、騎手、調教師
    │
    ├─> UM (競走馬マスタ) ─> 馬の基本情報、賞金、脚質
    │       │
    │       ├─> SK (産駒マスタ) ─> 3代血統
    │       │       │
    │       │       └─> HN (繁殖馬マスタ) ─> 5代血統、母父
    │       │               │
    │       │               └─> BT (系統情報) ─> 系統適性
    │       │
    │       ├─> HC/WC (調教データ) ─> 仕上がり状態
    │       │
    │       └─> SE (過去レース) ─> 過去成績（再帰的に取得）
    │
    ├─> CK (出走別着度数) ─> 詳細な適性データ
    │       ├─ 馬場別着回数
    │       ├─ 距離別着回数
    │       ├─ 競馬場別着回数
    │       ├─ 騎手成績
    │       └─ 調教師成績
    │
    ├─> KS (騎手マスタ) ─> 騎手の得意コース
    │
    └─> CH (調教師マスタ) ─> 調教師の得意パターン

┌──────────────────────────────────────────────────────────┐
│  3. コース・条件情報                                       │
└──────────────────────────────────────────────────────────┘

CS (コース情報) ─> コース特性（直線長、高低差等）
    │
RC (レコードマスタ) ─> コースレコード、G1レコード
    │
WE (天候馬場状態) ─> リアルタイム馬場状態

┌──────────────────────────────────────────────────────────┐
│  4. 人気・オッズ情報                                       │
└──────────────────────────────────────────────────────────┘

O1～O6 (オッズ) ─> 最終オッズ、人気順

┌──────────────────────────────────────────────────────────┐
│  5. 変更情報（リアルタイム）                               │
└──────────────────────────────────────────────────────────┘

JC (騎手変更) ─> 騎手の乗り替わり
TC (発走時刻変更) ─> スケジュール調整
CC (コース変更) ─> コース変更（予想の再実行）
AV (出走取消) ─> 取消馬の除外

┌──────────────────────────────────────────────────────────┐
│  6. 予想実行 → LLMへデータ投入                              │
└──────────────────────────────────────────────────────────┘

上記全データをJSON形式で整形 → Claude APIへ送信
    │
    ▼
予想結果（JSON） → DB保存 → Discord通知

┌──────────────────────────────────────────────────────────┐
│  7. 結果検証                                              │
└──────────────────────────────────────────────────────────┘

HR (払戻) ─> 的中判定、回収率計算
```

---

## mykeibadbでのテーブル名マッピング（予想）

JRA-VAN仕様書のレコードIDとmykeibadbでのテーブル名は異なる可能性があります。
データダウンロード完了後、以下のコマンドで確認が必要です：

```sql
-- テーブル一覧確認
\dt

-- テーブル構造確認
\d テーブル名
```

想定されるテーブル名マッピング例：

| レコードID | 想定テーブル名 | 別名候補 |
|-----------|--------------|---------|
| RA | race / race_shosai | races |
| SE | uma_race / umagoto_race_joho | race_horses |
| UM | uma | horses |
| KS | kishu | jockeys |
| CH | chokyoshi | trainers |
| HN | hansyokuba | broodmares |
| SK | sanku | offspring |
| HC | hanro_chokyo | hillwork_training |
| WC | wood_chokyo | woodchip_training |
| HR | haraimodoshi | payouts |
| O1～O6 | odds_* | - |
| CK | chakudo / shutsubetsu_chakudo | race_statistics |

※実際のテーブル名はデータダウンロード完了後に確認します。

---

## 次のステップ

1. ✅ **ER図作成完了**
2. 次: **インデックス設計** (docs/INDEX_DESIGN.md)
3. その後: **API設計** (docs/API_DESIGN.md)
