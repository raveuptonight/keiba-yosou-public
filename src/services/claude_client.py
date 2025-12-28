"""
Claude API クライアント実装

Anthropic SDK を使用した競馬予想生成のための Claude API 呼び出し
async/await 対応、エラーハンドリング、レート制限、ログ出力を実装
"""

import os
import json
import logging
from typing import Dict, Any
from datetime import datetime
import asyncio

from anthropic import AsyncAnthropic, APIError, APITimeoutError, RateLimitError

from src.config import (
    CLAUDE_DEFAULT_MODEL,
    CLAUDE_API_TIMEOUT,
    LLM_PREDICTION_TEMPERATURE,
    LLM_MAX_TOKENS,
)
from src.exceptions import (
    LLMAPIError,
    LLMResponseError,
    LLMTimeoutError,
    MissingEnvironmentVariableError,
)
from src.services.rate_limiter import claude_rate_limiter

logger = logging.getLogger(__name__)


def _get_api_key() -> str:
    """
    環境変数からClaude APIキーを取得

    Returns:
        str: APIキー

    Raises:
        MissingEnvironmentVariableError: APIキーが設定されていない場合
    """
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    if not api_key:
        raise MissingEnvironmentVariableError("ANTHROPIC_API_KEY or CLAUDE_API_KEY")
    return api_key


def generate_prediction_prompt(race_data: Dict[str, Any]) -> str:
    """
    予想データからClaude APIに送信するプロンプトを生成

    Args:
        race_data: get_race_prediction_data() の返り値
            {
                "race": {...},          # レース基本情報
                "horses": [...],        # 出走馬情報
                "histories": {...},     # 各馬の過去10走
                "pedigrees": {...},     # 血統情報
                "training": {...},      # 調教情報
                "statistics": {...},    # 着度数統計
                "odds": {...}          # オッズ情報
            }

    Returns:
        str: プロンプト文字列
    """
    race_info = race_data.get("race", {})
    horses = race_data.get("horses", [])
    histories = race_data.get("histories", {})
    pedigrees = race_data.get("pedigrees", {})
    training = race_data.get("training", {})
    statistics = race_data.get("statistics", {})
    odds_data = race_data.get("odds", {})

    # レース基本情報の抽出
    from src.db.table_names import (
        COL_RACE_NAME,
        COL_JYOCD,
        COL_KYORI,
        COL_TRACK_CD,
        COL_GRADE_CD,
        COL_RACE_NUM,
    )

    race_name = race_info.get(COL_RACE_NAME, "不明")
    venue = race_info.get(COL_JYOCD, "不明")
    distance = race_info.get(COL_KYORI, 0)
    track_type = race_info.get(COL_TRACK_CD, "不明")
    grade = race_info.get(COL_GRADE_CD, "")
    race_number = race_info.get(COL_RACE_NUM, "不明")

    # プロンプト構築
    prompt = f"""あなたは競馬予想のプロフェッショナルです。以下のレースデータを分析し、予想結果をJSON形式で出力してください。

## レース情報
- レース名: {race_name}
- 競馬場: {venue}
- 距離: {distance}m
- トラック: {track_type}
- グレード: {grade}
- レース番号: {race_number}R

## 出走馬データ
"""

    # 各馬の情報を追加
    from src.db.table_names import (
        COL_UMABAN,
        COL_BAMEI,
        COL_KETTONUM,
        COL_KINRYO,
        COL_KISYU_NAME,
        COL_TRAINER_NAME,
    )

    for i, horse in enumerate(horses[:18], 1):  # 最大18頭まで
        horse_num = horse.get(COL_UMABAN, i)
        horse_name = horse.get(COL_BAMEI, f"馬{i}")
        kettonum = horse.get(COL_KETTONUM, "")
        weight = horse.get(COL_KINRYO, 0)
        jockey = horse.get(COL_KISYU_NAME, "不明")
        trainer = horse.get(COL_TRAINER_NAME, "不明")

        prompt += f"\n### {horse_num}番 {horse_name}\n"
        prompt += f"- 斤量: {weight}kg\n"
        prompt += f"- 騎手: {jockey}\n"
        prompt += f"- 調教師: {trainer}\n"

        # 過去成績（最新5走）
        if kettonum in histories and histories[kettonum]:
            prompt += "- 過去5走:\n"
            for idx, past_race in enumerate(histories[kettonum][:5], 1):
                from src.db.table_names import COL_着順, COL_RACE_DATE
                chakujun = past_race.get(COL_着順, "-")
                race_date = past_race.get(COL_RACE_DATE, "不明")
                prompt += f"  {idx}. {race_date} {chakujun}着\n"
        else:
            prompt += "- 過去成績: データなし\n"

        # オッズ情報（単勝）
        if odds_data and "win" in odds_data:
            win_odds = odds_data["win"].get(str(horse_num), {}).get("odds", "-")
            prompt += f"- 単勝オッズ: {win_odds}\n"

    # 出力形式の指示
    prompt += """

## 予想指示

上記データを分析し、以下のJSON形式で予想結果を出力してください。

**重要**: 必ずJSON形式のみを出力し、説明文や前置きは一切不要です。

```json
{
  "win_prediction": {
    "first": {
      "horse_number": <馬番>,
      "horse_name": "<馬名>",
      "expected_odds": <予想オッズ>,
      "confidence": <信頼度 0.0-1.0>
    },
    "second": {
      "horse_number": <馬番>,
      "horse_name": "<馬名>",
      "expected_odds": <予想オッズ>,
      "confidence": <信頼度 0.0-1.0>
    },
    "third": {
      "horse_number": <馬番>,
      "horse_name": "<馬名>",
      "expected_odds": <予想オッズ>,
      "confidence": <信頼度 0.0-1.0>
    },
    "fourth": {
      "horse_number": <馬番>,
      "horse_name": "<馬名>",
      "expected_odds": <予想オッズ>,
      "confidence": <信頼度 0.0-1.0>
    },
    "fifth": {
      "horse_number": <馬番>,
      "horse_name": "<馬名>",
      "expected_odds": <予想オッズ>,
      "confidence": <信頼度 0.0-1.0>
    },
    "excluded": [
      {
        "horse_number": <馬番>,
        "horse_name": "<馬名>",
        "reason": "<消す理由>"
      }
    ]
  },
  "betting_strategy": {
    "recommended_tickets": [
      {
        "ticket_type": "3連複",
        "numbers": [<馬番1>, <馬番2>, <馬番3>],
        "amount": <購入金額>,
        "expected_payout": <期待払戻額>
      },
      {
        "ticket_type": "馬連",
        "numbers": [<馬番1>, <馬番2>],
        "amount": <購入金額>,
        "expected_payout": <期待払戻額>
      }
    ]
  }
}
```

注意事項:
- first, second, third は必須
- fourth, fifth は任意（有力馬が多い場合のみ）
- excluded は最大3頭まで（評価が著しく低い馬のみ）
- recommended_tickets は2-5個程度
- 総投資額は10,000円以内を目安に
"""

    return prompt


