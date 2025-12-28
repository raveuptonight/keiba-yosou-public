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

レコード長: 555バイト

**主キー構成**:
開催年(4) + 開催月日(4) + 競馬場コード(2) + 開催回(2) + 開催日目(2) + レース番号(2) + 馬番(2) = 18桁

**外部キー**:
- 血統登録番号 → UM（競走馬マスタ）
- 調教師コード → CH（調教師マスタ）
- 騎手コード → KS（騎手マスタ）

```
基本情報:
- record_id         : レコード種別ID "SE"
- data_kubun        : データ区分（1-7,A,B1,B2）RAと同じ
- kaisai_year       : 開催年（4桁）
- kaisai_monthday   : 開催月日（4桁）
- jyocd             : 競馬場コード（2桁）
- kaisai_kai        : 開催回（2桁）
- kaisai_nichime    : 開催日目（2桁）
- race_num          : レース番号（2桁）

馬情報:
- wakuban           : 枠番（1桁）
- umaban            : 馬番（2桁）
- kettonum          : 血統登録番号（10桁）生年4桁+品種1桁+数字5桁
- bamei             : 馬名（全角18文字）
- kigou_cd          : 馬記号コード（招待、抽選等）
- sex_cd            : 性別コード（牡/牝/セ）
- hinshu_cd         : 品種コード（サラ系等）
- keiro_cd          : 毛色コード（2桁）
- barei             : 馬齢（2桁）※2000年以前は数え年、2001年以降は満年齢

調教師・馬主:
- tozai_shozoku_cd  : 東西所属コード（美浦/栗東）
- chokyoshi_cd      : 調教師コード（5桁）
- chokyoshi_mei     : 調教師名略称（全角4文字）
- banushi_cd        : 馬主コード（6桁）
- banushi_mei       : 馬主名（全角32文字、法人格無し）
- fukushoku         : 服色標示（全角30文字、勝負服の色・模様）

負担重量・騎手:
- futan             : 負担重量（3桁、単位:0.1kg）
- henkou_mae_futan  : 変更前負担重量
- blinker_kbn       : ブリンカー使用区分（0:未使用 1:使用）
- kishu_cd          : 騎手コード（5桁）
- henkou_mae_kishu  : 変更前騎手コード
- kishu_mei         : 騎手名略称（全角4文字）
- kishu_minarai_cd  : 騎手見習コード（▲△☆等）

馬体重:
- bataiju           : 馬体重（3桁、単位:kg）
                      002-998:有効値 999:計量不能 000:出走取消
- zogen_fugo        : 増減符号（+:増加 -:減少）
- zogen_sa          : 増減差（3桁、単位:kg）
                      001-998:有効値 999:計量不能 000:前差なし
                      スペース:初出走

レース結果:
- ijyo_kbn_cd       : 異常区分コード（出走取消/競走除外/発走除外/競走中止）
- nyusen_juni       : 入線順位（2桁、失格・降着前）
- kakutei_chakujun  : 確定着順（2桁、失格・降着後の最終順位）
- dochaku_kbn       : 同着区分（0:なし 1:あり）
- dochaku_tosu      : 同着頭数（0-2）
- time              : 走破タイム（4桁、単位:0.1秒、9分99秒9）
                      例: 9459 = 9分45秒9
- chakusa_cd        : 着差コード（3桁、前馬との着差）
- plus_chakusa_cd   : ＋着差コード（前馬失格時）
- plus2_chakusa_cd  : ＋＋着差コード（前馬2頭失格時）

コーナー通過順位:
- corner_1          : 1コーナーでの順位（2桁）
- corner_2          : 2コーナーでの順位（2桁）
- corner_3          : 3コーナーでの順位（2桁）
- corner_4          : 4コーナーでの順位（2桁）

オッズ・人気・賞金:
- tansho_odds       : 単勝オッズ（4桁、単位:0.1倍、999.9倍）
- tansho_ninki      : 単勝人気順（2桁）
- kakutoku_honsho   : 獲得本賞金（8桁、単位:百円）
- kakutoku_fukasho  : 獲得付加賞金（8桁、単位:百円）

上がりタイム:
- ato_4f            : 後4ハロンタイム（3桁、単位:0.1秒）
- ato_3f            : 後3ハロンタイム（3桁、単位:0.1秒）
                      基本的には後3Fのみ設定
                      障害は1F平均タイムを設定
                      999:出走取消/競走除外/タイムオーバー

相手馬情報（同着考慮で3回繰返）:
- aite_kettonum_1   : 1着馬血統登録番号（自身が1着なら2着馬）
- aite_bamei_1      : 1着馬馬名
- aite_kettonum_2   : （同着時2頭目）
- aite_bamei_2      : （同着時2頭目）
- aite_kettonum_3   : （同着時3頭目）
- aite_bamei_3      : （同着時3頭目）
- time_sa           : タイム差（4桁、符号+99秒9）
                      1着:-、2着以下:+
                      9999:出走取消等

その他:
- record_koshin_kbn : レコード更新区分
- kyakushitsu       : 今回レース脚質判定（1:逃 2:先 3:差 4:追）

マイニング予想（データ区分7のみ）:
- mining_kbn        : マイニング区分（1:前日 2:当日 3:直前）
- mining_time       : マイニング予想走破タイム
- mining_gosa_plus  : 予想誤差＋（早くなる方向）
- mining_gosa_minus : 予想誤差－（遅くなる方向）
- mining_juni       : マイニング予想順位
```

**データ区分による設定値の違い**:
- データ区分1（木曜出走馬名表）: 馬情報、調教師、騎手、負担重量のみ
- データ区分2（金土出馬表）: 馬番確定、馬体重以外
- データ区分3-6（速報）: 着順・タイム等が段階的に確定
- データ区分7（月曜確定成績）: 全項目確定、マイニング予想含む
- データ区分B1（海外日本馬）、B2（海外外国馬）: 一部項目のみ

### RA（レース詳細）

レコード長: 1272バイト

**主キー構成** (race_id):
開催年(4) + 開催月日(4) + 競馬場コード(2) + 開催回(2) + 開催日目(2) + レース番号(2) = 16桁

```
基本情報:
- record_id         : レコード種別ID "RA"
- data_kubun        : データ区分（1:出走馬名表 2:出馬表 3-7:速報成績 A:地方 B:海外）
- kaisai_year       : 開催年（4桁 yyyy）
- kaisai_monthday   : 開催月日（4桁 mmdd）
- jyocd             : 競馬場コード（2桁）
- kaisai_kai        : 開催回[第N回]（2桁）
- kaisai_nichime    : 開催日目[N日目]（2桁）
- race_num          : レース番号（2桁）
- youbi_cd          : 曜日コード

競走名:
- kyoso_hondai      : 競走名本題（全角30文字）
- kyoso_fukudai     : 競走名副題（全角30文字）
- kyoso_kakko       : 競走名カッコ内（全角30文字）
- kyoso_ryaku_10    : 略称10文字
- kyoso_ryaku_6     : 略称6文字
- kyoso_ryaku_3     : 略称3文字

グレード・条件:
- grade_cd          : グレードコード（G1/G2/G3/Jpn1/Jpn2/Jpn3等）
- kyoso_shubetsu_cd : 競走種別コード
- kyoso_kigo_cd     : 競走記号コード
- juryo_shubetsu_cd : 重量種別コード（定量/別定/馬齢等）
- joken_2sai        : 2歳条件
- joken_3sai        : 3歳条件
- joken_4sai        : 4歳条件
- joken_5sai_ijo    : 5歳以上条件

コース:
- kyori             : 距離（メートル 4桁）
- track_cd          : トラックコード（芝/ダート/障害）
- course_kubun      : コース区分（A～E）

賞金:
- honsho_1～5       : 本賞金1～5着（単位:百円）
- fukasho_1～3      : 付加賞金1～3着（単位:百円）

レース実施:
- hassou_jikoku     : 発走時刻（hhmm）
- touroku_tosu      : 登録頭数
- shusso_tosu       : 出走頭数
- nyusen_tosu       : 入線頭数

馬場・天候:
- tenko_cd          : 天候コード（晴/曇/雨等）
- shiba_baba_cd     : 芝馬場状態（良/稍重/重/不良）
- dirt_baba_cd      : ダート馬場状態

ラップタイム（平地）:
- lap_time          : 1ハロン毎ラップ（25回×単位:0.1秒）
- mae_3f            : 前3ハロン（単位:0.1秒）
- mae_4f            : 前4ハロン（単位:0.1秒）
- ato_3f            : 後3ハロン（単位:0.1秒）
- ato_4f            : 後4ハロン（単位:0.1秒）

コーナー通過順位:
- corner_tuka       : 各コーナー通過順位
                      例: (4,5,6,*7)=1-2,3,8,9(10,11)
                      ():集団 =:大差 -:小差 *:先頭
```

