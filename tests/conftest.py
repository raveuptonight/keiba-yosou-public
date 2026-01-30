"""
Shared pytest fixtures for keiba-yosou tests.

Provides common fixtures for database mocking, API client, and sample data.
"""

import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Dict, List, Any

# Set mock mode for tests
os.environ["DB_MODE"] = "mock"


# =============================================================================
# Database Fixtures
# =============================================================================


@pytest.fixture
def mock_db_connection():
    """Mock synchronous database connection."""
    with patch("src.db.connection.get_db") as mock:
        mock_instance = MagicMock()
        mock_conn = MagicMock()
        mock_instance.get_connection.return_value = mock_conn
        mock.return_value = mock_instance
        yield mock_conn


@pytest.fixture
def mock_async_db_connection():
    """Mock asynchronous database connection."""
    with patch("src.db.async_connection.get_connection") as mock:
        mock_conn = AsyncMock()
        mock.return_value.__aenter__.return_value = mock_conn
        yield mock_conn


# =============================================================================
# API Client Fixtures
# =============================================================================


@pytest.fixture
def api_client():
    """FastAPI test client with mocked database."""
    from fastapi.testclient import TestClient

    # Mock async database functions before importing app
    with patch("src.db.async_connection.init_db_pool", new_callable=AsyncMock), \
         patch("src.db.async_connection.close_db_pool", new_callable=AsyncMock), \
         patch("src.db.async_connection.get_connection") as mock_get_conn:

        # Setup mock connection context manager
        mock_conn = AsyncMock()
        mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

        from src.api.main import app

        with TestClient(app) as client:
            yield client


@pytest.fixture
def async_api_client():
    """Async FastAPI test client."""
    from httpx import AsyncClient, ASGITransport
    from src.api.main import app

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# =============================================================================
# Sample Data Fixtures
# =============================================================================


@pytest.fixture
def sample_race_data() -> Dict[str, Any]:
    """Sample race data for testing."""
    return {
        "race_id": "2025012506010911",
        "race_name": "アメリカジョッキークラブカップ",
        "race_number": 11,
        "track_code": "06",  # Nakayama
        "distance": 2200,
        "surface": "turf",
        "horses": [
            {
                "horse_number": 1,
                "horse_name": "テスト馬1",
                "horse_id": "2019100001",
                "jockey_name": "テスト騎手1",
                "trainer_name": "テスト調教師1",
                "weight": 57.0,
            },
            {
                "horse_number": 2,
                "horse_name": "テスト馬2",
                "horse_id": "2019100002",
                "jockey_name": "テスト騎手2",
                "trainer_name": "テスト調教師2",
                "weight": 55.0,
            },
            {
                "horse_number": 3,
                "horse_name": "テスト馬3",
                "horse_id": "2019100003",
                "jockey_name": "テスト騎手3",
                "trainer_name": "テスト調教師3",
                "weight": 54.0,
            },
        ],
    }


@pytest.fixture
def sample_ranked_horses() -> List[Dict[str, Any]]:
    """Sample prediction ranked horses."""
    return [
        {
            "rank": 1,
            "horse_number": 1,
            "horse_name": "テスト馬1",
            "win_probability": 0.30,
            "place_probability": 0.60,
            "ml_score": 0.85,
        },
        {
            "rank": 2,
            "horse_number": 2,
            "horse_name": "テスト馬2",
            "win_probability": 0.20,
            "place_probability": 0.50,
            "ml_score": 0.70,
        },
        {
            "rank": 3,
            "horse_number": 3,
            "horse_name": "テスト馬3",
            "win_probability": 0.15,
            "place_probability": 0.40,
            "ml_score": 0.55,
        },
    ]


@pytest.fixture
def sample_odds_data() -> Dict[str, Dict[str, float]]:
    """Sample odds data for EV testing."""
    return {
        "tansho": {
            "1": 3.5,   # Win odds for horse 1
            "2": 5.0,   # Win odds for horse 2
            "3": 8.0,   # Win odds for horse 3
        },
        "fukusho": {
            "1": 1.5,   # Place odds for horse 1
            "2": 2.0,   # Place odds for horse 2
            "3": 2.8,   # Place odds for horse 3
        },
    }


@pytest.fixture
def sample_ev_recommendations() -> Dict[str, Any]:
    """Sample EV recommendation result."""
    return {
        "win_recommendations": [
            {
                "horse_number": 2,
                "horse_name": "テスト馬2",
                "win_probability": 0.35,
                "odds": 5.0,
                "expected_value": 1.75,
                "rank": 2,
            }
        ],
        "place_recommendations": [
            {
                "horse_number": 1,
                "horse_name": "テスト馬1",
                "place_probability": 0.60,
                "odds": 1.5,
                "expected_value": 0.90,
                "rank": 1,
            }
        ],
        "odds_source": "realtime",
        "odds_time": "2025-01-25 15:00",
    }


# =============================================================================
# Model Fixtures
# =============================================================================


@pytest.fixture
def mock_ml_model():
    """Mock ML ensemble model."""
    mock_model = MagicMock()
    mock_model.predict_proba.return_value = [
        [0.70, 0.30],  # Horse 1: 30% win prob
        [0.80, 0.20],  # Horse 2: 20% win prob
        [0.85, 0.15],  # Horse 3: 15% win prob
    ]
    return mock_model


# =============================================================================
# Environment Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_environment():
    """Reset environment variables after each test."""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch("src.settings.settings") as mock:
        mock.db_mode = "mock"
        mock.is_mock_mode = True
        mock.db_host = "localhost"
        mock.db_port = 5432
        mock.api_port = 8000
        mock.log_level = "DEBUG"
        yield mock
