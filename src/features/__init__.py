"""
Feature Generation Module

Extract features from JRA-VAN data for machine learning.

Main components:
- daily_bias: Daily bias calculation
- extractors.calculators: Feature calculation helpers
- extractors.db_queries: Database query helpers
"""

from src.features.daily_bias import DailyBiasAnalyzer, DailyBiasResult

__all__ = ["DailyBiasAnalyzer", "DailyBiasResult"]
