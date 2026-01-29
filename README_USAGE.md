# Horse Racing Prediction System - Usage Guide

**Goal: Achieve 200% ROI through EV-based betting**

## Quick Start

### 1. Environment Setup

```bash
# Start with Docker Compose
docker-compose up -d

# Or use virtual environment
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Model Training

```bash
# Fast training (recommended, ~10 minutes)
python -m src.models.fast_train

# Output: models/ensemble_model_latest.pkl
```

### 3. Generate Predictions

```bash
# Via API
curl -X POST "http://localhost:8000/api/v1/predictions/generate" \
  -H "Content-Type: application/json" \
  -d '{"race_id": "2026012506010911", "is_final": true}'
```

## Automated Predictions (Discord Bot)

The Discord Bot automatically generates predictions 30 minutes before each race.

### Notification Format

```
🔥 **Tokyo 11R Final Prediction**
15:25 start Japan Cup

**Win/Place Recommendations** (EV >= 1.5)
  #5 HorseName (EV W2.15/P1.65)
  #3 HorseName (EV P1.52)

**Axis Horse** (for wide/exacta)
  🎯 #5 HorseName (Place rate 72%)
```

### Understanding EV Recommendations

- **EV (Expected Value)** = Predicted Probability × Odds
- EV >= 1.5 means expected 50%+ profit on average
- W = Win bet EV, P = Place bet EV

### Using Axis Horse

The axis horse has the highest probability of finishing in the top 3.
Use it as:
- **Wide bets**: Combine axis horse with other candidates
- **Exacta/Trifecta**: Use axis horse as the anchor

## System Architecture

```
ML Pipeline:
  Features (100+) → XGBoost + LightGBM + CatBoost → Calibrated Probabilities
                                                           ↓
  Real-time Odds  →  EV Calculation  →  Betting Recommendations
```

### Features Used

- **Horse**: Past performance, win rate, place rate, speed index
- **Jockey/Trainer**: Stats, recent form, course/distance aptitude
- **Pedigree**: Sire/dam statistics, bloodline patterns
- **Venue**: Track condition, distance preferences
- **Race**: Field size, grade, prize money

## Weekly Model Retraining

The model automatically retrains every Tuesday at 23:00 JST:

1. **Train**: Uses latest 3 years of data
2. **Evaluate**: AUC, Brier score, Top-3 coverage, ROI
3. **Compare**: New vs current model on holdout data
4. **Deploy**: Only if new model shows improvement

Discord notification example:
```
🔄 **Weekly Model Retrain Complete**

Training samples: 150,000

📊 **Evaluation Metrics:**
Win AUC:       0.7523 🌟
Place AUC:     0.6892 ✅
Brier (win):   0.0512 🌟
Top-3 coverage: 62.5% ✅

✅ New model deployed
```

## API Reference

### Generate Prediction

```bash
POST /api/v1/predictions/generate
Content-Type: application/json

{
  "race_id": "2026012506010911",
  "is_final": true
}
```

Response includes:
- Ranked horses with probabilities
- Win/place probabilities for each horse
- EV recommendations
- Axis horse

### Get Races by Date

```bash
GET /api/v1/races/date/2026-01-25
```

### Get Odds

```bash
GET /api/v1/odds/{race_code}
```

## Result Analysis

After race day, the system analyzes prediction accuracy:

```bash
# Manually trigger result collection
docker exec keiba-ml-trainer python3 -c "
from src.scheduler.result_collector import ResultCollector
from datetime import date
collector = ResultCollector()
result = collector.collect_and_analyze(date(2026, 1, 25))
print(result)"
```

Weekend summary is automatically sent to Discord on Monday.

## Troubleshooting

### Model Not Found

```bash
# Retrain the model
python -m src.models.fast_train
```

### DB Connection Error

```bash
# Check .env file
cat .env

# Test connection
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 1;"
```

### API Health Check

```bash
curl http://localhost:8000/health
```

## EV Strategy Tips

1. **Focus on EV >= 1.5**: Higher expected returns
2. **Diversify**: Bet on multiple recommendations
3. **Track results**: Monitor actual ROI vs expected
4. **Trust the axis horse**: High place probability for stability
5. **Avoid favorite-only**: Look for value in mid-range odds

## File Locations

| File | Description |
|------|-------------|
| `models/ensemble_model_latest.pkl` | Current production model |
| `models/retrain_result_*.json` | Retraining history |
| `.env` | Environment configuration |
| `docker-compose.yml` | Container configuration |