**データ区分の遷移**:
木曜→出走馬名表(1) → 金土→出馬表(2) → 速報(3-6) → 月曜→確定成績(7)

### UM（競走馬マスタ）

レコード種別ID: **UM**

```
主要カラム:
- kettonum         : 血統登録番号（10桁）
- bamei            : 馬名
- birthdate        : 生年月日
- sexcd            : 性別コード
- keirocd          : 毛色コード
- ketto3info       : 血統情報（父、母、母父など）
- zaiky_flag       : JRA施設在きゅうフラグ

賞金情報:
- heichi_honsho    : 平地本賞金累計（単位:百円）JRAの平地競走において獲得した本賞金の累計
- shogai_honsho    : 障害本賞金累計（単位:百円）JRAの障害競走において獲得した本賞金の累計
- heichi_fukasho   : 平地付加賞金累計（単位:百円）JRAの平地競走において獲得した付加賞金の累計
- shogai_fukasho   : 障害付加賞金累計（単位:百円）JRAの障害競走において獲得した付加賞金の累計
- heichi_shutoku   : 平地収得賞金累計（単位:百円）クラス分けの基準となる賞金額
- shogai_shutoku   : 障害収得賞金累計（単位:百円）障害競走において獲得した収得賞金額の合計

各着回数（1986年以降のみカウント）:
- 1～5着、6着以下の各回数
- 競馬場別着回数
- 距離別着回数
- 馬場状態別着回数（良/稍重/重/不良）

脚質傾向（kyakushitsu_keikou）:
- 過去レースでの位置取りを[逃･先･差･追]の4段階で判定しカウント
- 判定方法:
  ■逃げ: 最終コーナー以外のいずれかのコーナーを1位で通過
  ■先行: 最終コーナーを4位以内で通過（逃げ除く）
  ■差し: 最終コーナーの通過順位が出走頭数の3分の2以内（逃げ・先行除く、8頭未満では該当なし）
  ■追込: 上記以外
  ※直線コースの場合は走破タイムから後3ハロンタイムを引いた値で判定
```

**重要な特記事項**:

1. **JRA施設在きゅうフラグ**: 平成18年6月6日以降設定、それ以前はスペース
2. **獲得賞金**: 一般的には平地・障害の本賞金と付加賞金の合計額（26～29の合計）を獲得賞金という
3. **収得賞金**:
   - 本賞金をJRAの定める規定に従って加算したもので**クラス分けの基準**となる重要指標
   - 平地収得賞金累計: 平地競走で獲得した収得賞金の合計（1999年以前は障害も含む）
   - 4歳夏季競馬以降: 4歳春季競馬まで獲得した収得賞金の2分の1 + 4歳夏季競馬以降に獲得した収得賞金
   - 平成18年度夏季競馬開始時: 4歳以上の全馬について収得賞金の2分の1を設定
   - **平成31年度夏季競馬以降**: 降級処理廃止のため、収得賞金の再計算は行わない
4. **各着回数**: 1986年以降についてのみカウント
5. **障害レース馬場状態**: トラックが「芝→ダート」となるものはダートの馬場状態でカウント
6. **レース中止・出走取消**: 脚質傾向のカウント対象外

### KS（騎手マスタ）

レコード種別ID: **KS**

```
主要カラム:
- kishu_cd         : 騎手コード（5桁）
- kishu_mei        : 騎手名
- kishu_mei_kana   : 騎手名カナ
- shozoku          : 所属（美浦/栗東/海外等）
- massho_kubun     : 騎手抹消区分（0:現役, 1:抹消）
- menkyo_kofu_date : 騎手免許交付年月日（yyyymmdd）
- menkyo_massho_date : 騎手免許抹消年月日（yyyymmdd）

成績情報（本年・前年・累計）:
- honnen_seiseki   : 本年成績（1着～6着以下、勝率、連対率等）
- zennen_seiseki   : 前年成績
- ruikei_seiseki   : 累計成績

競馬場別・距離別着回数（1986年以降のみカウント）:
- jyoba_chakasuu   : 競馬場別着回数
- kyori_chakasuu   : 距離別着回数
```

**重要な特記事項**:

1. **騎手抹消区分**: `1:抹消` の場合、騎手免許抹消年月日が初期値（スペース）の場合がある
2. **未来日設定**: 騎手免許交付年月日・抹消年月日に未来日が設定されることがある
3. **招待騎手**: 引退後も本年、前年、累計の順に成績を設定する
4. **競馬場別・距離別着回数**: 1986年以降についてのみカウント

### CH（調教師マスタ）

レコード種別ID: **CH**

```
主要カラム:
- chokyoshi_cd     : 調教師コード（5桁）
- chokyoshi_mei    : 調教師名
- chokyoshi_mei_kana : 調教師名カナ
- shozoku          : 所属（美浦/栗東等）
- massho_kubun     : 調教師抹消区分（0:現役, 1:抹消）
- menkyo_kofu_date : 調教師免許交付年月日（yyyymmdd）
- menkyo_massho_date : 調教師免許抹消年月日（yyyymmdd）

成績情報（本年・前年・累計）:
- honnen_seiseki   : 本年成績（1着～6着以下、勝率、連対率等）
- zennen_seiseki   : 前年成績
- ruikei_seiseki   : 累計成績

競馬場別・距離別着回数（1986年以降のみカウント）:
- jyoba_chakasuu   : 競馬場別着回数
- kyori_chakasuu   : 距離別着回数
```

**重要な特記事項**:

1. **調教師抹消区分**: `1:抹消` の場合、調教師免許抹消年月日が初期値（スペース）の場合がある
2. **未来日設定**: 調教師免許交付年月日・抹消年月日に未来日が設定されることがある
3. **招待調教師**: 引退後も本年、前年、累計の順に成績を設定する
4. **競馬場別・距離別着回数**: 1986年以降についてのみカウント

### TK（特別登録馬）

レコード種別ID: **TK**

**用途**: 今後開催予定のレース一覧と出走予定馬の情報（スケジューラーで「今日のレース」取得に必須）

```
主要カラム:
- kaisai_year      : 開催年（4桁）
- kaisai_monthday  : 開催月日（4桁）
- jyocd            : 競馬場コード（2桁）
- kaisai_kai       : 開催回（2桁）
- kaisai_nichime   : 開催日目（2桁）
- race_num         : レース番号（2桁）
- kettonum         : 血統登録番号（10桁）
- bamei            : 馬名

レース情報:
- kyoso_hondai     : 競走名本題
- kyoso_fukudai    : 競走名副題
- grade_cd         : グレードコード（G1/G2/G3/Jpn1/Jpn2/Jpn3等）
- kyoso_joken_cd   : 競走条件コード（2歳/3歳/4歳/5歳以上/最若年）
```

**重要な特記事項**:

1. **グレードコード表記の年度による違い**:
   - **2006年以前**: 全て「G」表記（国際格付けの有無に関係なく）
   - **2007-2009年**: 国際格付けあり→「G」、なし→「Jpn」
   - **2010年以降**: 格付けのない競走を除き全て「G」表記（全てが国際格付けを獲得）

   **注意**: JV-Data仕様では2007-2009年の国際格付け判定ができないため、別途判定が必要
   - 国際格付けCSVファイル: http://dl.cdn.jra-van.ne.jp/datalab/grade/International.csv
   - CSVフォーマット: 1行目=更新日付, 2行目以降=年度と特別競走番号

