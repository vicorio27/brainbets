# BrainBets - Sports Betting Intelligence Platform

A sports analysis and prediction system for tennis and football, built on Machine Learning, automated with n8n, and visualized in real time.

---

# Goal

BrainBets is a platform designed to:

* Collect sports data automatically.
* Normalize and store sporting events.
* Generate predictions with specialized Machine Learning models.
* Validate results automatically.
* Expose information through APIs and a web dashboard.
* Allow interaction through Telegram.
* Keep a decoupled, workflow-oriented architecture.

The platform is built on one principle:

> n8n orchestrates data collection and the models. PostgreSQL is the source of truth. FastAPI only exposes information. The frontend visualizes results. The models generate predictions.

---

# Current Status and What's New

## Current accuracy (2026-06-28)

```text
Total:     60.89%
Football:  65.79%
Tennis:    33.33%
```

Football keeps an acceptable accuracy thanks to the Poisson + Elo model. Tennis now has a real XGBoost model trained on 2010-2024 historical data; its impact on accuracy will be measured over the next validation cycles.

## Latest features

- **Tennis pipeline optimizations (2026-07-01)**: Tennis event collection went from 5 to 50 events (`data_collection_db`); the live snapshot calculation in `update_scores_tennis` was fixed; batch inference for the ML model was added (`POST /api/v1/internal/predict/tennis-ml/batch`); the tennis `Prediction Engine` consumes the `features` block from `FeatureService`; player names are normalized for H2H; the `/matches/tennis/enrich` endpoint returns full stats; the tennis odds parser was improved; the event detail cache went up to 300s; and the ML model adds fatigue features while staying compatible with older models.
- **New 2025 historical data**: The 2025 ATP season was ingested from tennis-data.co.uk (2,644 matches) and La Liga 2024-25 from openfootball/Wayback Machine (380 matches). The tennis Elo, Poisson and XGBoost models were retrained with this larger dataset.
- **Real ML model for tennis (XGBoost)**: A new service, `backend/src/application/tennis_ml_service.py`, trains an XGBoost classifier on Elo, surface Elo, ranking and form features. It exposes `POST /api/v1/internal/predict/tennis-ml` for inference and is part of the ensemble in `n8n/prediction_engine/tennis.py`. Training: ~15k rows in ~10s, 99.86% test accuracy.
- **Football odds parser fix**: The `Merge Football Odds` node correctly handles the real RapidAPI response (`response.odds.odds.matchfactMarkets` / `oddsTabMarkets`) and pairs input events with odds responses by index.
- **Per-event H2H for football**: The `data_collection_db` workflow calls RapidAPI's `football-get-head-to-head?eventid={id}` for each new event and enriches the match with real H2H data. Responses are paired by index because the HTTP node does not preserve the input item's fields. The backend applies H2H only to **new** matches, so no API calls are spent on events that were already collected.
- **Tennis H2H from the historical DB**: Added `backend/src/application/tennis_stats_service.py`, which computes head-to-head records between players from finished matches in PostgreSQL. The `POST /api/v1/internal/matches/tennis/enrich` endpoint exposes H2H records as a "wins-losses" string. The `data_collection_db` workflow groups tennis events, calls the endpoint and merges `h2h` into each match before saving it. The tennis engine (`n8n/prediction_engine/tennis.py`) uses this real H2H as a feature in the XGBoost-like model.
- **Football odds**: The collection workflow calls RapidAPI's `/football-event-odds?eventid={id}&countrycode=BR` endpoint and stores the 1X2 odds (`homeOdds`, `drawOdds`, `awayOdds`). The football engine uses these normalized odds in the ensemble, with dynamic weights depending on how much real data is available.
- **Tennis odds**: The collection workflow calls RapidAPI's odds endpoint (`/api/tennis/event/{id}/odds`) and stores the odds in `match_competitors.pre_match_odds`. The tennis engine uses these normalized odds in the ensemble, with dynamic weights depending on whether real/surface Elo is available.
- **Filtering stale PENDING predictions**: The `/api/v1/predictions/history` endpoint hides PENDING predictions whose match is older than yesterday, so predictions abandoned weeks or months ago don't show up in the frontend.
- **FeatureService fix**: Fixed an indentation bug that made `POST /api/v1/internal/features/build` load every match in the database when called with only a date range, hanging the prediction pipeline.
- **n8n workflow fixes**: All workflows were re-enabled after import. `/matches/by-date` now accepts empty parameters. `update_scores` was fixed to chain `Update Football → Update Tennis → Prepare Response`. JSON is now passed to the `Prediction Engine` as base64 + a temporary file (`/tmp/predict_input.json`) to avoid errors caused by single quotes in names.
- **Internal proxy/cache**: All live score workflows (football and tennis) use `POST /api/v1/internal/proxy`, with a PostgreSQL cache and backoff on `429`.
- **Date-window validation**: Only PENDING predictions from today and yesterday are validated. Older predictions are reported as `skipped`.

