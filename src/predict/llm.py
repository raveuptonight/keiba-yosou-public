"""
LLMクライアントモジュール

複数のLLMプロバイダー（Gemini、Claude等）を統一インターフェースで利用する。
"""

import os
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv()


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
        temperature: float = 0.7,
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
            str: 生成されたテキスト
        """
        pass

    @abstractmethod
    def generate_with_context(
        self,
        messages: list[Dict[str, str]],
        temperature: float = 0.7,
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
            str: 生成されたテキスト
        """
        pass


class GeminiClient(LLMClient):
    """Google Gemini APIクライアント"""

    def __init__(
        self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash-exp"
    ):
        """
        Args:
            api_key: Gemini APIキー（Noneの場合は環境変数GEMINI_API_KEYから取得）
            model: 使用するモデル（デフォルト: gemini-2.0-flash-exp）
        """
        super().__init__(api_key, model)
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            raise ValueError(
                "Gemini API key not found. Set GEMINI_API_KEY environment variable."
            )

        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        self.client = genai.GenerativeModel(self.model)

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        テキスト生成

        Args:
            prompt: プロンプト
            temperature: 生成の多様性（0.0〜1.0）
            max_tokens: 最大トークン数
            **kwargs: Gemini固有のパラメータ

        Returns:
            str: 生成されたテキスト
        """
        generation_config = {
            "temperature": temperature,
        }

        if max_tokens is not None:
            generation_config["max_output_tokens"] = max_tokens

        generation_config.update(kwargs)

        response = self.client.generate_content(
            prompt, generation_config=generation_config
        )

        return response.text

    def generate_with_context(
        self,
        messages: list[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        会話履歴を含むテキスト生成

        Args:
            messages: 会話履歴 [{"role": "user", "content": "..."}, ...]
            temperature: 生成の多様性（0.0〜1.0）
            max_tokens: 最大トークン数
            **kwargs: Gemini固有のパラメータ

        Returns:
            str: 生成されたテキスト
        """
        generation_config = {
            "temperature": temperature,
        }

        if max_tokens is not None:
            generation_config["max_output_tokens"] = max_tokens

        generation_config.update(kwargs)

        # Geminiのチャット形式に変換
        chat = self.client.start_chat(history=[])

        # 最後のメッセージ以外を履歴として追加
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            chat.history.append({"role": role, "parts": [msg["content"]]})

        # 最後のメッセージで生成
        last_message = messages[-1]["content"]
        response = chat.send_message(last_message, generation_config=generation_config)

        return response.text


class ClaudeClient(LLMClient):
    """
    Anthropic Claude APIクライアント（将来実装用）

    現在は未実装。Geminiから移行する際に実装する。
    """

    def __init__(
        self, api_key: Optional[str] = None, model: str = "claude-3-5-sonnet-20241022"
    ):
        """
        Args:
            api_key: Claude APIキー（Noneの場合は環境変数ANTHROPIC_API_KEYから取得）
            model: 使用するモデル（デフォルト: claude-3-5-sonnet-20241022）
        """
        super().__init__(api_key, model)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")

        if not self.api_key:
            raise ValueError(
                "Claude API key not found. Set ANTHROPIC_API_KEY environment variable."
            )

        # TODO: Anthropic SDKの初期化
        # from anthropic import Anthropic
        # self.client = Anthropic(api_key=self.api_key)

        raise NotImplementedError("ClaudeClient is not yet implemented.")

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
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
            str: 生成されたテキスト
        """
        raise NotImplementedError("ClaudeClient.generate is not yet implemented.")

    def generate_with_context(
        self,
        messages: list[Dict[str, str]],
        temperature: float = 0.7,
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
            str: 生成されたテキスト
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
        LLMClient: LLMクライアントインスタンス

    Raises:
        ValueError: 未対応のプロバイダーが指定された場合
    """
    if provider.lower() == "gemini":
        return GeminiClient(**kwargs)
    elif provider.lower() == "claude":
        return ClaudeClient(**kwargs)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


if __name__ == "__main__":
    # このファイルを直接実行した場合、簡単なテストを実行
    print("=== Gemini API テスト ===")
    try:
        client = get_llm_client("gemini")
        response = client.generate(
            "競馬予想システムについて、一言で説明してください。", temperature=0.5
        )
        print(f"応答: {response}")
    except Exception as e:
        print(f"エラー: {e}")