2. **競走条件コードの制度変更**:

   **平成18年度夏季競馬以降** - 収得賞金変更に伴う条件統一:
   ```
   <平成18年度夏季競馬以前>
   サラ系3歳以上:
     3歳500万下 4歳以上1000万下 → (3歳:"005" 4歳5歳以上:"010")
     3歳1000万下 4歳以上2000万下 → (3歳:"010" 4歳5歳以上:"020")
     3歳1600万下 4歳以上3200万下 → (3歳:"016" 4歳5歳以上:"032")

   サラ系4歳以上:
     4歳以上500万下 → (4歳:"005" 5歳以上:"010")
     4歳以上1000万下 → (4歳:"010" 5歳以上:"020")
     4歳以上1600万下 → (4歳:"016" 5歳以上:"032")

   <平成18年度夏季競馬以降>
   サラ系3歳以上:
     3歳以上500万下 → (3歳4歳5歳以上とも:"005")
     3歳以上1000万下 → (3歳4歳5歳以上とも:"010")
     3歳以上1600万下 → (3歳4歳5歳以上とも:"016")

   サラ系4歳以上:
     4歳以上500万下 → (4歳5歳以上とも:"005")
     4歳以上1000万下 → (4歳5歳以上とも:"010")
     4歳以上1600万下 → (4歳5歳以上とも:"016")

   ※最若年条件には変更なし
   ```

   **平成31年度夏季競馬以降** - 競走条件の呼称変更:
   ```
   500万下("005") → 1勝クラス("005")
   1000万下("010") → 2勝クラス("010")
   1600万下("016") → 3勝クラス("016")

   ※コード値は変更なし、呼称のみ変更
   ```

### BT（系統情報）

レコード種別ID: **BT**
レコード長: **6889バイト**

**用途**: 血統の系統分類と系統別適性分析（芝/ダート、距離適性の推論に使用）

```
主要カラム:
- record_id        : レコード種別ID "BT"
- data_kubun       : データ区分（0:削除, 1:新規, 2:更新）
- data_sakusei_ymd : データ作成年月日（yyyymmdd）
- hansyoku_num     : 繁殖登録番号（10桁）
- keitou_id        : 系統ID（30桁）2桁ごとに系譜を表現するID
- keitou_mei       : 系統名（全角36文字）例: "サンデーサイレンス系"
- keitou_setumei   : 系統説明（6800バイト）テキスト文
```

**重要な特記事項**:

1. **系統ID（30桁）の構造**:
   - 2桁ごとに系譜の階層を表現
   - 例: 親系統→子系統→孫系統... と階層的に管理
   - この構造により、どの大系統に属するかを判別可能

2. **系統説明の活用**:
   - 6800バイトの大容量テキストフィールド
   - その系統の特徴、適性、代表馬などの情報が記載
   - LLMプロンプトに含めることで血統適性の推論精度向上が期待できる

3. **予想での活用例**:
   - サンデーサイレンス系 → 芝・中距離に強い傾向
   - ノーザンダンサー系 → ダート・短距離に強い傾向
   - 系統説明テキストをLLMに渡して適性判断

### HN（繁殖馬マスタ）

レコード種別ID: **HN**
レコード長: **251バイト**

**用途**: 血統情報の詳細データ（父・母を遡って5代血統まで追跡可能）

```
主要カラム:
- record_id        : レコード種別ID "HN"
- data_kubun       : データ区分（0:削除, 1:新規, 2:更新）
- data_sakusei_ymd : データ作成年月日（yyyymmdd）
- hansyoku_num     : 繁殖登録番号（10桁）主キー
- kettonum         : 血統登録番号（10桁）外国繁殖馬は初期値の場合あり
- bamei            : 馬名（全角18文字）外国繁殖馬は欧字名の頭36バイト
- bamei_kana       : 馬名半角カナ（40文字）日本語馬のみ、外国繁殖馬は設定なし
- bamei_ouji       : 馬名欧字（全角40文字/半角80文字）
- birth_year       : 生年（西暦4桁）
- sex_cd           : 性別コード（牡/牝等）
- hinshu_cd        : 品種コード（サラ系等）
- keiro_cd         : 毛色コード（2桁）
- mochikomi_kubun  : 繁殖馬持込区分（0:内国産, 1:持込, 2:輸入内国産扱い, 3:輸入, 9:その他）
- yunyuu_year      : 輸入年（西暦4桁）
- sanchi_mei       : 産地名（全角10文字）
- chichi_hansyoku_num : 父馬繁殖登録番号（10桁）
- haha_hansyoku_num   : 母馬繁殖登録番号（10桁）
```

**主キー**: 繁殖登録番号（hansyoku_num）

**外部キー関連**:
- UM（競走馬マスタ）.kettonum → HN.kettonum で紐付け
- 父馬・母馬の繁殖登録番号で再帰的に血統を遡れる
- BT（系統情報）.hansyoku_num でも参照される

**重要な特記事項**:

1. **同一馬で繁殖登録番号が複数存在する場合がある**
   - 同じ馬が複数の繁殖登録番号を持つケースあり
   - 血統登録番号での名寄せが必要

2. **外国繁殖馬の扱い**:
   - 血統登録番号が初期値（0 or スペース）の場合がある
   - 馬名フィールドには馬名欧字の頭36バイトを設定
   - 馬名半角カナは設定されない（空白）

3. **血統の遡り方**:
   ```sql
   -- 5代血統を取得するクエリ例
   WITH RECURSIVE pedigree AS (
     -- 起点：対象馬
     SELECT kettonum, bamei, chichi_hansyoku_num, haha_hansyoku_num, 1 as generation
     FROM hansyoku_master
     WHERE kettonum = '対象馬の血統登録番号'

     UNION ALL

     -- 再帰：父馬・母馬を遡る
     SELECT h.kettonum, h.bamei, h.chichi_hansyoku_num, h.haha_hansyoku_num, p.generation + 1
     FROM hansyoku_master h
     JOIN pedigree p ON (h.hansyoku_num = p.chichi_hansyoku_num OR h.hansyoku_num = p.haha_hansyoku_num)
     WHERE p.generation < 5
   )
   SELECT * FROM pedigree;
   ```

4. **繁殖馬持込区分の意味**:
   - 0:内国産 → 日本生まれ
   - 1:持込 → 海外から持ち込まれた馬
   - 2:輸入内国産扱い → 輸入馬だが内国産扱い
   - 3:輸入 → 海外生まれの輸入馬
   - 9:その他

5. **予想での活用**:
   - 父・母・母父（母の父）の3代血統分析
   - 5代まで遡って系統の血の濃さを判定
   - 産地情報による体質・適性の推測
   - 輸入馬はダート適性が高い傾向

### SK（産駒マスタ）

レコード種別ID: **SK**
レコード長: **208バイト**

**用途**: 種牡馬の産駒情報と3代血統データ（血統分析の精度向上）

```
主要カラム:
- record_id        : レコード種別ID "SK"
- data_kubun       : データ区分（0:削除, 1:新規, 2:更新）
- data_sakusei_ymd : データ作成年月日（yyyymmdd）
- kettonum         : 血統登録番号（10桁）主キー
- birth_date       : 生年月日（yyyymmdd）
- sex_cd           : 性別コード
- hinshu_cd        : 品種コード
- keiro_cd         : 毛色コード
- sanku_mochikomi_kubun : 産駒持込区分
  0:内国産
  1:持込
  2:輸入内国産扱い
  3:輸入
- yunyuu_year      : 輸入年（西暦4桁）
- seisansha_cd     : 生産者コード（8桁）
- sanchi_mei       : 産地名（全角10文字）

3代血統繁殖登録番号（14頭分、各10桁）:
- sandai_ketto[0]  : 父（Father）
- sandai_ketto[1]  : 母（Mother）
- sandai_ketto[2]  : 父父（FF）
- sandai_ketto[3]  : 父母（FM）
- sandai_ketto[4]  : 母父（MF）
- sandai_ketto[5]  : 母母（MM）
- sandai_ketto[6]  : 父父父（FFF）
- sandai_ketto[7]  : 父父母（FFM）
- sandai_ketto[8]  : 父母父（FMF）
- sandai_ketto[9]  : 父母母（FMM）
- sandai_ketto[10] : 母父父（MFF）
- sandai_ketto[11] : 母父母（MFM）
- sandai_ketto[12] : 母母父（MMF）
- sandai_ketto[13] : 母母母（MMM）
```

