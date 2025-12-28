"""
レート制限実装

スライディングウィンドウ方式でAPIリクエスト数を制限
"""

from datetime import datetime, timedelta
from collections import deque
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """シンプルなレート制限実装（スライディングウィンドウ）"""

    def __init__(self, max_requests: int, window_seconds: int):
        """
        Args:
            max_requests: 時間窓内の最大リクエスト数
            window_seconds: 時間窓のサイズ（秒）
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: deque = deque()

    def is_allowed(self) -> bool:
        """
        リクエストが許可されるかチェック

        Returns:
            bool: 許可される場合True
        """
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.window_seconds)

        # 古いリクエストを削除
        while self.requests and self.requests[0] < cutoff:
            self.requests.popleft()

        # 制限チェック
        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            logger.debug(
                f"Rate limit OK: {len(self.requests)}/{self.max_requests} requests"
            )
            return True

        logger.warning(
            f"Rate limit exceeded: {len(self.requests)}/{self.max_requests} requests"
        )
        return False

    def get_retry_after(self) -> int:
        """
        次のリクエストまでの待機時間（秒）を取得

        Returns:
            int: 待機時間（秒）
        """
        if not self.requests:
            return 0

        oldest = self.requests[0]
        cutoff = oldest + timedelta(seconds=self.window_seconds)
        now = datetime.now()

        if cutoff > now:
            return int((cutoff - now).total_seconds()) + 1
        return 0

    def reset(self) -> None:
        """レート制限をリセット"""
        self.requests.clear()
        logger.info("Rate limit reset")


# Claude API用のグローバルレート制限インスタンス
# 5リクエスト/分
claude_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)
