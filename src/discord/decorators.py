"""
Discord コマンド用デコレーター

API呼び出しのエラーハンドリングなど、共通処理を提供
"""

import logging
from functools import wraps
from typing import Callable
import requests
from discord.ext import commands

logger = logging.getLogger(__name__)


def handle_api_errors(func: Callable) -> Callable:
    """
    API呼び出しの共通エラーハンドリング

    requests ライブラリを使用したAPI呼び出しで発生する
    一般的なエラーをキャッチし、ユーザーに適切なメッセージを表示します。

    Args:
        func: デコレート対象の非同期関数

    Returns:
        ラップされた関数

    使用例:
        @commands.command(name="predict")
        @handle_api_errors
        async def predict_race(self, ctx, race_spec: str):
            # エラーハンドリング不要、本質的なロジックのみ記述
            response = requests.get(...)
    """
    @wraps(func)
    async def wrapper(self, ctx: commands.Context, *args, **kwargs):
        try:
            return await func(self, ctx, *args, **kwargs)

        except requests.exceptions.Timeout as e:
            logger.error(f"{func.__name__} - APIタイムアウト: {e}")
            await ctx.send("❌ タイムアウトしました。予想に時間がかかっています。")

        except requests.exceptions.ConnectionError as e:
            logger.error(f"{func.__name__} - API接続エラー: {e}")
            await ctx.send("❌ APIサーバーに接続できません。サーバーが起動しているか確認してください。")

        except requests.exceptions.RequestException as e:
            logger.error(f"{func.__name__} - APIリクエストエラー: {e}")
            await ctx.send(f"❌ APIリクエストエラーが発生しました: {str(e)}")

        except ValueError as e:
            logger.warning(f"{func.__name__} - バリデーションエラー: {e}")
            await ctx.send(f"❌ {str(e)}")

        except Exception as e:
            logger.exception(f"{func.__name__} - 予期しないエラー: {e}")
            await ctx.send(f"❌ エラーが発生しました: {str(e)}")

    return wrapper


def log_command_execution(func: Callable) -> Callable:
    """
    コマンド実行ログを自動記録

    Args:
        func: デコレート対象の非同期関数

    Returns:
        ラップされた関数
    """
    @wraps(func)
    async def wrapper(self, ctx: commands.Context, *args, **kwargs):
        logger.info(f"コマンド実行: {func.__name__}, user={ctx.author}, args={args}, kwargs={kwargs}")
        try:
            result = await func(self, ctx, *args, **kwargs)
            logger.info(f"コマンド完了: {func.__name__}")
            return result
        except Exception as e:
            logger.error(f"コマンド失敗: {func.__name__}, error={e}")
            raise

    return wrapper