**主キー**: 血統登録番号（kettonum）

**外部キー関連**:
- HN（繁殖馬マスタ）へリンク（3代血統の各繁殖登録番号）
- UM（競走馬マスタ）から参照される

**重要な特記事項**:

1. **HNとの違い**:
   - **HN（繁殖馬マスタ）**: 父馬・母馬の繁殖登録番号のみ（再帰的に遡る必要）
   - **SK（産駒マスタ）**: 3代血統（14頭分）が1レコードに格納（高速アクセス可能）

2. **3代血統の構造**:
   ```
   対象馬
   ├─父（F）
   │ ├─父父（FF）
   │ │ ├─父父父（FFF）
   │ │ └─父父母（FFM）
   │ └─父母（FM）
   │   ├─父母父（FMF）
   │   └─父母母（FMM）
   └─母（M）
     ├─母父（MF）
     │ ├─母父父（MFF）
     │ └─母父母（MFM）
     └─母母（MM）
       ├─母母父（MMF）
       └─母母母（MMM）
   ```

3. **血統分析での活用**:
   ```python
   # 母父（MF: Broodmare Sire）の重要性
   # 競馬界では「母父の影響が大きい」と言われる
   mf_kettonum = sk_record["sandai_ketto"][4]  # 母父
   mf_info = get_hansyoku_info(mf_kettonum)

   # ニックス判定（相性の良い父×母父の組合せ）
   nicks_score = check_nicks(father, mother_father)

   # インブリード判定（近親交配）
   inbreeding = detect_inbreeding(sandai_ketto_list)
   ```

4. **産駒持込区分の意味**:
   - 0:内国産 → 日本で生産された馬
   - 1:持込 → 海外から持ち込まれた馬
   - 2:輸入内国産扱い → 輸入馬だが内国産扱い
   - 3:輸入 → 海外生まれの輸入馬（ダート適性高い傾向）

5. **予想での活用例**:
   - 母父がサンデーサイレンス系 → 芝・中距離適性
   - 母父がノーザンダンサー系 → ダート・短距離適性
   - インブリード（近親交配）の影響評価

### CK（出走別着度数）

レコード種別ID: **CK**
レコード長: **6870バイト**

**用途**: 各レースの出走馬ごとの詳細な累積成績データ（予想時の適性判断に最重要）

```
主要カラム:
- record_id        : レコード種別ID "CK"
- data_kubun       : データ区分（0:削除, 1:新規, 2:更新）
- data_sakusei_ymd : データ作成年月日（yyyymmdd）
- kaisai_year      : 開催年（4桁）
- kaisai_monthday  : 開催月日（4桁）
- jyocd            : 競馬場コード（2桁）
- kaisai_kai       : 開催回（2桁）
- kaisai_nichime   : 開催日目（2桁）
- race_num         : レース番号（2桁）
- kettonum         : 血統登録番号（10桁）
- bamei            : 馬名（全角18文字）

賞金情報（そのレース時点での累積）:
- heichi_honsho    : 平地本賞金累計（単位:百円）
- shogai_honsho    : 障害本賞金累計（単位:百円）
- heichi_fukasho   : 平地付加賞金累計（単位:百円）
- shogai_fukasho   : 障害付加賞金累計（単位:百円）
- heichi_shutoku   : 平地収得賞金累計（単位:百円）クラス分けの基準
- shogai_shutoku   : 障害収得賞金累計（単位:百円）

総合着回数（中央＋地方＋海外）:
- sogo_chakasuu    : 1着～5着及び着外の回数（6項目）

中央合計着回数:
- chuo_chakasuu    : 1着～5着及び着外の回数（6項目）

馬場別着回数（中央のみ）:
- shiba_choku      : 芝・直線（1-5着、着外）
- shiba_migi       : 芝・右回り（1-5着、着外）
- shiba_hidari     : 芝・左回り（1-5着、着外）
- dirt_choku       : ダート・直線（1-5着、着外）
- dirt_migi        : ダート・右回り（1-5着、着外）
- dirt_hidari      : ダート・左回り（1-5着、着外）
- shogai           : 障害（1-5着、着外）

馬場状態別着回数（中央のみ）:
- shiba_ryo/fu/ju/furyo   : 芝・良/稍重/重/不良（各6項目）
- dirt_ryo/fu/ju/furyo    : ダート・良/稍重/重/不良（各6項目）
- shogai_ryo/fu/ju/furyo  : 障害・良/稍重/重/不良（各6項目）

距離別着回数（中央のみ）:
芝（9段階）:
- shiba_1200ika      : 1200m以下
- shiba_1201_1400    : 1201-1400m
- shiba_1401_1600    : 1401-1600m
- shiba_1601_1800    : 1601-1800m
- shiba_1801_2000    : 1801-2000m
- shiba_2001_2200    : 2001-2200m
- shiba_2201_2400    : 2201-2400m
- shiba_2401_2800    : 2401-2800m
- shiba_2801ijo      : 2801m以上

ダート（9段階、同様の距離区分）

競馬場別着回数（10競馬場×3種類=30項目）:
- sapporo_shiba/dirt/shogai
- hakodate_shiba/dirt/shogai
- fukushima_shiba/dirt/shogai
- niigata_shiba/dirt/shogai
- tokyo_shiba/dirt/shogai
- nakayama_shiba/dirt/shogai
- chukyo_shiba/dirt/shogai
- kyoto_shiba/dirt/shogai
- hanshin_shiba/dirt/shogai
- kokura_shiba/dirt/shogai

脚質傾向:
- kyakushitsu_keikou : 逃げ/先行/差し/追込の各回数（4項目×3バイト=12バイト）

騎手情報:
- kishu_cd         : 騎手コード（5桁）
- kishu_mei        : 騎手名（全角17文字）
- kishu_seiseki    : 本年・累計成績（2回繰返、各1220バイト）
  - 設定年、平地/障害本賞金、付加賞金
  - 芝/ダート/障害着回数
  - 距離別着回数（芝9段階、ダート9段階）
  - 競馬場別着回数（10競馬場×3種類）

調教師情報:
- chokyoshi_cd     : 調教師コード（5桁）
- chokyoshi_mei    : 調教師名（全角17文字）
- chokyoshi_seiseki : 本年・累計成績（2回繰返、各1220バイト）
  ※騎手と同じ構造

馬主情報:
- banushi_cd       : 馬主コード（6桁）
- banushi_mei      : 馬主名（法人格有/無、各64バイト）
- banushi_seiseki  : 本年・累計成績（2回繰返、各60バイト）

生産者情報:
- seisansha_cd     : 生産者コード（8桁）
- seisansha_mei    : 生産者名（法人格有/無、各72バイト）
- seisansha_seiseki : 本年・累計成績（2回繰返、各60バイト）
```

**主キー構成**: race_id(16桁) + kettonum(10桁) = 26桁
- 各レースの各出走馬ごとに1レコード

**重要な特記事項**:

1. **SEとの関係**:
   - **SE（馬毎レース情報）**: そのレースでの結果（着順、タイム等）
   - **CK（出走別着度数）**: そのレース時点での累積成績と関係者情報
   - 両テーブルを組み合わせて予想に使用

2. **着回数データの詳細度**:
   - 各着回数は **1着～5着、着外（6着以下）の6項目** で構成
   - 馬場別（7種類）、馬場状態別（12種類）、距離別（18種類）、競馬場別（30種類）
   - 合計 **67種類の着回数データ** を保持

3. **騎手・調教師の本年/累計成績**:
   - 各2回繰り返し（本年、累計）で成績を記録
   - 距離別・競馬場別の詳細な成績も含む
   - そのレース時点での騎手・調教師の調子を判断可能

4. **脚質傾向の活用**:
   - 逃げ/先行/差し/追込の各回数をカウント
   - コース特性（逃げ馬有利/差し馬有利）との相性判断

