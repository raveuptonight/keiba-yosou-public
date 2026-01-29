"""
Unit tests for prediction service.

Tests the prediction generation flow and result formatting.
"""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Ensure mock mode
os.environ["DB_MODE"] = "mock"


class TestMockMode:
    """Test mock mode behavior."""

    def test_is_mock_mode_returns_true(self):
        """Test _is_mock_mode returns True when DB_MODE=mock."""
        os.environ["DB_MODE"] = "mock"

        from src.services.prediction_service import _is_mock_mode

        assert _is_mock_mode() is True

    def test_is_mock_mode_returns_false(self):
        """Test _is_mock_mode returns False when DB_MODE=local."""
        os.environ["DB_MODE"] = "local"

        from src.services.prediction_service import _is_mock_mode

        assert _is_mock_mode() is False

        # Reset
        os.environ["DB_MODE"] = "mock"


class TestMockPrediction:
    """Test mock prediction generation."""

    @pytest.mark.asyncio
    async def test_generate_mock_prediction(self):
        """Test mock prediction is generated in mock mode."""
        os.environ["DB_MODE"] = "mock"

        from src.services.prediction_service import generate_prediction

        result = await generate_prediction(
            race_id="2025012506010911",
            is_final=False,
        )

        assert result is not None
        assert result.race_id == "2025012506010911"
        assert hasattr(result, "prediction_result")

    @pytest.mark.asyncio
    async def test_mock_prediction_has_ranked_horses(self):
        """Test mock prediction contains ranked horses."""
        os.environ["DB_MODE"] = "mock"

        from src.services.prediction_service import generate_prediction

        result = await generate_prediction(
            race_id="2025012506010911",
            is_final=False,
        )

        assert hasattr(result.prediction_result, "ranked_horses")
        assert len(result.prediction_result.ranked_horses) > 0


class TestPredictionResponse:
    """Test prediction response format."""

    @pytest.mark.asyncio
    async def test_prediction_response_structure(self):
        """Test prediction response has expected structure."""
        os.environ["DB_MODE"] = "mock"

        from src.services.prediction_service import generate_prediction

        result = await generate_prediction(
            race_id="2025012506010911",
            is_final=False,
        )

        # Check top-level fields
        assert hasattr(result, "race_id")
        assert hasattr(result, "race_name")
        assert hasattr(result, "prediction_result")

        # Check prediction_result fields
        pred_result = result.prediction_result
        assert hasattr(pred_result, "ranked_horses")
        assert hasattr(pred_result, "prediction_confidence")

    @pytest.mark.asyncio
    async def test_ranked_horse_fields(self):
        """Test ranked horse has required fields."""
        os.environ["DB_MODE"] = "mock"

        from src.services.prediction_service import generate_prediction

        result = await generate_prediction(
            race_id="2025012506010911",
            is_final=False,
        )

        horse = result.prediction_result.ranked_horses[0]

        assert hasattr(horse, "rank")
        assert hasattr(horse, "horse_number")
        assert hasattr(horse, "horse_name")
        assert hasattr(horse, "win_probability")
        assert hasattr(horse, "place_probability")


class TestPredictionParameters:
    """Test prediction parameter handling."""

    @pytest.mark.asyncio
    async def test_is_final_parameter(self):
        """Test is_final parameter is accepted."""
        os.environ["DB_MODE"] = "mock"

        from src.services.prediction_service import generate_prediction

        # Should not raise
        result = await generate_prediction(
            race_id="2025012506010911",
            is_final=True,
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_bias_date_parameter(self):
        """Test bias_date parameter is accepted."""
        os.environ["DB_MODE"] = "mock"

        from src.services.prediction_service import generate_prediction

        # Should not raise
        result = await generate_prediction(
            race_id="2025012506010911",
            is_final=False,
            bias_date="2025-01-25",
        )

        assert result is not None


class TestPredictionProbabilities:
    """Test probability values in predictions."""

    @pytest.mark.asyncio
    async def test_probabilities_are_valid(self):
        """Test probabilities are between 0 and 1."""
        os.environ["DB_MODE"] = "mock"

        from src.services.prediction_service import generate_prediction

        result = await generate_prediction(
            race_id="2025012506010911",
            is_final=False,
        )

        for horse in result.prediction_result.ranked_horses:
            assert 0 <= horse.win_probability <= 1
            assert 0 <= horse.place_probability <= 1

    @pytest.mark.asyncio
    async def test_ranks_are_sequential(self):
        """Test ranks are sequential starting from 1."""
        os.environ["DB_MODE"] = "mock"

        from src.services.prediction_service import generate_prediction

        result = await generate_prediction(
            race_id="2025012506010911",
            is_final=False,
        )

        horses = result.prediction_result.ranked_horses
        ranks = [h.rank for h in horses]

        # Should be [1, 2, 3, ...]
        expected = list(range(1, len(ranks) + 1))
        assert ranks == expected

    @pytest.mark.asyncio
    async def test_win_probabilities_sum_approximately_to_one(self):
        """Test win probabilities sum is close to 1.0."""
        os.environ["DB_MODE"] = "mock"

        from src.services.prediction_service import generate_prediction

        result = await generate_prediction(
            race_id="2025012506010911",
            is_final=False,
        )

        total_win_prob = sum(
            h.win_probability for h in result.prediction_result.ranked_horses
        )

        # Should be close to 1.0 (with some tolerance)
        assert 0.9 <= total_win_prob <= 1.1


class TestExportedFunctions:
    """Test module exports."""

    def test_all_exports(self):
        """Test __all__ contains expected functions."""
        from src.services import prediction_service

        expected = [
            "generate_prediction",
            "save_prediction",
            "get_prediction_by_id",
            "get_predictions_by_race",
        ]

        for func_name in expected:
            assert hasattr(prediction_service, func_name)