## Accuracy improvement roadmap

- **Option A - Football odds** ✅: Add bookmaker odds to the football ensemble (in parallel with the tennis work).
- **Option B - Real tennis models** ✅: Train XGBoost/CatBoost on the 2010+ historical data already loaded, instead of using heuristics.
- **Option C - Better football collection** 🔄: Bring in xG, form, league position, scheduled matches and real stats instead of placeholders.

---

# Overall Architecture

```text
┌─────────────────────┐
│     Telegram Bot    │
│      (Python)       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   workflow_executor │
│   (n8n proxy only)  │
└──────────┬──────────┘
           │
           ▼
┌──────────────────────┐
│         n8n          │
│ Workflow Orchestrator│
│  + Prediction Engine │
│   (Python scripts)   │
└──────────┬───────────┘
           │
           ▼
     storage/*.json
           │
           ▼
┌──────────────────────┐
│   migration_worker   │
│ (CDC to PostgreSQL)  │
└──────────┬───────────┘
           │
           ▼
      PostgreSQL
           │
           ▼
      FastAPI (BFF)
           │
           ▼
       Vue Dashboard
```

---

# Architectural Principles

## 1. n8n is the brain of the system

All orchestration happens in n8n.

Responsibilities:

* Scraping
* Data collection
* Normalization
* Running the models
* Validation
* Notifications
* Telegram integration

n8n is the only layer allowed to coordinate processes.

---

## 2. FastAPI is read-only (public)

FastAPI does not:

* Run predictions
* Run scraping
* Modify files
* Train models

FastAPI only:

* Reads from PostgreSQL
* Exposes REST APIs
* Aggregates metrics
* Feeds the dashboard

FastAPI does expose internal endpoints (`/api/v1/internal/*`), protected with an API key, so that n8n and the `migration_worker` can write to PostgreSQL.

---

## 3. The Prediction Engine lives inside n8n

The prediction logic is implemented as Python scripts mounted inside the n8n container and orchestrated by n8n workflows.

Responsibilities:

* Per-sport inference (football and tennis)
* Scoring with Elo, Poisson, XGBoost-like and CatBoost-like models
* Model ensembles
* Generating predictions that are persisted in PostgreSQL

OpenAI receives the ensemble output and enriches each prediction's `naturalLanguageReasoning` with a betting-expert analysis in Spanish. The engine can evolve independently as long as it keeps the same JSON contract.

## 4. PostgreSQL is the source of truth

All historical and live data is stored in PostgreSQL:

* Sports, leagues, competitors (teams/players)
* Matches (scheduled, live, finished)
* Predictions and their validation results
* Rolling statistics, Elo history, feature store
* Historical data ingestion jobs

The `migration_worker` acts as CDC: it detects new JSON files in `storage/`, migrates them to PostgreSQL and deletes them after a configurable time so the disk doesn't fill up.

---

## 5. Decoupled frontend

Vue.js never accesses directly:

* Sports APIs
* OpenAI
* ML models

All access goes through FastAPI.

---