async def call_claude_api(
    prompt: str,
    temperature: float = LLM_PREDICTION_TEMPERATURE,
    model: str = CLAUDE_DEFAULT_MODEL,
    max_tokens: int = LLM_MAX_TOKENS,
) -> Dict[str, Any]:
    """
    Claude API を呼び出して予想を生成

    Args:
        prompt: プロンプト文字列
        temperature: サンプリング温度（0.0-1.0）
        model: 使用するClaudeモデル
        max_tokens: 最大トークン数

    Returns:
        Dict[str, Any]: {
            "content": str,          # レスポンステキスト
            "model": str,            # 使用モデル
            "usage": Dict,           # トークン使用量
            "stop_reason": str       # 停止理由
        }

    Raises:
        LLMAPIError: API呼び出しエラー
        LLMTimeoutError: タイムアウトエラー
    """
    # レート制限チェック
    if not claude_rate_limiter.is_allowed():
        retry_after = claude_rate_limiter.get_retry_after()
        logger.warning(f"Rate limit exceeded. Waiting {retry_after} seconds...")
        await asyncio.sleep(retry_after)

    # APIキー取得
    api_key = _get_api_key()

    # クライアント初期化
    client = AsyncAnthropic(
        api_key=api_key,
        timeout=CLAUDE_API_TIMEOUT,
    )

    logger.info(f"Calling Claude API: model={model}, temperature={temperature}, max_tokens={max_tokens}")
    logger.debug(f"Prompt length: {len(prompt)} chars")

    try:
        # API呼び出し
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        # レスポンス内容の抽出
        content = ""
        if response.content:
            # TextBlockからテキストを抽出
            content = "\n".join(
                block.text for block in response.content
                if hasattr(block, "text")
            )

        result = {
            "content": content,
            "model": response.model,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            "stop_reason": response.stop_reason,
        }

        logger.info(
            f"Claude API success: model={result['model']}, "
            f"tokens={result['usage']['input_tokens']}+{result['usage']['output_tokens']}, "
            f"stop_reason={result['stop_reason']}"
        )
        logger.debug(f"Response length: {len(content)} chars")

        return result

    except APITimeoutError as e:
        logger.error(f"Claude API timeout: {e}")
        raise LLMTimeoutError(f"Claude API request timed out after {CLAUDE_API_TIMEOUT}s")

    except RateLimitError as e:
        logger.error(f"Claude API rate limit: {e}")
        raise LLMAPIError(
            "Rate limit exceeded",
            api_name="Claude",
            status_code=429
        )

    except APIError as e:
        logger.error(f"Claude API error: {e}")
        status_code = getattr(e, "status_code", None)
        raise LLMAPIError(
            str(e),
            api_name="Claude",
            status_code=status_code
        )

    except Exception as e:
        logger.error(f"Unexpected error calling Claude API: {e}")
        raise LLMAPIError(f"Unexpected error: {e}", api_name="Claude")


