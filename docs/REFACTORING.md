# リファクタリング履歴

このドキュメントでは、プロジェクトに対して行われたリファクタリングを記録します。

---

## 2024-12-28: Discord Commands 分割とエラーハンドリング共通化

### 概要

Discord Bot のコマンド処理を保守性向上のためリファクタリングしました。

### 変更内容

#### 1. エラーハンドリングの共通化

**作成ファイル**: `src/discord/decorators.py`

**目的**:
- API呼び出しで発生する共通エラー（タイムアウト、接続エラーなど）のハンドリングを一元化
- コード重複を削減
- エラーメッセージの一貫性を確保

**実装**:
```python
@handle_api_errors  # デコレーターでエラーハンドリング
@log_command_execution  # ログ記録も自動化
async def predict_race(self, ctx, race_spec: str):
    # 本質的なロジックのみ記述
    # try-except が不要に
```

**効果**:
- 各コマンドのtry-except ブロックが不要に
- エラーハンドリングロジックの変更が1箇所で済む
- コードが読みやすく、テストしやすくなった

---

#### 2. Discord Commands の分割

**変更前**:
```
src/discord/
├── commands.py  # 447行、4つのCogクラスが混在
```

**変更後**:
```
src/discord/
├── commands/
│   ├── __init__.py       # Cog一括登録
│   ├── prediction.py     # PredictionCommands (予想関連)
│   ├── stats.py          # StatsCommands (統計関連)
│   ├── betting.py        # BettingCommands (馬券購入推奨)
│   └── help.py           # HelpCommands (ヘルプ)
└── decorators.py         # エラーハンドリングデコレーター
```

**詳細**:

| ファイル | Cogクラス | コマンド | 行数 |
|---------|---------|---------|------|
| `prediction.py` | PredictionCommands | `!predict`, `!today` | ~165行 |
| `stats.py` | StatsCommands | `!stats`, `!roi` | ~105行 |
| `betting.py` | BettingCommands | `!baken` | ~140行 |
| `help.py` | HelpCommands | `!help` | ~60行 |

**メリット**:
1. **関心の分離**: 各ファイルが単一の責任を持つ
2. **拡張性**: 新しいコマンド追加が容易
3. **テスト容易性**: 各Cogを独立してテスト可能
4. **可読性**: ファイルサイズが適切（60-165行）

---

### 移行手順

#### bot.py の変更

**変更前**:
```python
await self.load_extension("src.discord.commands")
```

**変更後**:
```python
# 変更なし（内部で4つのCogを自動ロード）
await self.load_extension("src.discord.commands")
```

`src/discord/commands/__init__.py` が自動的に4つのCogをロードするため、bot.pyの変更は最小限。

---

### 互換性

- **破壊的変更なし**: コマンド名、引数、動作は完全に同一
- **ユーザー影響なし**: Discord上のコマンド使用方法は変更なし
- **デプロイ**: 単純にファイルを置き換えるだけで動作

---

### テスト

#### 構文チェック
```bash
python3 -m py_compile src/discord/decorators.py \
                       src/discord/commands/__init__.py \
                       src/discord/commands/prediction.py \
                       src/discord/commands/stats.py \
                       src/discord/commands/betting.py \
                       src/discord/commands/help.py \
                       src/discord/bot.py
```

✅ 構文エラーなし

#### 動作確認（推奨）
```bash
# ローカルで起動テスト
python -m src.discord.bot

# EC2で再起動
sudo systemctl restart keiba-discord-bot
sudo journalctl -u keiba-discord-bot -f

# Discordで各コマンド実行
!help
!today
!predict 中山1R
!stats
!baken 中山1R 10000 3連複
```

---

### バックアップ

元のファイルは保存されています:
- `src/discord/commands.py.backup` - 分割前の447行ファイル

必要に応じて復元可能:
```bash
mv src/discord/commands.py.backup src/discord/commands.py
rm -rf src/discord/commands/  # 新ディレクトリ削除
```

---

### 今後の改善提案

1. **プロンプト生成の切り出し** （次の優先課題）
   - `src/services/claude_client.py` のプロンプト生成ロジックを分離
   - `src/prompts/` ディレクトリに移動
   - テスタビリティとプロンプト改善の容易性を向上

2. **API クライアントの抽象化**
   - requests 呼び出しを `src/services/api_client.py` に集約
   - モック化が容易になりテストしやすくなる

3. **コマンド結果のキャッシュ**
   - `!today` の結果を一定時間キャッシュ
   - API呼び出し回数を削減

---

## 参考資料

- **Discord.py 公式**: https://discordpy.readthedocs.io/
- **Cog設計パターン**: https://discordpy.readthedocs.io/en/stable/ext/commands/cogs.html
- **Pythonデコレーター**: https://docs.python.org/ja/3/glossary.html#term-decorator

---

**リファクタリング完了日**: 2024-12-28
**影響範囲**: Discord Bot コマンド処理のみ（API、DB、予想ロジックは無変更）
**動作確認**: 構文チェック済み（実環境テスト推奨）
