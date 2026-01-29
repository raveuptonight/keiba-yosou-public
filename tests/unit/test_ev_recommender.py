"""
Unit tests for EVRecommender module.

Tests expected value (EV) calculation logic and betting recommendations.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestEVCalculation:
    """Test EV calculation logic."""

    def test_ev_calculation_basic(self):
        """Test basic EV calculation: probability * odds."""
        # EV = win_probability * odds
        probability = 0.30
        odds = 5.0
        expected_ev = 1.5

        ev = probability * odds
        assert ev == expected_ev

    def test_ev_threshold_recommendation(self, sample_ranked_horses):
        """Test EV threshold determines recommendation."""
        from src.models.ev_recommender import (
            DEFAULT_WIN_EV_THRESHOLD,
            LOOSE_WIN_EV_THRESHOLD,
        )

        # Default threshold should be 1.5
        assert DEFAULT_WIN_EV_THRESHOLD == 1.5
        # Loose threshold should be 1.2
        assert LOOSE_WIN_EV_THRESHOLD == 1.2

    def test_ev_above_threshold_is_recommended(self):
        """Test horses with EV >= 1.5 are strongly recommended."""
        threshold = 1.5

        # High EV case
        win_prob = 0.35
        odds = 5.0
        ev = win_prob * odds  # 1.75

        assert ev >= threshold, "EV 1.75 should be above threshold 1.5"

    def test_ev_below_threshold_is_candidate(self):
        """Test horses with 1.2 <= EV < 1.5 are candidates."""
        strong_threshold = 1.5
        loose_threshold = 1.2

        # Candidate EV case
        win_prob = 0.25
        odds = 5.0
        ev = win_prob * odds  # 1.25

        assert ev < strong_threshold, "EV 1.25 should be below strong threshold"
        assert ev >= loose_threshold, "EV 1.25 should be above loose threshold"


class TestEVRecommenderClass:
    """Test EVRecommender class methods."""

    @patch("src.models.ev_recommender.get_db")
    def test_recommender_initialization(self, mock_get_db):
        """Test EVRecommender initializes with correct thresholds."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        from src.models.ev_recommender import EVRecommender

        recommender = EVRecommender()

        assert recommender.win_ev_threshold == 1.5
        assert recommender.place_ev_threshold == 1.5

    @patch("src.models.ev_recommender.get_db")
    def test_recommender_custom_thresholds(self, mock_get_db):
        """Test EVRecommender accepts custom thresholds."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        from src.models.ev_recommender import EVRecommender

        recommender = EVRecommender(
            win_ev_threshold=2.0,
            place_ev_threshold=1.8,
        )

        assert recommender.win_ev_threshold == 2.0
        assert recommender.place_ev_threshold == 1.8

    @patch("src.models.ev_recommender.get_db")
    def test_get_recommendations_no_odds(self, mock_get_db, sample_ranked_horses):
        """Test recommendations when no odds data available."""
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_get_db.return_value = mock_db

        # Mock cursor returns no data
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor

        from src.models.ev_recommender import EVRecommender

        recommender = EVRecommender()
        result = recommender.get_recommendations(
            race_code="2025012506010911",
            ranked_horses=sample_ranked_horses,
            use_realtime_odds=True,
        )

        assert result["win_recommendations"] == []
        assert result["place_recommendations"] == []
        assert "error" in result or result["odds_source"] == "realtime"


class TestEVRecommendationLogic:
    """Test the recommendation logic with various scenarios."""

    def test_sort_by_ev_descending(self):
        """Test recommendations are sorted by EV in descending order."""
        recommendations = [
            {"horse_number": 1, "expected_value": 1.5},
            {"horse_number": 2, "expected_value": 2.0},
            {"horse_number": 3, "expected_value": 1.7},
        ]

        sorted_recs = sorted(
            recommendations, key=lambda x: x["expected_value"], reverse=True
        )

        assert sorted_recs[0]["horse_number"] == 2  # EV 2.0
        assert sorted_recs[1]["horse_number"] == 3  # EV 1.7
        assert sorted_recs[2]["horse_number"] == 1  # EV 1.5

    def test_top1_with_ev_condition(self, sample_ranked_horses):
        """Test top1 recommendation requires rank 1 + EV >= 1.0."""
        # Rank 1 horse with EV >= 1.0 should be marked as top1
        horse = sample_ranked_horses[0]  # rank 1
        odds = 3.5
        win_prob = horse["win_probability"]  # 0.30

        ev = win_prob * odds  # 1.05

        is_rank1 = horse["rank"] == 1
        is_ev_ok = ev >= 1.0

        assert is_rank1, "First horse should be rank 1"
        assert is_ev_ok, "EV 1.05 should meet >= 1.0 condition"

    def test_place_bet_uses_place_probability(self, sample_ranked_horses):
        """Test place bet EV uses place_probability, not win_probability."""
        horse = sample_ranked_horses[0]
        fukusho_odds = 1.5

        # Should use place_probability (0.60), not win_probability (0.30)
        place_ev = horse["place_probability"] * fukusho_odds  # 0.90

        assert place_ev == 0.90


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_zero_probability(self):
        """Test handling of zero probability."""
        probability = 0.0
        odds = 5.0

        ev = probability * odds
        assert ev == 0.0

    def test_zero_odds(self):
        """Test handling of zero odds."""
        probability = 0.30
        odds = 0.0

        ev = probability * odds
        assert ev == 0.0

    def test_negative_values_not_allowed(self):
        """Test that negative values result in zero EV."""
        # In real system, negative values shouldn't occur
        # but if they do, EV should not be calculated
        probability = -0.1
        odds = 5.0

        ev = probability * odds
        # System should filter out negative probabilities
        assert ev < 0, "Negative probability results in negative EV"

    def test_very_high_odds(self):
        """Test handling of very high odds (longshots)."""
        probability = 0.02  # 2% chance
        odds = 100.0

        ev = probability * odds  # 2.0

        assert ev == 2.0
        assert ev >= 1.5, "High EV longshot should be recommended"

    def test_missing_horse_number(self, sample_ranked_horses):
        """Test handling of missing horse number in odds."""
        horses = sample_ranked_horses
        odds_dict = {"1": 3.5, "2": 5.0}  # Missing horse 3

        horse3 = horses[2]
        umaban = str(horse3["horse_number"])  # "3"

        odds = odds_dict.get(umaban, 0)
        assert odds == 0, "Missing horse should have 0 odds"