5. **予想での活用例**:
   ```python
   # 同じ競馬場・同じ距離での過去成績
   nakayama_shiba_1600_record = check_course_record(horse, "中山", "芝", 1600)

   # 馬場状態への適性
   heavy_turf_win_rate = calculate_win_rate(horse, track="芝", condition="重")

   # 騎手との相性（騎手の得意コース×馬の得意コース）
   jockey_course_match = analyze_jockey_horse_compatibility(jockey, horse, course)

   # 脚質とコース特性のマッチング
   running_style_advantage = match_running_style_to_course(horse.kyakushitsu, course.characteristics)
   ```

6. **データ取得時の注意**:
   - レースごとに出走馬数分のレコードが存在
   - 12頭立てなら12レコード、18頭立てなら18レコード
   - 大容量データのため、必要なカラムのみを取得するのが効率的

### HR（払戻）

レコード種別ID: **HR**
レコード長: **719バイト**

**用途**: 払戻金額と的中馬番の記録（予想結果の検証・回収率計算に必須）

```
主要カラム:
- record_id        : レコード種別ID "HR"
- data_kubun       : データ区分（0:削除, 1:速報成績(払戻金確定), 2:成績(月曜), 9:レース中止）
- data_sakusei_ymd : データ作成年月日（yyyymmdd）
- kaisai_year      : 開催年（4桁）
- kaisai_monthday  : 開催月日（4桁）
- jyocd            : 競馬場コード（2桁）
- kaisai_kai       : 開催回（2桁）
- kaisai_nichime   : 開催日目（2桁）
- race_num         : レース番号（2桁）
- touroku_tosu     : 登録頭数（出馬表発表時）
- shusso_tosu      : 出走頭数（取消・除外を除く）

不成立フラグ（各馬券種）:
- fusei_tansho/fukusho/wakuren/umaren/wide/umatan/sanrenpuku/sanrentan
  （0:不成立なし, 1:不成立あり）

特払フラグ（各馬券種）:
- tokubara_tansho/fukusho/wakuren/umaren/wide/umatan/sanrenpuku/sanrentan
  （0:特払なし, 1:特払あり）
  ※特払：大量返還等で通常配当でなく特別払戻となるケース

返還フラグ（各馬券種）:
- henkan_tansho/fukusho/wakuren/umaren/wide/umatan/sanrenpuku/sanrentan
  （0:返還なし, 1:返還あり）

返還情報:
- henkan_umaban    : 返還馬番情報（28バイト、馬番01～28）
  例: 5番取消 → "0000100000000000000000000000"
- henkan_wakuban   : 返還枠番情報（8バイト、枠番1～8）
  例: 5枠のみ取消 → "00001000"
- henkan_dowaku    : 返還同枠情報（8バイト）
  例: 7枠の片方取消で7-7のみ返還 → "00000010"

払戻情報（各馬券種、同着を考慮して繰返し）:

<単勝払戻> 繰返3回:
- umaban           : 的中馬番（2桁、00:発売なし/特払/不成立）
- haraimodoshi     : 払戻金（9桁、単位:円）
- ninki_jun        : 人気順（2桁）

<複勝払戻> 繰返5回:
- umaban           : 的中馬番（2桁）
- haraimodoshi     : 払戻金（9桁）
- ninki_jun        : 人気順（2桁）

<枠連払戻> 繰返3回:
- kumiban          : 的中枠番組合（2桁、00:発売なし/特払/不成立）
- haraimodoshi     : 払戻金（9桁）
- ninki_jun        : 人気順（2桁）

<馬連払戻> 繰返3回:
- kumiban          : 的中馬番組合（4桁、0000:発売なし/特払/不成立）
- haraimodoshi     : 払戻金（9桁）
- ninki_jun        : 人気順（3桁）

<ワイド払戻> 繰返7回:
- kumiban          : 的中馬番組合（4桁）
- haraimodoshi     : 払戻金（9桁）
- ninki_jun        : 人気順（3桁）

<馬単払戻> 繰返6回:
- kumiban          : 的中馬番組合（4桁、順序あり）
- haraimodoshi     : 払戻金（9桁）
- ninki_jun        : 人気順（3桁）

<3連複払戻> 繰返3回:
- kumiban          : 的中馬番組合（6桁、000000:発売なし/特払/不成立）
- haraimodoshi     : 払戻金（9桁）
- ninki_jun        : 人気順（3桁）

<3連単払戻> 繰返6回:
- kumiban          : 的中馬番組合（6桁、順序あり）
- haraimodoshi     : 払戻金（9桁）
- ninki_jun        : 人気順（4桁）
```

**主キー構成**: race_id(16桁)
- レースごとに1レコード

**重要な特記事項**:

1. **データ区分の意味**:
   - **1:速報成績** → 払戻金確定後すぐに提供（レース当日）
   - **2:成績(月曜)** → 月曜日の確定版
   - **9:レース中止** → 悪天候等でレース自体が中止

2. **同着の扱い**:
   - 単勝: 最大3回繰返（3頭同着まで対応）
   - 複勝: 最大5回繰返（5頭同着まで対応）
   - ワイド: 最大7回繰返（多数の組合せ的中）
   - 馬単: 最大6回繰返
   - 3連単: 最大6回繰返

3. **特払（特別払戻）とは**:
   - 大量の返還馬がいる場合等、通常と異なる配当計算
   - 例: 18頭立てで15頭が取消となった場合
   - 特払フラグが立っている場合、配当額の解釈に注意

4. **返還情報の読み方**:
   ```python
   # 5番が取消の場合
   henkan_umaban = "0000100000000000000000000000"
   # インデックス4（0始まり）が"1" → 5番が返還対象

   # 7枠に7番・8番がいて、8番が取消の場合
   henkan_wakuban = "00000000"  # 7枠自体は残る
   henkan_dowaku  = "00000010"  # 7-7の同枠は返還
   ```

5. **予想結果検証での活用例**:
   ```python
   # 予想が的中したか判定
   def check_prediction_result(prediction, haraimodoshi_data):
       predicted_horses = prediction["win_prediction"]["top3"]
       actual_sanrenpuku = haraimodoshi_data["sanrenpuku_kumiban"]

       # 3連複的中判定
       is_hit = set(predicted_horses) == set(actual_sanrenpuku)

       if is_hit:
           payout = haraimodoshi_data["sanrenpuku_haraimodoshi"]
           roi = payout / prediction["investment"]
           return {"hit": True, "payout": payout, "roi": roi}
       return {"hit": False}

   # 回収率計算
   def calculate_recovery_rate(predictions, results):
       total_investment = sum(p["amount"] for p in predictions)
       total_return = sum(check_hit_and_payout(p, results) for p in predictions)
       recovery_rate = total_return / total_investment * 100
       return recovery_rate
   ```

6. **人気順との比較分析**:
   - 人気順と実際の結果を比較
   - 本命が外れるパターン（大荒れ）の検出
   - 穴馬の的中率分析

7. **オッズとの関係**:
   - OD（オッズ）テーブルの最終オッズと払戻金額を比較
   - 理論配当と実際配当の差異分析（控除率の確認）

### YS（開催スケジュール）

レコード種別ID: **YS**
レコード長: **382バイト**

**用途**: 開催スケジュールと重賞レース情報（年間予定、重賞レース詳細の把握）

```
主要カラム:
- record_id        : レコード種別ID "YS"
- data_kubun       : データ区分
  1:開催予定(年末時点)
  2:開催予定(開催直前時点)
  3:開催終了(成績確定時点)
  9:開催中止
- kaisai_year      : 開催年（4桁）
- kaisai_monthday  : 開催月日（4桁）
- jyocd            : 競馬場コード（2桁）
- kaisai_kai       : 開催回（2桁）
- kaisai_nichime   : 開催日目（2桁）
- youbi_cd         : 曜日コード

重賞案内（3回繰返）:
- tokubetsu_kyoso_num : 特別競走番号（4桁）重賞レースのみ設定
- kyoso_hondai        : 競走名本題（全角30文字）
- kyoso_ryaku_10/6/3  : 競走名略称10/6/3文字
- jusho_kaiji         : 重賞回次[第N回]（3桁）通算回数
- grade_cd            : グレードコード（G1/G2/G3/Jpn等）
- kyoso_shubetsu_cd   : 競走種別コード
- kyoso_kigo_cd       : 競走記号コード
- juryo_shubetsu_cd   : 重量種別コード
- kyori               : 距離（単位:メートル）
- track_cd            : トラックコード
```

