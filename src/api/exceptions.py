"""
APIカスタム例外クラス
"""

from fastapi import HTTPException, status


class RaceNotFoundException(HTTPException):
    """レースが見つからない場合の例外"""

    def __init__(self, race_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RACE_NOT_FOUND",
                "message": "指定されたレースが見つかりません",
                "details": {"race_id": race_id},
            },
        )


class HorseNotFoundException(HTTPException):
    """馬が見つからない場合の例外"""

    def __init__(self, kettonum: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "HORSE_NOT_FOUND",
                "message": "指定された馬が見つかりません",
                "details": {"kettonum": kettonum},
            },
        )


class PredictionNotFoundException(HTTPException):
    """予想結果が見つからない場合の例外"""

    def __init__(self, prediction_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "PREDICTION_NOT_FOUND",
                "message": "指定された予想結果が見つかりません",
                "details": {"prediction_id": prediction_id},
            },
        )


class PredictionTimeoutException(HTTPException):
    """予想生成タイムアウトの例外"""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={
                "code": "PREDICTION_TIMEOUT",
                "message": "予想生成がタイムアウトしました。",
                "details": {},
            },
        )


class DatabaseErrorException(HTTPException):
    """データベースエラーの例外"""

    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "DATABASE_ERROR",
                "message": f"データベースエラーが発生しました: {message}",
                "details": {},
            },
        )


class InvalidRequestException(HTTPException):
    """不正なリクエストの例外"""

    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_REQUEST",
                "message": message,
                "details": {},
            },
        )
