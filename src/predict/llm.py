"""
LLMクライアントモジュール

複数のLLMプロバイダー（Gemini、Claude等）を統一インターフェースで利用する。
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import time

from dotenv import load_dotenv

from src.config import (
    LLM_DEFAULT_TEMPERATURE,
    LLM_MAX_TOKENS,
    GEMINI_DEFAULT_MODEL,
    GEMINI_API_TIMEOUT,
    CLAUDE_DEFAULT_MODEL,
    CLAUDE_API_TIMEOUT,
    LLM_MAX_RETRIES,
    LLM_RETRY_DELAY,
)
from src.exceptions import (
    LLMAPIError,
    LLMResponseError,
    LLMTimeoutError,
    MissingEnvironmentVariableError,
)

# .envファイルを読み込み
load_dotenv()

# ロガー設定
logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """LLMクライアントの基底クラス"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Args:
            api_key: APIキー（Noneの場合は環境変数から取得）
            model: 使用するモデル名（Noneの場合はデフォルト）
        """
        self.api_key = api_key
        self.model = model

    @abstractmethod
    def generate(
        self,
        prompt: str,
        temperature: float = LLM_DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        テキスト生成

        Args:
            prompt: プロンプト
            temperature: 生成の多様性（0.0〜1.0）
            max_tokens: 最大トークン数
            **kwargs: プロバイダー固有のパラメータ

        Returns:
            生成されたテキスト

        Raises:
            LLMAPIError: API呼び出しに失敗した場合
            LLMResponseError: レスポンスの解析に失敗した場合
            LLMTimeoutError: タイムアウトした場合
        """
        pass

    @abstractmethod
    def generate_with_context(
        self,
        messages: List[Dict[str, str]],
        temperature: float = LLM_DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        会話履歴を含むテキスト生成

        Args:
            messages: 会話履歴 [{"role": "user", "content": "..."}, ...]
            temperature: 生成の多様性（0.0〜1.0）
            max_tokens: 最大トークン数
            **kwargs: プロバイダー固有のパラメータ

        Returns:
            生成されたテキスト

        Raises:
            LLMAPIError: API呼び出しに失敗した場合
            LLMResponseError: レスポンスの解析に失敗した場合
            LLMTimeoutError: タイムアウトした場合
        """
        pass


class GeminiClient(LLMClient):
    """Google Gemini APIクライアント（新google.genai SDK使用）"""

    def __init__(
        self, api_key: Optional[str] = None, model: Optional[str] = None
    ):
        """
        Args:
            api_key: Gemini APIキー（Noneの場合は環境変数GEMINI_API_KEYから取得）
            model: 使用するモデル（Noneの場合は環境変数GEMINI_MODELから取得、デフォルト: gemini-2.0-flash-exp）

        Raises:
            MissingEnvironmentVariableError: APIキーが設定されていない場合
            LLMAPIError: クライアント初期化に失敗した場合
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", GEMINI_DEFAULT_MODEL)

        super().__init__(self.api_key, self.model)

        if not self.api_key:
            raise MissingEnvironmentVariableError("GEMINI_API_KEY")

        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
            logger.info(f"GeminiClient初期化成功: model={self.model}")
        except Exception as e:
            logger.error(f"GeminiClient初期化失敗: {e}")
            raise LLMAPIError(f"Gemini クライアント初期化失敗: {e}", api_name="Gemini") from e

    def generate(
        self,
        prompt: str,
        temperature: float = LLM_DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        テキスト生成

        Args:
            prompt: プロンプト
            temperature: 生成の多様性（0.0〜1.0）
            max_tokens: 最大トークン数（デフォルト: 設定値）
            **kwargs: Gemini固有のパラメータ

        Returns:
            生成されたテキスト

        Raises:
            LLMAPIError: API呼び出しに失敗した場合
            LLMResponseError: レスポンスが空または不正な場合
            LLMTimeoutError: タイムアウトした場合
        """
        if not prompt:
            raise LLMAPIError("プロンプトが空です", api_name="Gemini")

        try:
            from google.genai import types

            # 生成設定を作成
            config_params = {"temperature": temperature}
            if max_tokens is not None:
                config_params["max_output_tokens"] = max_tokens
            else:
                config_params["max_output_tokens"] = LLM_MAX_TOKENS
            config_params.update(kwargs)

            generation_config = types.GenerateContentConfig(**config_params)

            logger.debug(f"Gemini API呼び出し開始: prompt_len={len(prompt)}, temp={temperature}")

            # コンテンツ生成（タイムアウト設定）
            start_time = time.time()
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=generation_config
            )
            elapsed = time.time() - start_time

            # レスポンス検証
            if not hasattr(response, 'text') or not response.text:
                logger.error("Gemini APIレスポンスが空")
                raise LLMResponseError("Gemini APIレスポンスが空です")

            logger.info(f"Gemini API呼び出し成功: elapsed={elapsed:.2f}s, response_len={len(response.text)}")
            return response.text

        except LLMResponseError:
            # 既知のエラーは再スロー
            raise
        except TimeoutError as e:
            logger.error(f"Gemini APIタイムアウト: {e}")
            raise LLMTimeoutError(f"Gemini API タイムアウト: {e}") from e
        except Exception as e:
            logger.error(f"Gemini API呼び出し失敗: {e}")
            raise LLMAPIError(f"Gemini API呼び出し失敗: {e}", api_name="Gemini") from e

    def generate_with_context(
        self,
        messages: List[Dict[str, str]],
        temperature: float = LLM_DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        会話履歴を含むテキスト生成

        Args:
            messages: 会話履歴 [{"role": "user", "content": "..."}, ...]
            temperature: 生成の多様性（0.0〜1.0）
            max_tokens: 最大トークン数（デフォルト: 設定値）
            **kwargs: Gemini固有のパラメータ

        Returns:
            生成されたテキスト

        Raises:
            LLMAPIError: API呼び出しに失敗した場合
            LLMResponseError: レスポンスが空または不正な場合
            LLMTimeoutError: タイムアウトした場合
        """
        if not messages:
            raise LLMAPIError("メッセージリストが空です", api_name="Gemini")

        try:
            from google.genai import types

            # 生成設定を作成
            config_params = {"temperature": temperature}
            if max_tokens is not None:
                config_params["max_output_tokens"] = max_tokens
            else:
                config_params["max_output_tokens"] = LLM_MAX_TOKENS
            config_params.update(kwargs)

            generation_config = types.GenerateContentConfig(**config_params)

            # メッセージを新SDKのフォーマットに変換
            contents = []
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

            logger.debug(f"Gemini API（コンテキスト付き）呼び出し開始: messages={len(messages)}, temp={temperature}")

            # チャット生成
            start_time = time.time()
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=generation_config
            )
            elapsed = time.time() - start_time

            # レスポンス検証
            if not hasattr(response, 'text') or not response.text:
                logger.error("Gemini APIレスポンス（コンテキスト付き）が空")
                raise LLMResponseError("Gemini APIレスポンスが空です")

            logger.info(f"Gemini API（コンテキスト付き）呼び出し成功: elapsed={elapsed:.2f}s, response_len={len(response.text)}")
            return response.text

        except LLMResponseError:
            # 既知のエラーは再スロー
            raise
        except TimeoutError as e:
            logger.error(f"Gemini APIタイムアウト（コンテキスト付き）: {e}")
            raise LLMTimeoutError(f"Gemini API タイムアウト: {e}") from e
        except Exception as e:
            logger.error(f"Gemini API呼び出し失敗（コンテキスト付き）: {e}")
            raise LLMAPIError(f"Gemini API呼び出し失敗: {e}", api_name="Gemini") from e


class ClaudeClient(LLMClient):
    """
    Anthropic Claude APIクライアント（将来実装用）

    現在は未実装。Geminiから移行する際に実装する。
    """

    def __init__(
        self, api_key: Optional[str] = None, model: Optional[str] = None
    ):
        """
        Args:
            api_key: Claude APIキー（Noneの場合は環境変数ANTHROPIC_API_KEYから取得）
            model: 使用するモデル（デフォルト: claude-3-5-sonnet-20241022）

        Raises:
            MissingEnvironmentVariableError: APIキーが設定されていない場合
            NotImplementedError: ClaudeClientは未実装
        """
        super().__init__(api_key, model or CLAUDE_DEFAULT_MODEL)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")

        if not self.api_key:
            raise MissingEnvironmentVariableError("ANTHROPIC_API_KEY")

        # TODO: Anthropic SDKの初期化
        # from anthropic import Anthropic
        # self.client = Anthropic(api_key=self.api_key)

        logger.warning("ClaudeClientは未実装です")
        raise NotImplementedError("ClaudeClient is not yet implemented.")

    def generate(
        self,
        prompt: str,
        temperature: float = LLM_DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        テキスト生成（未実装）

        Args:
            prompt: プロンプト
            temperature: 生成の多様性（0.0〜1.0）
            max_tokens: 最大トークン数
            **kwargs: Claude固有のパラメータ

        Returns:
            生成されたテキスト

        Raises:
            NotImplementedError: 未実装
        """
        raise NotImplementedError("ClaudeClient.generate is not yet implemented.")

    def generate_with_context(
        self,
        messages: List[Dict[str, str]],
        temperature: float = LLM_DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        会話履歴を含むテキスト生成（未実装）

        Args:
            messages: 会話履歴 [{"role": "user", "content": "..."}, ...]
            temperature: 生成の多様性（0.0〜1.0）
            max_tokens: 最大トークン数
            **kwargs: Claude固有のパラメータ

        Returns:
            生成されたテキスト

        Raises:
            NotImplementedError: 未実装
        """
        raise NotImplementedError(
            "ClaudeClient.generate_with_context is not yet implemented."
        )


def get_llm_client(provider: str = "gemini", **kwargs) -> LLMClient:
    """
    LLMクライアントのファクトリー関数

    Args:
        provider: プロバイダー名（"gemini" or "claude"）
        **kwargs: クライアント初期化パラメータ

    Returns:
        LLMクライアントインスタンス

    Raises:
        ValueError: 未対応のプロバイダーが指定された場合
        MissingEnvironmentVariableError: APIキーが設定されていない場合
        LLMAPIError: クライアント初期化に失敗した場合
    """
    try:
        if provider.lower() == "gemini":
            logger.info(f"LLMクライアント作成: provider=gemini")
            return GeminiClient(**kwargs)
        elif provider.lower() == "claude":
            logger.info(f"LLMクライアント作成: provider=claude")
            return ClaudeClient(**kwargs)
        else:
            logger.error(f"未対応のLLMプロバイダー: {provider}")
            raise ValueError(f"Unsupported provider: {provider}")
    except Exception as e:
        logger.error(f"LLMクライアント作成失敗: {e}")
        raise


if __name__ == "__main__":
    # このファイルを直接実行した場合、簡単なテストを実行
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=== Gemini API テスト ===")
    try:
        client = get_llm_client("gemini")
        response = client.generate(
            "競馬予想システムについて、一言で説明してください。",
            temperature=0.5
        )
        print(f"応答: {response}")
    except MissingEnvironmentVariableError as e:
        print(f"環境変数エラー: {e}")
    except LLMAPIError as e:
        print(f"API エラー: {e}")
    except Exception as e:
        print(f"エラー: {e}")