def parse_prediction_response(response: str) -> Dict[str, Any]:
    """
    Claude APIのレスポンスをパースして予想結果JSONを抽出

    Args:
        response: Claude APIのレスポンステキスト

    Returns:
        Dict[str, Any]: パース済み予想結果
            {
                "win_prediction": {...},
                "betting_strategy": {...}
            }

    Raises:
        LLMResponseError: レスポンスのパースに失敗した場合
    """
    logger.debug(f"Parsing prediction response (length: {len(response)} chars)")

    # JSONコードブロックを抽出（```json ... ``` の場合）
    if "```json" in response:
        try:
            start = response.index("```json") + 7
            end = response.index("```", start)
            json_str = response[start:end].strip()
        except ValueError:
            logger.warning("JSON code block markers found but parsing failed")
            json_str = response
    elif "```" in response:
        # ```のみの場合
        try:
            start = response.index("```") + 3
            end = response.index("```", start)
            json_str = response[start:end].strip()
        except ValueError:
            json_str = response
    else:
        json_str = response

    # JSON開始位置を探す
    json_start = json_str.find("{")
    if json_start == -1:
        logger.error("No JSON object found in response")
        raise LLMResponseError("No JSON object found in Claude response")

    # JSON終了位置を探す（最後の}）
    json_end = json_str.rfind("}") + 1
    if json_end == 0:
        logger.error("Incomplete JSON object in response")
        raise LLMResponseError("Incomplete JSON object in Claude response")

    json_str = json_str[json_start:json_end]

    try:
        prediction_data = json.loads(json_str)
        logger.debug("JSON parsing successful")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        logger.debug(f"Failed JSON string: {json_str[:500]}...")
        raise LLMResponseError(f"Failed to parse JSON: {e}")

    # 必須フィールドの検証
    if "win_prediction" not in prediction_data:
        raise LLMResponseError("Missing required field: win_prediction")

    win_pred = prediction_data["win_prediction"]
    for rank in ["first", "second", "third"]:
        if rank not in win_pred:
            raise LLMResponseError(f"Missing required field: win_prediction.{rank}")

        horse_data = win_pred[rank]
        if "horse_number" not in horse_data or "horse_name" not in horse_data:
            raise LLMResponseError(
                f"Missing required fields in win_prediction.{rank}: "
                f"horse_number and horse_name are required"
            )

    logger.info(
        f"Prediction parsed successfully: "
        f"first={win_pred['first']['horse_number']}, "
        f"second={win_pred['second']['horse_number']}, "
        f"third={win_pred['third']['horse_number']}"
    )

    return prediction_data


async def generate_race_prediction(
    race_data: Dict[str, Any],
    temperature: float = LLM_PREDICTION_TEMPERATURE,
    model: str = CLAUDE_DEFAULT_MODEL,
) -> Dict[str, Any]:
    """
    レースデータから予想を生成（プロンプト生成→API呼び出し→パース）

    高レベルAPI: ワンステップで予想を生成

    Args:
        race_data: get_race_prediction_data() の返り値
        temperature: サンプリング温度
        model: 使用するClaudeモデル

    Returns:
        Dict[str, Any]: パース済み予想結果
            {
                "win_prediction": {...},
                "betting_strategy": {...},
                "_metadata": {
                    "model": str,
                    "usage": dict,
                    "stop_reason": str,
                    "generated_at": str
                }
            }

    Raises:
        LLMAPIError: API呼び出しエラー
        LLMResponseError: レスポンスパースエラー
        LLMTimeoutError: タイムアウトエラー
    """
    logger.info("Starting race prediction generation")

    # プロンプト生成
    prompt = generate_prediction_prompt(race_data)
    logger.debug(f"Generated prompt: {len(prompt)} chars")

    # API呼び出し
    response = await call_claude_api(
        prompt=prompt,
        temperature=temperature,
        model=model
    )

    # レスポンスパース
    prediction = parse_prediction_response(response["content"])

    # メタデータを追加
    prediction["_metadata"] = {
        "model": response["model"],
        "usage": response["usage"],
        "stop_reason": response["stop_reason"],
        "generated_at": datetime.now().isoformat(),
    }

    logger.info("Race prediction generation completed")

    return prediction