**主キー構成**: kaisai_year + kaisai_monthday + jyocd + kaisai_kai + kaisai_nichime

**重要な特記事項**:

1. **データ区分の遷移**:
   - 年末時点（1）: 翌年の年間スケジュール発表
   - 開催直前（2）: 直前の最終確定情報
   - 開催終了（3）: 成績確定時点
   - 開催中止（9）: 悪天候等で中止

2. **重賞案内の活用**:
   - 1開催日に最大3レースの重賞情報を格納
   - G1レースの日程把握
   - 特別競走番号で過去の同一レースを追跡可能

3. **スケジューラーでの活用**:
   - 今後の開催予定を取得してスケジュール管理
   - 重賞レース前に特別な予想処理を実行

### WE（天候馬場状態）

レコード種別ID: **WE**
レコード長: **42バイト**

**用途**: 天候・馬場状態の変化追跡（リアルタイム予想の精度向上に最重要）

```
主要カラム:
- record_id        : レコード種別ID "WE"
- data_kubun       : データ区分（1:初期値）
- kaisai_year      : 開催年（4桁）
- kaisai_monthday  : 開催月日（4桁）
- jyocd            : 競馬場コード（2桁）
- kaisai_kai       : 開催回（2桁）
- kaisai_nichime   : 開催日目（2桁）
- happyo_tsukihi_jifun : 発表月日時分（8桁、mmddHHMM）
- henkou_shikibetsu    : 変更識別
  1:天候馬場初期状態（天候・馬場とも有効値）
  2:天候変更（天候のみ有効値、馬場は初期値）
  3:馬場状態変更（馬場のみ有効値、天候は初期値）

現在状態情報:
- tenko_jotai      : 天候状態（晴/曇/雨/雪等）
- baba_jotai_shiba : 馬場状態・芝（良/稍重/重/不良）
- baba_jotai_dirt  : 馬場状態・ダート（良/稍重/重/不良）

変更前状態情報:
- tenko_jotai_mae     : 変更前 天候状態
- baba_jotai_shiba_mae : 変更前 馬場状態・芝
- baba_jotai_dirt_mae  : 変更前 馬場状態・ダート
```

**主キー構成**: race_date(8桁) + jyocd(2桁) + kaisai_kai(2桁) + kaisai_nichime(2桁) + happyo_tsukihi_jifun(8桁) + henkou_shikibetsu(1桁)

**重要な特記事項**:

1. **リアルタイム追跡の重要性**:
   - 開催中に天候・馬場状態が変化する場合がある
   - 「良→稍重→重」と悪化すると予想が大きく変わる
   - 馬場状態による適性判断が予想精度の鍵

2. **予想への影響**:
   ```python
   # 馬場状態悪化時の再予想判定
   if current_baba != initial_baba:
       # 重馬場・不良馬場での成績が良い馬を優遇
       adjust_prediction_for_heavy_track(horses, current_baba)
   ```

3. **CK（出走別着度数）との連携**:
   - CKテーブルの馬場状態別着回数と照合
   - 現在の馬場状態での各馬の適性を判断

### AV（出走取消・競走除外）

レコード種別ID: **AV**
レコード長: **78バイト**

**用途**: 出走取消・競走除外の記録（HR払戻の返還情報と連動）

```
主要カラム:
- record_id        : レコード種別ID "AV"
- data_kubun       : データ区分（1:出走取消, 2:競走除外）
- kaisai_year～race_num : レース識別情報
- happyo_tsukihi_jifun : 発表月日時分（8桁）
- umaban           : 該当馬番（01～18）
- bamei            : 馬名（全角18文字）
- jiyu_kubun       : 事由区分
  000:初期値
  001:疾病
  002:事故
  003:その他
```

**重要な特記事項**:

1. **出走取消と競走除外の違い**:
   - **出走取消**: 発売後に取消（返還対象となる）
   - **競走除外**: レース中の事故等で除外

2. **HR（払戻）との連携**:
   - AV（出走取消）→ HR（返還フラグ、返還馬番情報）
   - 取消馬を含む馬券は返還処理

### JC（騎手変更）

レコード種別ID: **JC**
レコード長: **161バイト**

**用途**: 騎手変更の追跡（予想の再評価に影響）

```
主要カラム:
- record_id        : レコード種別ID "JC"
- kaisai_year～race_num : レース識別情報
- happyo_tsukihi_jifun : 発表月日時分（8桁）
- umaban           : 該当馬番（01～18）
- bamei            : 馬名

変更後情報:
- futan_juryo      : 負担重量（単位:0.1kg）
- kishu_cd         : 騎手コード（未定の場合はALL0）
- kishu_mei        : 騎手名（未定の場合は"未定"）
- kishu_minarai_cd : 騎手見習コード

変更前情報:
- futan_juryo_mae  : 変更前 負担重量
- kishu_cd_mae     : 変更前 騎手コード
- kishu_mei_mae    : 変更前 騎手名
- kishu_minarai_cd_mae : 変更前 騎手見習コード
```

**重要な特記事項**:

1. **予想への影響**:
   - 主戦騎手から乗り替わりの場合、評価を下げる
   - 騎手とコースの相性を再評価
   - CK（出走別着度数）の騎手成績を参照

2. **負担重量の変更**:
   - 騎手変更に伴い負担重量も変わる場合がある
   - 見習騎手への変更で減量（▲△☆）

### TC（発走時刻変更）

レコード種別ID: **TC**
レコード長: **45バイト**

**用途**: 発走時刻変更の記録（スケジューラー調整）

```
主要カラム:
- record_id        : レコード種別ID "TC"
- kaisai_year～race_num : レース識別情報
- happyo_tsukihi_jifun : 発表月日時分（8桁）

変更後情報:
- henkou_go_hassou_jikoku : 変更後 発走時刻（hhmm）

変更前情報:
- henkou_mae_hassou_jikoku : 変更前 発走時刻（hhmm）
```

**重要な特記事項**:

1. **スケジューラーへの影響**:
   - 「レース1時間前の最終予想」タイミングを再計算
   - 発走時刻変更を検知して予想タイミングを調整

### CC（コース変更）

レコード種別ID: **CC**
レコード長: **50バイト**

**用途**: コース変更の記録（馬場状態悪化時の距離・トラック変更）

```
主要カラム:
- record_id        : レコード種別ID "CC"
- kaisai_year～race_num : レース識別情報
- happyo_tsukihi_jifun : 発表月日時分（8桁）

変更後情報:
- henkou_go_kyori  : 変更後 距離（単位:メートル）
- henkou_go_track  : 変更後 トラックコード

変更前情報:
- henkou_mae_kyori : 変更前 距離
- henkou_mae_track : 変更前 トラックコード

- jiyu_kubun       : 事由区分
  1:強風
  2:台風
  3:雪
  4:その他
```

**重要な特記事項**:

1. **コース変更の影響**:
   - 芝→ダートへの変更（馬場状態悪化）
   - 距離短縮（悪天候時）
   - 予想の全面的な見直しが必要

2. **予想への影響**:
   ```python
   # コース変更検知時の処理
   if course_changed:
       # 変更後のコースでの過去成績を再取得
       new_course_record = get_course_record(horse, new_track, new_distance)
       # 予想を再実行
       re_predict(race, new_course_record)
   ```

### RC（レコードマスタ）

レコード種別ID: **RC**
レコード長: **501バイト**

**用途**: コースレコードとG1レコードの管理（タイム評価の基準）

