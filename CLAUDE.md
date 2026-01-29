# CLAUDE.md - keiba-yosou Project Instructions

## Project Overview

Horse racing prediction system using JRA-VAN official data with machine learning (XGBoost + LightGBM + CatBoost ensemble).
Provides predictions combining data analysis and statistical methods.

## Repository Info

- **Remote**: https://github.com/raveuptonight/keiba-yosou
- **Branch Strategy**: main (production), develop (development), feature/* (feature development)

### Git Rules

- `git pull` before starting work
- Commit in small functional units
- Commit messages can be in Japanese or English
- Verify functionality before pushing

## Documentation

| File | Contents |
|------|----------|
| `README.md` | Project overview, quick start, architecture |
| `README_USAGE.md` | Detailed usage guide, API reference |
| `docs/PROJECT_OVERVIEW.md` | System config, directory structure |
| `docs/JRA_VAN_SPEC.md` | JRA-VAN data spec, tables, SQL examples |

## Tech Stack

- **Language**: Python 3.11+
- **DB**: PostgreSQL (via mykeibadb)
- **Data**: JRA-VAN Data Lab.
- **ML**: XGBoost + LightGBM + CatBoost (ensemble)
- **Env**: WSL2 + VS Code + Docker

## Directory Structure

```
keiba-yosou/
├── CLAUDE.md                    # This file
├── docs/                        # Documentation
├── src/
│   ├── api/                     # FastAPI REST API
│   │   ├── routes/              # API endpoints
│   │   └── schemas/             # Pydantic models
│   ├── db/                      # Database connections
│   │   └── queries/             # SQL queries
│   ├── discord/                 # Discord Bot
│   ├── features/                # Feature extraction
│   │   └── extractors/          # Modular extractors (db_queries, calculators)
│   ├── models/                  # ML models
│   │   └── feature_extractor/   # FastFeatureExtractor modules
│   ├── scheduler/               # Scheduled tasks
│   │   ├── result/              # Result analysis (db_operations, analyzer, notifier)
│   │   └── retrain/             # Model retraining (trainer, evaluator, manager, notifier)
│   └── services/                # Business logic
│       └── prediction/          # Prediction modules (ml_engine, bias_adjustment, etc.)
├── models/                      # Trained model files
│   ├── ensemble_model_latest.pkl
│   └── backup/
├── scripts/                     # Utilities
├── tests/                       # Tests
└── requirements.txt
```

## Current System Features

1. **Ensemble Model**: XGBoost + LightGBM + CatBoost with optimized weights
2. **Calibrated Probabilities**: Isotonic regression for reliable probability outputs
3. **EV-based Recommendations**: Expected Value >= 1.5 threshold for betting
4. **Axis Horse**: Highest place probability for wide/exacta strategies
5. **Automated Predictions**: Discord Bot, 30 minutes before race
6. **Weekly Retraining**: Tuesday 23:00 JST with automatic deployment if improved

## Coding Standards

### Python

- Formatter: black
- Linter: ruff
- Type hints: Recommended
- Docstring: Google style (English)

### Naming Conventions

- Files: snake_case
- Classes: PascalCase
- Functions/Variables: snake_case
- Constants: UPPER_SNAKE_CASE

### Import Order

```python
# Standard library
import os
from datetime import datetime

# Third-party
import pandas as pd
import xgboost as xgb

# Local
from src.db.connection import get_db
```

## DB Connection

### Local PostgreSQL

```
Host: localhost (or DB_HOST env var)
Port: 5432
Database: keiba_db
User: postgres
```

Password managed in `.env` (see .env.example)

### Connection Test

```bash
psql -U postgres -d keiba_db -c "SELECT version();"
```

## Common Commands

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/

# Format code
black src/

# Lint
ruff check src/

# Train model
python -m src.models.fast_train

# Start API server
python -m src.api.main

# Start Discord Bot
python -m src.discord.bot
```

## Docker Commands

```bash
# Start all containers
docker-compose up -d

# Check logs
docker-compose logs -f keiba-ml-trainer

# Rebuild
docker-compose down && docker-compose up -d --build
```

## Important Notes

1. **JV-Link is Windows-only** - Use mykeibadb for data access in WSL
2. **Initial data import takes days** - Full data from 1986
3. **Never commit .env** - Check .gitignore
4. **JRA-VAN data redistribution prohibited** - License restriction

## Troubleshooting

- Table names unknown → `\dt` for table list
- Column names unknown → `\d table_name` for structure
- JRA-VAN spec → see `docs/JRA_VAN_SPEC.md`
- API issues → check `docker-compose logs keiba-api`
- Model issues → `python -m src.models.fast_train` to retrain