# Data Architecture

```text
Data Sources (RapidAPI, historical CSVs)
     │
     ▼
┌─────────────────────────────┐
│   n8n Collection Pipeline   │
└─────────────┬───────────────┘
              │
              ▼
       storage/matches/*.json
              │
              ▼
┌─────────────────────────────┐
│     migration_worker        │
│   (CDC filesystem → DB)     │
└─────────────┬───────────────┘
              │
              ▼
         PostgreSQL
              │
     ┌────────┴────────┐
     ▼                 ▼
Prediction Engine   Validation Pipeline
(n8n + Python)      (n8n + RapidAPI)
     │                 │
     ▼                 ▼
storage/predictions  storage/results
     │                 │
     └────────┬────────┘
              │
              ▼
       PostgreSQL
              │
              ▼
         FastAPI
              │
              ▼
          Dashboard
```

---

# Tech Stack

## Automation

* n8n
* Webhooks
* Cron Jobs

## Backend

* Python 3.12
* FastAPI
* Pydantic
* SQLAlchemy 2.0
* Alembic
* PostgreSQL

## Frontend

* Vue 3
* Vite
* TailwindCSS
* Pinia

## Machine Learning

* Scikit-Learn
* XGBoost
* CatBoost
* Elo Rating
* Poisson Models

## Infrastructure

* Docker
* Docker Compose
* Nginx
* PostgreSQL 16

---

# Project Structure

```text
brainbets/

├── docker-compose.yml

├── backend/
│   ├── alembic/               # PostgreSQL migrations
│   │   ├── versions/
│   │   ├── env.py
│   │   └── init.sql
│   ├── alembic.ini
│   ├── src/
│   │   ├── domain/            # SQLAlchemy ORM models
│   │   ├── infrastructure/    # Database, repositories, migration_worker
│   │   ├── application/       # DataService
│   │   └── presentation/      # FastAPI routers + schemas
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile

├── frontend/
│   ├── src/
│   ├── nginx.conf
│   └── Dockerfile

├── services/
│   ├── file_writer/           # Deprecated (kept for compatibility)
│   ├── workflow_executor/
│   ├── telegram_bot/
│   └── migration_worker/      # CDC to PostgreSQL (inside backend/)
│
├── n8n/
│   ├── Dockerfile
│   ├── prediction_engine/     # Python scripts executed inside n8n
│   │   ├── football.py
│   │   ├── tennis.py
│   │   ├── common.py
│   │   └── predict.py
│   └── workflows/
│       ├── data_collection_db.json
│       ├── prediction_pipeline_db.json
│       ├── validation_db.json
│       └── telegram_bot.json
│
├── schemas/
│
├── storage/                   # Temporary files before CDC
│   ├── matches/
│   ├── predictions/
│   ├── results/
│   └── audit/
│
├── scripts/                   # Admin utilities (not used by active workflows)
│
└── docs/
```

---

# Setup / Installation

## Requirements

* Docker Desktop, or Docker Engine + Docker Compose
* Git
* ~4 GB of free RAM

## Start the platform

```bash
# Clone the project, or go to its folder
cd brainbets

# Start all services
docker-compose up -d --build

# Check that every container is healthy
docker-compose ps
```

## Enable the n8n workflows (after the first start)

Workflows are imported automatically from `n8n/workflows/`, but n8n needs them to be enabled manually to register the webhooks:

```bash
# Enable all workflows via the CLI
docker exec brainbets-n8n n8n update:workflow --all --active=true

# Restart n8n so the webhooks get registered
docker restart brainbets-n8n
```

Alternatively, open http://localhost:5678 and enable each workflow with the toggle at the top right.

## Health checks

```bash
# Backend
curl http://localhost:8000/health

# Workflow executor
curl http://localhost:5001/health

# n8n
open http://localhost:5678
```

## Run the full pipeline

```bash
# Via the workflow executor
curl -X POST http://localhost:5001/execute/pipeline

# Via the Telegram Bot
# Send /pipeline to @coriousreybey_bot
```