```
主要カラム:
- record_id        : レコード種別ID "RC"
- data_kubun       : データ区分（1:初期値, 0:削除）
- data_sakusei_ymd : データ作成年月日（yyyymmdd）
- record_shikibetsu_kubun : レコード識別区分
  1:コースレコード（競馬場×距離×トラックごとの最速記録）
  2:G1レコード（G1レースごとの最速記録）
- kaisai_year      : 開催年（4桁）
- kaisai_monthday  : 開催月日（4桁）
- jyocd            : 競馬場コード（2桁）
- kaisai_kai       : 開催回（2桁）
- kaisai_nichime   : 開催日目（2桁）
- race_num         : レース番号（2桁）
- tokubetsu_kyoso_num : 特別競走番号（4桁）G1レコードのみ
- kyoso_hondai     : 競走名本題（全角30文字）
- grade_cd         : グレードコード
- kyoso_shubetsu_cd : 競走種別コード
- kyori            : 距離（単位:メートル）
- track_cd         : トラックコード

レコード情報:
- record_kubun     : レコード区分
  1:基準タイム（その条件での標準タイム）
  2:レコードタイム（最速記録）
  3:参考タイム
  4:備考タイム
- record_time      : レコードタイム（9分99秒9、単位:0.1秒）
- tenko_cd         : 天候コード（レコード達成時）
- shiba_baba_cd    : 芝馬場状態コード
- dirt_baba_cd     : ダート馬場状態コード

レコード保持馬情報（3回繰返、同着考慮）:
- kettonum         : 血統登録番号（10桁）
- bamei            : 馬名（全角18文字）
- kigou_cd         : 馬記号コード
- sex_cd           : 性別コード
- chokyoshi_cd     : 調教師コード（5桁）
- chokyoshi_mei    : 調教師名（全角17文字）
- futan_juryo      : 負担重量（単位:0.1kg）
- kishu_cd         : 騎手コード（5桁）
- kishu_mei        : 騎手名（全角17文字）
```

**主キー構成**:
- コースレコード: record_shikibetsu(1) + jyocd + kyoso_shubetsu + kyori + track_cd
- G1レコード: record_shikibetsu(2) + tokubetsu_kyoso_num

**重要な特記事項**:

1. **コースレコードとG1レコードの違い**:
   - **コースレコード**: 競馬場・距離・トラックの組合せごとの最速記録
     - 例: 東京芝1600mのコースレコード → 1:31.3
   - **G1レコード**: 特定のG1レースでの最速記録
     - 例: 日本ダービー（東京芝2400m）のレコード → 2:23.0

2. **レコード区分の意味**:
   - **1:基準タイム**: その条件での標準的なタイム
   - **2:レコードタイム**: 最速記録（これが本来のレコード）
   - **3:参考タイム**: 参考情報
   - **4:備考タイム**: その他の備考

3. **タイム評価での活用**:
   ```python
   # レースタイムがレコードに近いかを評価
   course_record = get_course_record(venue, distance, track)
   race_time = get_race_time(race_id)

   time_diff = race_time - course_record
   if time_diff < 5:  # 0.5秒差以内
       evaluation = "レコードに迫る好タイム"
   elif time_diff < 10:  # 1.0秒差以内
       evaluation = "レコード級の好タイム"
   else:
       evaluation = f"レコードから{time_diff/10:.1f}秒遅い"
   ```

4. **馬場状態の考慮**:
   - レコードは通常「良馬場」で出る
   - 稍重・重・不良では基準タイムを緩和する必要
   ```python
   # 馬場状態による補正
   if baba_jotai == "良":
       base_time = record_time
   elif baba_jotai == "稍重":
       base_time = record_time + 5  # +0.5秒
   elif baba_jotai == "重":
       base_time = record_time + 10  # +1.0秒
   elif baba_jotai == "不良":
       base_time = record_time + 20  # +2.0秒
   ```

5. **予想での活用例**:
   - 前走でレコードに迫る好タイムを出した馬を高評価
   - コースレコード保持馬の適性分析
   - LLMプロンプトに「前走は東京芝1600mでレコードから0.3秒差の好タイム」と記載

6. **レコード保持馬の複数記録**:
   - 同着の場合、最大3頭までレコード保持馬を記録
   - 騎手・調教師情報も含まれるため、レコード達成時の陣容が分かる

### O1～O6（オッズ）

**用途**: 各馬券種のオッズ情報（人気度の把握、期待値計算、オッズ推移分析）

#### O1（オッズ1: 単勝・複勝・枠連）

レコード種別ID: **O1**
レコード長: **962バイト**

```
主要カラム:
- record_id        : レコード種別ID "O1"
- data_kubun       : データ区分
  1:中間オッズ
  2:前日売最終
  3:最終オッズ
  4:確定オッズ
  5:確定(月曜)
  9:レース中止
- happyo_tsukihi_jifun : 発表月日時分（8桁、中間オッズのみ）
- touroku_tosu     : 登録頭数
- shusso_tosu      : 出走頭数
- hatsubai_flag_tansho/fukusho/wakuren : 発売フラグ
  0:発売なし, 1:発売前取消, 3:発売後取消, 7:発売あり

単勝オッズ（28頭分、馬番昇順01～28）:
- umaban           : 馬番（2桁）
- odds             : オッズ（999.9倍、4桁）
  9999:999.9倍以上, 0000:無投票, ----:発売前取消, ****:発売後取消
- ninki_jun        : 人気順（2桁）

複勝オッズ（28頭分、馬番昇順01～28）:
- umaban           : 馬番（2桁）
- saitei_odds      : 最低オッズ（999.9倍、4桁）
- saikou_odds      : 最高オッズ（999.9倍、4桁）
- ninki_jun        : 人気順（2桁）

枠連オッズ（36組、組番昇順1-1～8-8）:
- kumiban          : 組番（2桁）
- odds             : オッズ（9999.9倍、5桁）
- ninki_jun        : 人気順（2桁）

票数合計:
- tansho_hyosu     : 単勝票数合計（単位:百円、11桁）
- fukusho_hyosu    : 複勝票数合計
- wakuren_hyosu    : 枠連票数合計
```

#### O2（オッズ2: 馬連）

レコード種別ID: **O2**
レコード長: **2042バイト**

```
馬連オッズ（153組、組番昇順01-02～17-18）:
- kumiban          : 組番（4桁、例: 0103）
- odds             : オッズ（99999.9倍、6桁）
- ninki_jun        : 人気順（3桁）
```

#### O3（オッズ3: ワイド）

レコード種別ID: **O3**
レコード長: **2654バイト**

```
ワイドオッズ（153組、組番昇順01-02～17-18）:
- kumiban          : 組番（4桁）
- saitei_odds      : 最低オッズ（9999.9倍、5桁）
- saikou_odds      : 最高オッズ（9999.9倍、5桁）
- ninki_jun        : 人気順（3桁）
```

#### O4（オッズ4: 馬単）

レコード種別ID: **O4**
レコード長: **4031バイト**

```
馬単オッズ（306組、組番昇順01-02～18-17）:
- kumiban          : 組番（4桁、順序あり）
- odds             : オッズ（99999.9倍、6桁）
- ninki_jun        : 人気順（3桁）
```

#### O5（オッズ5: 3連複）

レコード種別ID: **O5**
レコード長: **12293バイト**

```
3連複オッズ（816組、組番昇順01-02-03～16-17-18）:
- kumiban          : 組番（6桁、例: 010203）
- odds             : オッズ（99999.9倍、6桁）
- ninki_jun        : 人気順（3桁）
```

#### O6（オッズ6: 3連単）

レコード種別ID: **O6**
レコード長: **83285バイト**（最大容量）

```
3連単オッズ（4896組、組番昇順01-02-03～18-17-16）:
- kumiban          : 組番（6桁、順序あり）
- odds             : オッズ（999999.9倍、7桁）
- ninki_jun        : 人気順（4桁）
```

**主キー構成**: race_id(16桁) + happyo_tsukihi_jifun(8桁、中間オッズのみ)
- 最終オッズは発表時分なし

**重要な特記事項**:

1. **データ区分の遷移**:
   - **1:中間オッズ** → レース当日、複数回更新（発表月日時分で区別）
   - **2:前日売最終** → 前日の発売終了時点
   - **3:最終オッズ** → 発走直前の最終オッズ（最重要）
   - **4:確定オッズ** → レース終了後の確定版
   - **5:確定(月曜)** → 月曜日の最終確定版

