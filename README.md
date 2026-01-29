# keiba-yosou

Horse racing prediction system using JRA-VAN data with machine learning (XGBoost + LightGBM + CatBoost ensemble).

## Features

- **ML-based Prediction**: Ensemble model (XGBoost + LightGBM + CatBoost) with calibrated probabilities
- **EV-based Betting**: Expected Value (EV) based betting recommendations
- **Automated Predictions**: Discord Bot with scheduled predictions 30 minutes before race
- **Weekly Model Retraining**: Automatic model updates with performance comparison
- **Real-time Odds Integration**: Uses latest odds for EV calculations

## Quick Start

### Prerequisites

- Docker & Docker Compose
- PostgreSQL (with JRA-VAN data via mykeibadb)
- NVIDIA GPU (recommended for training)

### One-Command Setup

```bash
# Clone repository
git clone https://github.com/raveuptonight/keiba-yosou.git
cd keiba-yosou

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
# Train the ML model (~10 minutes)
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
│ Service         │ │ Extraction      │ │ (Weekly)        │
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
│   │   ├── result/             # Result analysis
│   │   └── retrain/            # Model retraining
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

Example Discord notification:
```
🔥 **Tokyo 11R Final Prediction**
15:25 start Japan Cup

**Win/Place Recommendations** (EV >= 1.5)
  #5 HorseName (EV W2.15/P1.65)
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
- **XGBoost**: Gradient boosting
- **LightGBM**: Fast gradient boosting
- **CatBoost**: Categorical feature handling

Features include:
- Horse performance stats (win rate, place rate)
- Jockey/trainer statistics
- Track condition preferences
- Distance/surface aptitude
- Pedigree analysis
- Recent form

## Weekly Retraining

Models are automatically retrained weekly (Tuesday 23:00 JST):

1. Train new model with latest data
2. Compare with current model using backtest
3. Deploy if improved, keep current otherwise
4. Send Discord notification with metrics

## License

Private - JRA-VAN data redistribution prohibited.

## Contributing

1. Create feature branch from `develop`
2. Make changes
3. Run tests: `pytest tests/`
4. Submit pull request