## Database migrations

Alembic migrations run automatically when the backend starts.

To run them manually:

```bash
docker exec brainbets-backend alembic upgrade head
```

To create a new migration after changing the models:

```bash
cd backend
alembic revision --autogenerate -m "description of changes"
```

## Important environment variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL URL | `postgresql://brainbets:brainbets123@postgres:5432/brainbets` |
| `INTERNAL_API_KEY` | API key for internal endpoints | (no default; set it in `.env`) |
| `WORKER_DELETE_AFTER_MIGRATE` | Delete files after migrating them | `true` |
| `WORKER_MIN_FILE_AGE_SECONDS` | Minimum file age before deleting | `300` |
| `WORKER_POLL_INTERVAL` | CDC polling interval | `10` |

---

# Football Prediction Engine

## Goal

Generate predictions for:

* Match Winner
* Double Chance
* Over/Under
* BTTS
* Asian Handicap
* Correct Score

---

## Elo Model

Inputs:

```text
home_elo
away_elo
elo_difference
home_advantage
```

Output:

```text
home_win_probability
away_win_probability
draw_probability
```

---

## Poisson Model

Inputs:

```text
goals_scored
goals_conceded
expected_goals
expected_goals_against
```

Output:

```text
expected_goals_home
expected_goals_away
score_distribution
```

Markets:

* Correct Score
* Over/Under
* BTTS

---

## XGBoost Model

Features:

```text
elo_difference
xG
xGA
shots
corners
form
injuries
rest_days
market_odds
```

Predictions:

```text
winner
btts
over_under
asian_handicap
```

---

## Final Football Ensemble

```text
40% XGBoost
35% Poisson
25% Elo
```

Implemented in `n8n/prediction_engine/football.py` and run inside the `prediction_pipeline_db` n8n workflow.

---

# Tennis Prediction Engine

## Goal

Generate predictions for:

* Match winner
* First set winner
* Number of sets
* Total games
* Games handicap
* Correct Score
* Tie Break

---

## General Elo

Inputs:

```text
player_elo
ranking
recent_form
```

---

## Surface Elo

Inputs:

```text
clay_elo
hard_elo
grass_elo
```

---

## XGBoost

Inputs:

```text
ranking
elo
surface_elo
h2h
recent_form
aces
double_faults
break_points_saved
return_points_won
fatigue
```

---

## CatBoost

Categorical inputs:

```text
surface
country
tournament
indoor_outdoor
```

---

## Final Tennis Ensemble

```text
35% Surface Elo
25% Elo
25% XGBoost
15% CatBoost
```

Implemented in `n8n/prediction_engine/tennis.py` and run inside the `prediction_pipeline_db` n8n workflow.

---

# n8n Workflows

## 1. Data Collection

Responsibilities:

* Fetch matches
* Fetch statistics
* Fetch rankings
* Fetch odds
* Normalize data

Output:

```text
storage/matches/*.json
```

---

## 2. Prediction Pipeline

Responsibilities:

* Read matches
* Run the Prediction Engine (Python scripts inside n8n)
* Generate predictions with the model ensemble
* Send results to OpenAI to enrich the reasoning
* Persist results

Output:

```text
storage/predictions/*.json
```

Models per sport:

* **Football**: 40% XGBoost-like, 35% Poisson, 25% Elo
* **Tennis**: 35% Surface Elo, 25% Elo, 25% XGBoost-like, 15% CatBoost-like

---

## 3. Validation Pipeline

Responsibilities:

* Fetch final results
* Compare them against the predictions
* Compute accuracy
* Generate metrics

Output:

```text
storage/results/*.json
```

---

# Telegram Bot

## Mandatory Architectural Rule

The bot must NOT consume directly:

* Sports APIs
* The Prediction Engine
* FastAPI
* OpenAI

Every interaction must go through n8n.

---

## Mandatory Flow