2. **人気度の把握**:
   ```python
   # 単勝1番人気の馬番を取得
   tansho_odds = get_tansho_odds(race_id, data_kubun=3)  # 最終オッズ
   ninki_1 = [o["umaban"] for o in tansho_odds if o["ninki_jun"] == 1][0]

   # LLMプロンプトに含める
   prompt += f"単勝1番人気は{ninki_1}番（オッズ{odds}倍）"
   ```

3. **期待値計算**:
   ```python
   # 予想の期待値を計算
   predicted_horse = 3
   odds = get_tansho_odds(race_id, predicted_horse)
   confidence = 0.3  # 予想の信頼度（30%の勝率）
   expected_value = odds * confidence

   if expected_value > 1.0:
       evaluation = "期待値プラス"
   ```

4. **オッズ推移分析**:
   - 中間オッズから最終オッズへの変化を追跡
   - 人気が急上昇/急降下した馬の検出
   ```python
   # オッズ推移の検出
   chukan_odds = get_odds(race_id, data_kubun=1, latest=True)
   saishuu_odds = get_odds(race_id, data_kubun=3)

   for uma in range(1, 19):
       if chukan_odds[uma] > saishuu_odds[uma] * 1.5:
           # オッズが1.5倍以上下がった = 人気急上昇
           alert(f"{uma}番が人気急上昇")
   ```

5. **予想での活用例**:
   - 単勝1番人気の馬を本命として扱う
   - オッズから期待配当を計算して馬券戦略を立てる
   - 人気薄（10番人気以下）の穴馬を検出
   - LLMプロンプトに「3番は単勝2番人気（オッズ4.5倍）」と記載

6. **データサイズの考慮**:
   - O6（3連単）は83KBと大容量
   - 必要なデータ区分（最終オッズ）のみを取得
   - 中間オッズは時系列分析が必要な場合のみ

### CS（コース情報）

レコード種別ID: **CS**
レコード長: **6829バイト**

**用途**: 競馬場ごとのコース特性と改修履歴（コース特性の理解と改修前後の傾向変化分析）

```
主要カラム:
- record_id        : レコード種別ID "CS"
- data_kubun       : データ区分（0:削除, 1:新規, 2:更新）
- data_sakusei_ymd : データ作成年月日（yyyymmdd）
- jyocd            : 競馬場コード（2桁）
- kyori            : 距離（4桁、単位:メートル）
- track_cd         : トラックコード（2桁）芝/ダート/障害
- kaishu_ymd       : コース改修年月日（yyyymmdd）コース改修後、最初に行われた開催日
- course_setumei   : コース説明（6800バイト）テキスト文
```

**主キー構成**: 競馬場コード + 距離 + トラックコード + コース改修年月日

**重要な特記事項**:

1. **コース改修年月日の重要性**:
   - コース改修前後で馬場特性が大きく変わる可能性がある
   - 改修前のデータと改修後のデータを分けて扱う必要がある
   - 予想時は現在のコース状態（最新の改修日以降）のデータを使用すべき

2. **コース説明の活用**:
   - 6800バイトの大容量テキストフィールド
   - コースの形状、高低差、直線の長さ、コーナーの特徴などが記載
   - LLMプロンプトに含めることでコース適性の推論に使用

3. **予想での活用例**:
   - 東京競馬場芝1600m → 直線が長く差し・追込有利
   - 中山競馬場芝2000m → 急坂があり先行有利
   - 阪神競馬場ダート1800m → 内枠有利な傾向
   - コース説明テキストをLLMに渡して脚質・枠順適性を判断

4. **データ活用時の注意**:
   - 同じ競馬場・距離でも改修により複数レコードが存在する
   - 予想対象レースの開催日に対応する改修バージョンを取得する必要がある
   - クエリ例: `WHERE kaishu_ymd <= race_date ORDER BY kaishu_ymd DESC LIMIT 1`

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

### 日本国内（JRA中央競馬）

```
01: 札幌 (Sapporo)
02: 函館 (Hakodate)
03: 福島 (Fukushima)
04: 新潟 (Niigata)
05: 東京 (Tokyo)
06: 中山 (Nakayama)
07: 中京 (Chukyo)
08: 京都 (Kyoto)
09: 阪神 (Hanshin)
10: 小倉 (Kokura)
```

### 海外主要国（外国馬・国際G1レース用）

**北米・南米**:
```
A0: アメリカ (United States) USA
A8: カナダ (Canada) CAN
E2: アルゼンチン (Argentina) ARG
E4: ブラジル (Brazil) BRZ
E6: ベルギー (Belgium) BEL
F2: チリ (Chile) CHI
J6: メキシコ (Mexico) MEX
```

**ヨーロッパ**:
```
B0: イギリス (United Kingdom) GB
B2: フランス (France) FRA
B4: アイルランド (Ireland) IRE
B6: ニュージーランド (New Zealand) NZ
C0: イタリア (Italy) ITY
C2: ドイツ (Germany) GER
D0: スウェーデン (Sweden) SWE
D2: ハンガリー (Hungary) HUN
D4: ポルトガル (Portugal) POR
G2: スペイン (Spain) SPA
H4: スイス (Switzerland) SWI
```

**オセアニア**:
```
A2: オーストラリア (Australia) AUS
B6: ニュージーランド (New Zealand) NZ
```

**アジア・中東**:
```
F0: 韓国 (Korea) KOR
F1: 中国 (China) CHN
G0: 香港 (Hong Kong) HK
K6: サウジアラビア (Saudi Arabia) SDA
M0: シンガポール (Singapore) SIN
M2: マカオ (Macau) MAC
C7: アラブ首長国連邦 (UAE) UAE
L0: タイ (Thailand) THA
J4: マレーシア (Malaysia) MAL
```

**その他**:
```
H2: 南アフリカ (South Africa) SAF
E8: トルコ (Turkey) TUR
D6: ロシア (Russia) RUS
```

### 活用例

```python
# 外国馬の海外G1実績を評価
if horse.past_races.country_cd == "B0":  # イギリス
    if horse.past_races.grade_cd == "A":  # G1勝ち
        evaluation = "英G1馬（芝適性高）"
elif horse.past_races.country_cd == "A0":  # アメリカ
    if horse.past_races.grade_cd == "A":
        evaluation = "米G1馬（ダート適性高）"
elif horse.past_races.country_cd == "G0":  # 香港
    if horse.past_races.grade_cd == "A":
        evaluation = "香港G1馬（高速芝適性）"

# LLMプロンプトに含める
prompt += f"過去に{evaluation}の実績あり"
```

### 海外成績の重要性

1. **香港G1勝ち馬**: 高速芝の短距離～マイル戦に強い傾向
2. **英愛G1勝ち馬**: 芝の中長距離に強い、日本の芝にも適応しやすい
3. **米G1勝ち馬**: ダート適性が非常に高い
4. **仏G1勝ち馬**: 芝の中長距離、凱旋門賞などの実績は高評価
5. **豪G1勝ち馬**: 芝の中距離～長距離、メルボルンカップなど

### 注意事項

- 海外レースの競馬場コードは国コード（地域全体を代表）
- 具体的な競馬場名（例: シャンティイ、ロンシャン）は含まれない
- 海外成績データは限定的（JRA出走馬の主要G1のみ）

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

### 📘 公式仕様書（必読）

**JV-Data仕様書 Ver.4.9.0.1** - 全データ種別の詳細仕様
- [PDF版](https://jra-van.jp/dlb/sdv/sdk/JV-Data4901.pdf) ⭐ **最も重要**
- [Excel版](https://jra-van.jp/dlb/sdv/sdk/JV-Data4901.xlsx)

この仕様書には以下が記載されています：
- 全データ種別（RA, SE, HC, WC, O1-O6等）のレコードフォーマット
- 各フィールドの位置、バイト数、データ型
- コード値の定義（競馬場コード、馬場状態コード等）
- データ更新タイミング

### その他の公式資料

- [JV-Linkインターフェース仕様書](https://jra-van.jp/dlb/sdv/sdk/JV-Link4901.pdf) - データ取得APIの仕様
- [JRA-VAN Data Lab.開発ガイド](https://jra-van.jp/dlb/sdv/sdk/DataLab422.pdf) - 開発全般のガイド

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
