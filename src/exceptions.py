"""
Custom Exception Classes

Defines system-wide exceptions for unified error handling.
"""


class KeibaYosouError(Exception):
    """Base exception class for horse racing prediction system."""
    pass


# =====================================
# Database Exceptions
# =====================================
class DatabaseError(KeibaYosouError):
    """Database related error."""
    pass


class DatabaseConnectionError(DatabaseError):
    """Database connection error."""
    pass


class DatabaseQueryError(DatabaseError):
    """Database query execution error."""
    pass


class DatabaseMigrationError(DatabaseError):
    """Database migration error."""
    pass


# =====================================
# Machine Learning Exceptions
# =====================================
class MLError(KeibaYosouError):
    """Machine learning related error."""
    pass


class ModelNotFoundError(MLError):
    """Model file not found."""
    pass


class ModelLoadError(MLError):
    """Model loading error."""
    pass


class ModelTrainError(MLError):
    """Model training error."""
    pass


class ModelPredictionError(MLError):
    """Model prediction error."""
    pass


class InsufficientDataError(MLError):
    """Insufficient training data error."""
    pass


# =====================================
# Pipeline Exceptions
# =====================================
class PipelineError(KeibaYosouError):
    """Pipeline execution error."""
    pass


class FeatureExtractionError(PipelineError):
    """Feature extraction error."""
    pass


class PredictionError(PipelineError):
    """Prediction generation error."""
    pass


class AnalysisError(PipelineError):
    """Analysis error."""
    pass


# =====================================
# Data Exceptions
# =====================================
class DataError(KeibaYosouError):
    """Data related error."""
    pass


class DataValidationError(DataError):
    """Data validation error."""
    pass


class DataParseError(DataError):
    """Data parsing error (JSON, etc.)."""
    pass


class MissingDataError(DataError):
    """Required data is missing."""
    pass


# =====================================
# API Exceptions
# =====================================
class APIError(KeibaYosouError):
    """API related error."""
    pass


class ExternalAPIError(APIError):
    """External API call error."""
    pass


# =====================================
# Discord Bot Exceptions
# =====================================
class BotError(KeibaYosouError):
    """Discord Bot related error."""
    pass


class BotCommandError(BotError):
    """Bot command execution error."""
    pass


# =====================================
# Configuration Exceptions
# =====================================
class ConfigError(KeibaYosouError):
    """Configuration related error."""
    pass


class MissingEnvironmentVariableError(ConfigError):
    """Required environment variable is not set."""
    def __init__(self, var_name: str):
        self.var_name = var_name
        super().__init__(f"Environment variable '{var_name}' is not set")