```text
Telegram User
      │
      ▼
Telegram Bot
      │
      ▼
workflow_executor (n8n proxy)
      │
      ▼
n8n Webhook
      │
      ▼
Workflow
      │
      ▼
Telegram Response
```

---

## Initial Commands

```text
/picks
/football
/tennis
/match
/player
/stats
/help
```

---

# OpenAI

OpenAI does NOT generate predictions.

OpenAI may only be used to:

* Explain predictions
* Generate narrative analysis
* Write summaries
* Answer user questions
* Generate insights

The final probability must always come from the Prediction Engine.

---

# REST APIs

## Matches

```http
GET /api/v1/matches/latest
```

```http
GET /api/v1/matches/history
```

---

## Predictions

```http
GET /api/v1/predictions/latest
```

```http
GET /api/v1/predictions/history
```

---

## Results

```http
GET /api/v1/results/latest
```

---

## Analytics

```http
GET /api/v1/analytics/accuracy
```

```http
GET /api/v1/analytics/dashboard
```

```http
GET /api/v1/analytics/bankroll?initial=100&strategy=percent&stakePct=2&target=2&days=365
```

Bankroll simulator: a backtest over the predictions that have already been validated **and have stored odds**.
Parameters: `initial`, `strategy` (`percent` | `flat` | `kelly`), `stakePct`, `kellyMultiplier`,
`maxStakePct`, `target` (target multiple, 2 = double), `days`, `sport`, `market`,
`minConfidence`, `minEv`, `useCalibrated`, `sims`, `horizonDays`.
It returns `sample` (odds coverage), `backtest` (daily curve, yield, drawdown),
`projection` (days to reach the target), `monteCarlo` (p10/p50/p90 and probability of ruin),
`byMarket` (which markets pay, with a significance test and CLV) and `stability` (does the edge
hold up in the first vs. the second half of the history?). "Exact Set Score" is
excluded from the default universe (`PAUSED_BETTING_MARKETS`) while its redesign is being evaluated;
passing `market=Exact Set Score` explicitly still shows it, for monitoring.

```http
POST /api/v1/internal/matches/tennis/closing-odds/capture?window_hours=6
```

Internal. Captures the tennis odds right before the first serve (Closing Line Value) for
matches starting within `window_hours`, stored in
`matches.extra_data.odds_markets_closing`. Called every hour by the "Capture Closing Odds" node in
`validation_db`.

```http
POST /api/v1/internal/train/exact-score-prior
GET  /api/v1/internal/predict/tennis-exact-score-prior
```

Internal. Trains (from the whole tennis history with a final score) and serves the empirical
exact-score-by-sets prior. See `exact_score_prior_service.py` and the "Exact Set Score"
redesign section in `AGENTS.md`.

```http
GET /api/v1/internal/validate/tennis-ensemble-walkforward?cutoff_frac=0.7
```

Internal, diagnostics only (persists nothing). Fits the Match Winner ensemble weights
on the first chronological slice of the validated history, freezes them, and evaluates them on
the slice they never saw, comparing against the hardcoded constants and against the fit
on all the data (what the engine serves today). See `ensemble_walkforward_service.py` and the
`PRIOR_STRENGTH` finding in `AGENTS.md`.

---

# Roadmap

## Phase 1 (Done)

* Live data collection (RapidAPI)
* Vue.js dashboard
* Basic predictions (Elo, Poisson, XGBoost-like, CatBoost-like)
* Telegram Bot
* Migration to PostgreSQL with CDC from files

## Phase 2 (In progress)

* Automatic training on historical data (2010+)
* Feature store and retrainable models
* Advanced metrics and backtesting
* Smart alerts

## Phase 3 (Planned)

* MCP Server
* Multi-sport (NBA, MLB, eSports)
* Reinforcement Learning
* Live predictions with continuous updates
* Bankroll management and the Kelly Criterion

---

# Future Goal

Expose the Prediction Engine through an MCP Server so any AI agent can query directly:

```text
predict_football()
predict_tennis()
get_best_picks()
get_player_analysis()
```

without depending on the frontend or the dashboard.
