# keiba-yosou

Horse racing prediction system using JRA-VAN data with machine learning (XGBoost + LightGBM + CatBoost ensemble).

## Features

- **ML-based Prediction**: Ensemble model (XGBoost + LightGBM + CatBoost) with calibrated probabilities
- **Optuna Auto-Tuning**: Automatic hyperparameter optimization (30 trials, TPE sampler)
- **Surface-Specific Models**: Separate turf/dirt models for improved accuracy
- **LambdaRank Learning**: Ranking-optimized models (XGBRanker + LGBMRanker + CatBoost YetiRank)
- **Confidence Intervals**: Model disagreement-based 95% CI for win probabilities
- **Composite Ranking**: Win probability + place probability + rank score for robust ranking
- **EV-based Betting**: Expected Value (EV >= 1.5) based betting recommendations
- **Failure Analysis**: Automatic categorization of prediction misses (upset / close call / blind spot)
- **Automated Predictions**: Discord Bot with scheduled predictions 30 minutes before race
- **Weekly Model Retraining**: Automatic model updates with Optuna optimization and performance comparison

## Quick Start

### Prerequisites

- Docker & Docker Compose
- PostgreSQL (with JRA-VAN data via mykeibadb)

### One-Command Setup

```bash
# Clone repository
git clone https://github.com/raveuptonight/keiba-yosou-public.git
cd keiba-yosou-public

# Setup everything with one command
make setup
```

This will:
1. Create `.env` from template
2. Build Docker images
3. Start all services
4. Check API health

After setup, edit `.env` with your credentials:
```bash
# Edit credentials
nano .env

# Restart services
make restart
```

### Train Model

```bash
# Train the ML model
make train

# Or train in background
make train-bg
```

### Common Commands

```bash
make up          # Start services
make down        # Stop services
make logs        # View logs
make health      # Check API health
make help        # Show all commands
```

### Manual Setup (without Make)

```bash
cp .env.example .env
# Edit .env with your credentials
docker-compose up -d
```

## System Architecture

```
                    ┌──────────────────┐
                    │   Discord Bot    │
                    │   (Scheduler)    │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │    FastAPI       │
                    │   REST API       │
                    └────────┬─────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
┌────────▼────────┐ ┌────────▼────────┐ ┌────────▼────────┐
│ Prediction      │ │ Feature         │ │ Model Training  │
│ Service         │ │ Extraction      │ │ (Weekly+Optuna) │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────▼─────────┐
                    │   PostgreSQL     │
                    │   (JRA-VAN)      │
                    └──────────────────┘
```

## Directory Structure

```
keiba-yosou/
├── src/
│   ├── api/                    # FastAPI REST API
│   │   ├── routes/             # API endpoints
│   │   └── schemas/            # Pydantic models
│   ├── db/                     # Database connections
│   │   └── queries/            # SQL queries
│   ├── discord/                # Discord Bot
│   ├── features/               # Feature extraction
│   │   └── extractors/         # Modular extractors
│   ├── models/                 # ML models
│   │   └── feature_extractor/  # Feature extraction modules
│   ├── scheduler/              # Scheduled tasks
│   │   ├── result/             # Result analysis & failure detection
│   │   └── retrain/            # Model retraining with Optuna
│   └── services/               # Business logic
│       └── prediction/         # Prediction modules
├── models/                     # Trained model files
├── docs/                       # Documentation
├── tests/                      # Test files
└── scripts/                    # Utility scripts
```

## Prediction Output

The system outputs:

1. **EV Recommendations** (EV >= 1.5)
   - Win bet recommendations with expected value
   - Place bet recommendations with expected value

2. **Axis Horse** (for wide/exacta bets)
   - Horse with highest place probability

3. **Confidence Intervals**
   - 95% CI based on model disagreement (XGB vs LGB vs CB)

Example Discord notification:
```
🔥 **Tokyo 11R Final Prediction**
15:25 start Japan Cup

**Win/Place Recommendations** (EV >= 1.5)
  #5 HorseName (EV W2.15/P1.65) Win: 22.1% [17.5%-26.7%]
  #3 HorseName (EV P1.52)

**Axis Horse** (for wide/exacta)
  🎯 #5 HorseName (Place rate 72%)
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/predictions/generate` | POST | Generate prediction |
| `/api/v1/races/date/{date}` | GET | Get races by date |
| `/api/v1/odds/{race_code}` | GET | Get odds for race |

## Configuration

Key environment variables:

```env
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=keiba_db
DB_USER=postgres
DB_PASSWORD=your_password

# Discord
DISCORD_BOT_TOKEN=your_token
DISCORD_NOTIFICATION_CHANNEL_ID=channel_id

# API
API_HOST=0.0.0.0
API_PORT=8000
```

## Model Training

The ensemble model uses:
- **XGBoost**: Gradient boosting (XGBRanker + XGBClassifier)
- **LightGBM**: Fast gradient boosting (LGBMRanker + LGBMClassifier)
- **CatBoost**: YetiRank + CatBoostClassifier
- **Optuna**: TPE sampler with 30 trials for hyperparameter optimization
- **Calibration**: Isotonic regression + Platt scaling blend

100+ features including:
- Horse performance stats (win rate, place rate, weighted by recency)
- Jockey/trainer statistics and recent form
- Track condition and surface preferences
- Distance/venue aptitude
- Pedigree analysis (sire stats by surface)
- Running style and pace compatibility
- Training workout data
- Corner position progression and closing ability

## Weekly Retraining

Models are automatically retrained weekly (Tuesday 23:00 JST):

1. Extract features from 4 years of race data
2. Optuna hyperparameter search (30 trials)
3. Train ranking + win/quinella/place classifiers with best params
4. Calibrate probabilities (isotonic + Platt)
5. Compare with current model using backtest
6. Deploy if improved, keep current otherwise
7. Send Discord notification with metrics and failure analysis

## Result Analysis

After each race day, the system automatically:
- Compares predictions against actual results
- Calculates EV recommendation ROI (win/place separately)
- Tracks axis horse performance (win/place/show rates)
- Categorizes prediction failures:
  - **Upset**: Longshot winner (odds >= 10x) — hard to predict
  - **Close call**: Winner was predicted 4th-5th — nearly got it
  - **Blind spot**: Winner predicted 6th+ despite low odds — model weakness
- Detects systematic weaknesses by venue/distance/surface
- Sends detailed Discord report

## License

Private - JRA-VAN data redistribution prohibited.

## Contributing

1. Create feature branch from `develop`
2. Make changes
3. Run tests: `pytest tests/`
4. Submit pull request
