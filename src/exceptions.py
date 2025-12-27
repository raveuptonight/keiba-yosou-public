"""
カスタム例外クラス

システム全体で使用する例外を定義し、エラーハンドリングを統一
"""


class KeibaYosouError(Exception):
    """競馬予想システムの基底例外クラス"""
    pass


# =====================================
# データベース関連例外
# =====================================
class DatabaseError(KeibaYosouError):
    """データベース関連のエラー"""
    pass


class DatabaseConnectionError(DatabaseError):
    """データベース接続エラー"""
    pass


class DatabaseQueryError(DatabaseError):
    """データベースクエリ実行エラー"""
    pass


class DatabaseMigrationError(DatabaseError):
    """データベースマイグレーションエラー"""
    pass


# =====================================
# LLM関連例外
# =====================================
class LLMError(KeibaYosouError):
    """LLM関連のエラー"""
    pass


class LLMAPIError(LLMError):
    """LLM API呼び出しエラー"""
    def __init__(self, message: str, api_name: str = "Unknown", status_code: int = None):
        self.api_name = api_name
        self.status_code = status_code
        super().__init__(f"[{api_name}] {message}" + (f" (status: {status_code})" if status_code else ""))


class LLMResponseError(LLMError):
    """LLMレスポンス解析エラー"""
    pass


class LLMTimeoutError(LLMError):
    """LLMタイムアウトエラー"""
    pass


# =====================================
# 機械学習関連例外
# =====================================
class MLError(KeibaYosouError):
    """機械学習関連のエラー"""
    pass


class ModelNotFoundError(MLError):
    """モデルファイルが見つからない"""
    pass


class ModelLoadError(MLError):
    """モデル読み込みエラー"""
    pass


class ModelTrainError(MLError):
    """モデル学習エラー"""
    pass


class ModelPredictionError(MLError):
    """モデル予測エラー"""
    pass


class InsufficientDataError(MLError):
    """学習データ不足エラー"""
    pass


# =====================================
# パイプライン関連例外
# =====================================
class PipelineError(KeibaYosouError):
    """パイプライン実行エラー"""
    pass


class FeatureExtractionError(PipelineError):
    """特徴量抽出エラー"""
    pass


class PredictionError(PipelineError):
    """予想生成エラー"""
    pass


class AnalysisError(PipelineError):
    """分析エラー"""
    pass


# =====================================
# データ関連例外
# =====================================
class DataError(KeibaYosouError):
    """データ関連のエラー"""
    pass


class DataValidationError(DataError):
    """データ検証エラー"""
    pass


class DataParseError(DataError):
    """データ解析エラー（JSON等）"""
    pass


class MissingDataError(DataError):
    """必要なデータが不足"""
    pass


# =====================================
# API関連例外
# =====================================
class APIError(KeibaYosouError):
    """API関連のエラー"""
    pass


class ExternalAPIError(APIError):
    """外部API呼び出しエラー"""
    pass


# =====================================
# Discord Bot関連例外
# =====================================
class BotError(KeibaYosouError):
    """Discord Bot関連のエラー"""
    pass


class BotCommandError(BotError):
    """Botコマンド実行エラー"""
    pass


# =====================================
# 設定関連例外
# =====================================
class ConfigError(KeibaYosouError):
    """設定関連のエラー"""
    pass


class MissingEnvironmentVariableError(ConfigError):
    """必須環境変数が設定されていない"""
    def __init__(self, var_name: str):
        self.var_name = var_name
        super().__init__(f"環境変数 '{var_name}' が設定されていません")
