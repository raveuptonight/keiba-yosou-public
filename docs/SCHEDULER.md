# 自動予想スケジューラー仕様

## 概要

Discord Botが自動的に予想を実行し、通知するスケジューラー機能です。

**2つの予想タイミング**:
1. **開催日の朝9時**: 当日全レースの初回予想
2. **レース1時間前**: 馬体重発表後の最終予想

---

## 動作仕様

### 1. 朝9時の初回予想

毎日9時（設定可変）に当日開催レースを自動予想します。

**処理フロー**:
```
1. 当日のレース一覧を取得（APIから）
2. 各レースについて予想実行
3. 予想完了通知をDiscordチャンネルに送信
4. 予想済みレースIDを記録（重複実行防止）
```

**通知例**:
```
🌅 おはようございます！本日は12レースの予想を開始します。

🏇 【予想完了】中山金杯
📅 2024/12/28 (日) 15:25 中山11R
◎本命: 3番 ディープボンド
○対抗: 7番 エフフォーリア
...
✅ 本日の初回予想が完了しました！
```

### 2. レース1時間前の最終予想

各レース発走の1時間前に、馬体重を反映した最終予想を実行します。

**処理フロー**:
```
1. 10分ごとにレース一覧をチェック
2. レース発走1時間前（±5分）を検出
3. 最終予想を実行
4. 「🔥 最終予想」マーク付きで通知
5. 予想済みレースIDを記録
```

**通知例**:
```
🐴 馬体重発表！中山金杯の最終予想を実行します。

🔥 【最終予想】馬体重反映済み

🏇 【予想完了】中山金杯
...
```

---

## 設定

### 環境変数（.env）

```bash
# Discord通知先チャンネルID
DISCORD_CHANNEL_ID=1234567890123456789

# API Base URL
API_BASE_URL=http://localhost:8000
```

### src/config.py

```python
# 自動予想スケジューラー設定
SCHEDULER_MORNING_PREDICTION_HOUR: Final[int] = 9  # 朝予想の実行時刻（時）
SCHEDULER_MORNING_PREDICTION_MINUTE: Final[int] = 0  # 朝予想の実行時刻（分）
SCHEDULER_CHECK_INTERVAL_MINUTES: Final[int] = 10  # レース時刻チェック間隔（分）
SCHEDULER_FINAL_PREDICTION_HOURS_BEFORE: Final[int] = 1  # 最終予想のタイミング（レース何時間前）
SCHEDULER_FINAL_PREDICTION_TOLERANCE_MINUTES: Final[int] = 5  # 最終予想の時刻許容範囲（分）
```

---

## 管理コマンド

### スケジューラーステータス確認

```
!scheduler-status
```

**出力例**:
```
⚙️ 自動予想スケジューラーステータス

朝9時予想タスク: 🟢 実行中
次回実行: 2024-12-29 09:00:00
本日予想済み: 12レース

レースチェックタスク: 🟢 実行中
最終予想済み: 8レース

通知チャンネルID: 1234567890123456789
```

### スケジューラーリセット

```
!scheduler-reset
```

予想済みレース記録をクリアします（開発・テスト用）。

---

## タイムライン例

### 土曜日の動作例（中山・阪神開催）

```
09:00 🌅 朝9時予想開始
09:01   中山1R予想完了
09:03   中山2R予想完了
...
09:22   阪神12R予想完了
09:23 ✅ 本日の初回予想完了（24レース）

09:05 ⏰ レースチェックタスク開始（10分間隔）
09:15 ⏰ レースチェック
...

09:50 🐴 馬体重発表！中山1R最終予想実行
10:50 🐴 馬体重発表！中山2R最終予想実行
...
```

---

## 実装詳細

### ファイル構成

```
src/discord/
├── scheduler.py        # スケジューラー本体
├── bot.py              # Botメイン（schedulerをロード）
├── commands.py         # 手動コマンド
└── formatters.py       # 通知メッセージフォーマット
```

### クラス構成

```python
class PredictionScheduler(commands.Cog):
    """自動予想スケジューラー"""

    # タスク
    @tasks.loop(time=time(hour=9, minute=0))
    async def morning_prediction_task(self):
        """毎朝9時の予想"""

    @tasks.loop(minutes=10)
    async def hourly_check_task(self):
        """レース時刻チェック"""

    # 管理コマンド
    @commands.command(name="scheduler-status")
    async def scheduler_status(self, ctx):
        """ステータス確認"""

    @commands.command(name="scheduler-reset")
    async def scheduler_reset(self, ctx):
        """リセット"""
```

### 重複実行防止

```python
# 予想済みレースIDをセットで管理
self.predicted_race_ids_morning: set = set()  # 朝9時予想済み
self.predicted_race_ids_final: set = set()    # 馬体重後予想済み
```

- 朝9時予想と最終予想は別々に記録
- 同じレースIDの重複実行を防止
- 日付変更時は自動的にクリア（TODO: 実装予定）

---

## レート制限対策

### API呼び出し間隔

```python
# 各レース予想の間に2秒待機
await asyncio.sleep(2)
```

朝9時に12レース予想する場合、約24秒かかります（レート制限回避）。

---

## エラーハンドリング

### 想定エラー

1. **APIサーバー停止**
   - ログ出力、スキップして次回再試行

2. **レース一覧取得失敗**
   - ログ出力、次回チェック時に再試行

3. **予想実行タイムアウト**
   - 5分（DISCORD_REQUEST_TIMEOUT）でタイムアウト
   - エラーログ記録、次レースへ進む

4. **Discord通知失敗**
   - ログ出力、予想自体は実行済み

---

## 今後の改善予定

- [ ] 日付変更時の予想済みレースIDクリア
- [ ] レース一覧取得APIエンドポイント実装
- [ ] 予想失敗時のリトライ機構
- [ ] 統計情報の自動送信（週次・月次）
- [ ] 馬体重発表時刻の正確な取得
- [ ] 発走直前の最終オッズ反映予想（オプション）

---

## トラブルシューティング

### Q: スケジューラーが起動しない

A: 以下を確認してください：
1. `DISCORD_CHANNEL_ID`が正しく設定されているか
2. Bot起動時にエラーログが出ていないか
3. `!scheduler-status`で状態確認

### Q: 朝9時に予想が実行されない

A: 以下を確認してください：
1. タイムゾーンが正しいか（Botサーバーの時刻）
2. APIサーバーが起動しているか
3. レース一覧APIが正しく動作しているか

### Q: 予想が重複実行される

A: `!scheduler-reset`でリセットしてください。

---

## 開発メモ

### テスト方法

1. **朝9時タスクのテスト**:
   ```python
   # config.pyで時刻を現在時刻+1分に設定
   SCHEDULER_MORNING_PREDICTION_HOUR = 14  # 14:01実行
   SCHEDULER_MORNING_PREDICTION_MINUTE = 1
   ```

2. **レースチェックタスクのテスト**:
   ```python
   # 間隔を短縮
   SCHEDULER_CHECK_INTERVAL_MINUTES = 1  # 1分ごと
   ```

3. **手動実行（開発用）**:
   ```python
   # scheduler.pyで直接メソッド呼び出し
   await self.morning_prediction_task()
   ```

---

## ライセンス

本プロジェクトと同じライセンスに従います。
