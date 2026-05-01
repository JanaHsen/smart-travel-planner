# The World Decoded For You
### AI-Powered Smart Travel Planner

A full-stack travel planning agent that answers natural-language trip queries with personalized destination recommendations, real-time weather data, and ML-powered travel style classification — delivered through a polished chat interface and posted to Discord when complete.

---

## Architecture
User (React) → FastAPI → LangGraph Agent
├── Haiku (tool selection)
│     ├── rag_search      → pgvector (Postgres)
│     ├── live_conditions → Open-Meteo API
│     └── classify_destination → scikit-learn model
└── Sonnet (final synthesis)
↓
Postgres (users, agent_runs, tool_call_logs, embeddings)
↓
Discord Webhook (async delivery)
**Stack:**
- **Backend:** FastAPI, LangGraph, LangChain Anthropic, SQLAlchemy 2.x async, pgvector, sentence-transformers
- **Frontend:** React + Vite, Tailwind CSS, Axios, React Router
- **Database:** Postgres 16 + pgvector extension
- **Models:** Claude Haiku 4.5 (tool calls), Claude Sonnet 4.6 (synthesis), all-MiniLM-L6-v2 (embeddings)
- **Infrastructure:** Docker Compose

---

## What It Does

A user types a natural language travel query — "I want a warm beach in Southeast Asia in March, around $2,000, with great seafood." The system:

1. Runs **RAG search** across 45 destination guides (627 embedded chunks) to retrieve relevant destination knowledge
2. Calls **live conditions** to fetch real-time weather for candidate cities via Open-Meteo
3. Runs the **ML classifier** to predict each destination's dominant travel style
4. Routes all tool results to **Claude Sonnet** for final synthesis into a polished, human-readable travel plan
5. Persists the full run — query, answer, tool logs, token counts, cost — to Postgres
6. Fires a **Discord webhook** with the plan asynchronously after the response is returned

Every agent run is scoped to the authenticated user. The React frontend shows the plan in a markdown-rendered chat bubble, with a collapsible "How I planned this" trace showing which tools fired, their inputs/outputs, and the query cost.

---

## Project Structure
Smart-Travel-Planner/
├── backend/
│   ├── app/
│   │   ├── config.py          # pydantic-settings, single source of truth
│   │   ├── dependencies.py    # FastAPI Depends() — session, auth, agent
│   │   ├── main.py            # lifespan singletons, CORS, router mounting
│   │   ├── models/
│   │   │   ├── db.py          # SQLAlchemy ORM models
│   │   │   └── schemas.py     # Pydantic request/response schemas
│   │   ├── routes/
│   │   │   ├── auth.py        # register, login
│   │   │   └── trips.py       # plan, history, run detail
│   │   ├── services/
│   │   │   ├── agent.py       # LangGraph agent, dual-model routing
│   │   │   ├── rag.py         # pgvector cosine similarity search
│   │   │   └── webhook.py     # Discord delivery, fire-and-forget
│   │   ├── tools/
│   │   │   ├── classify_destination.py
│   │   │   ├── live_conditions.py
│   │   │   └── rag_search.py
│   │   └── utils/
│   │       ├── logging.py     # structlog JSON configuration
│   │       └── retry.py       # tenacity async retry decorator
│   ├── rag/
│   │   ├── documents/         # 15 destinations × 3 .md files each
│   │   ├── chunking.py        # recursive character splitter
│   │   ├── embeddings.py      # sentence-transformers singleton
│   │   ├── ingest.py          # chunk → embed → bulk insert pipeline
│   │   └── run_ingest.py      # CLI entry point
│   ├── models/
│   │   ├── destination_classifier.joblib
│   │   └── destination_classifier_meta.json
│   ├── tests/
│   │   └── test_rag_retrieval.py
│   ├── alembic.ini
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── api/client.js
│       ├── components/
│       │   ├── ChatInterface.jsx
│       │   ├── ProtectedRoute.jsx
│       │   └── ToolTrace.jsx
│       ├── context/AuthContext.jsx
│       └── pages/
│           ├── ChatPage.jsx
│           ├── HistoryPage.jsx
│           ├── LoginPage.jsx
│           └── SignupPage.jsx
├── docker-compose.yml
└── .env.example
---

## Getting Started

### Prerequisites

- Docker Desktop (running)
- Python 3.12+
- Node.js 18+
- An Anthropic API key

### 1 — Clone and configure

```bash
git clone https://github.com/JanaHsen/smart-travel-planner.git
cd smart-travel-planner
Copy the root env template and fill in your values:

```bash
cp .env.example .env
```

Required values in `.env`:
ANTHROPIC_API_KEY=your_key_here
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/travel_planner
JWT_SECRET=at-least-32-random-characters-here
DISCORD_WEBHOOK_URL=your_discord_webhook_url  # optional

Copy the backend env template (for local development):

```bash
cp backend/.env.example backend/.env
```

Set `DATABASE_URL` in `backend/.env` to use `localhost` instead of `postgres`:
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/travel_planner

### 2 — Start Postgres

```bash
docker compose up -d postgres
```

### 3 — Set up the Python environment

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
pip install "pydantic[email]"
```

### 4 — Run migrations

```bash
alembic upgrade head
```

### 5 — Ingest the RAG documents

```bash
python -m rag.run_ingest
```

This loads the embedding model, chunks all 45 destination guides, and bulk-inserts 627 embeddings into Postgres. Takes about 30 seconds on first run (model download ~90MB).

### 6 — Start the backend

```bash
uvicorn app.main:app --reload --port 8000
```

Watch for `startup_complete` in the logs. The ML model loads automatically from `models/destination_classifier.joblib`.

### 7 — Start the frontend

```bash
cd ../frontend
npm install
npm run dev -- --port 3000
```

Open `http://localhost:3000`. Register an account and start planning.

---

## RAG System

### Documents

45 `.md` files covering 15 destinations across all 6 travel style categories:

| Destination | Style |
|---|---|
| Kyoto, Japan | Culture |
| Chiang Mai, Thailand | Budget / Culture |
| Patagonia, Argentina | Adventure |
| Amalfi Coast, Italy | Luxury / Relaxation |
| Queenstown, New Zealand | Adventure |
| Marrakech, Morocco | Culture / Budget |
| Maldives | Luxury / Relaxation |
| Costa Rica | Adventure / Family |
| Barcelona, Spain | Culture / Family |
| Iceland | Adventure |
| Bali, Indonesia | Budget / Relaxation |
| Santorini, Greece | Luxury / Relaxation |
| Peru (Cusco / Machu Picchu) | Adventure / Culture |
| Tanzania (Serengeti) | Adventure / Luxury |
| Portugal (Lisbon) | Budget / Culture |

Each destination has three documents: `_overview.md`, `_activities.md`, `_practical.md`.

### Chunking rationale

- **Chunk size: 512 characters** (~100–150 tokens at the typical 4 chars/token ratio for English prose). Well within all-MiniLM-L6-v2's 256-token context window. Travel documents are descriptive — 512 chars typically spans one coherent topic segment.
- **Overlap: 64 characters** (~12–16 tokens). Carries the tail of each chunk into the next so that sentences split at a boundary remain retrievable from either side.
- **Splitting priority:** paragraph breaks → line breaks → sentence endings → clause boundaries → spaces → characters. Larger semantic units are preserved first.

### Retrieval strategy

Cosine similarity via pgvector's `<=>` operator. `score = 1 − cosine_distance` so higher scores are better. Default `top_k=5` in the agent tool.

### Retrieval test results

Six hand-written queries tested before agent integration:

| Query | Top result | Score |
|---|---|---|
| Wildlife safari and big game viewing in Africa | tanzania/tanzania_activities.md | 0.745 |
| Temples and different cultures in Asia | bali/bali_activities.md | 0.603 |
| Warm beach with good weather and good prices | barcelona/barcelona_overview.md | 0.537 |
| Budget backpacking nightlife and street food | costa_rica/costa_rica_overview.md | 0.537 |
| Long trail hiking and watching volcanoes | santorini/santorini_activities.md | 0.534 |
| Luxury overwater bungalows and honeymoon resorts | bali/bali_overview.md | 0.534 |

Strong results for specific vocabulary (safari, temples). The budget/backpacking query returns acceptable but not optimal results — the agent's query-rewriting step compensates by narrowing to destination-specific vocabulary before calling the tool.

---

## ML Classifier

### Overview

A scikit-learn classifier that predicts the dominant travel style of a destination from 30 numeric features. Used by the agent's `classify_destination` tool.

- **Model:** Logistic Regression with L2 regularization, `class_weight='balanced'`
- **Pipeline:** `StandardScaler → LogisticRegression` — preprocessing inside the pipeline prevents leakage
- **Dataset:** 1,078 destinations, labeled by hand

### Classes

| Class | Training rows |
|---|---|
| Adventure | 189 |
| Culture | 178 |
| Relaxation | 154 |
| Nightlife | 127 |
| Eco-Tourism | 124 |
| Family | 40 |
| Budget | 36 |
| Luxury | 14 |

The brief specified 6 classes. Two additional styles — Nightlife and Eco-Tourism — emerged naturally from the dataset with sufficient representation to justify inclusion.

### Labeling rules

- **Adventure:** high hiking trails, extreme sports operators, topographic elevation
- **Culture:** high museum/gallery count, historical monuments, UNESCO sites within 50km
- **Relaxation:** high spa/wellness centers, resort density, coastal/lakeside proximity
- **Nightlife:** high noise/light pollution index, walkability, Michelin restaurant density
- **Eco-Tourism:** high outdoor/indoor attraction ratio, national park proximity, low pollution
- **Family:** high family-hotel ratio, theme parks/zoos, healthcare quality index
- **Budget:** low cost-of-living index, low hostel and meal rates
- **Luxury:** high 5-star hotel rates, luxury boutique density, Michelin density

### Model comparison (5-fold stratified CV)

| Model | Accuracy | Macro F1 |
|---|---|---|
| **Logistic Regression** | **0.596 ± 0.015** | **0.589 ± 0.029** |
| Gradient Boosting | 0.609 ± 0.030 | 0.576 ± 0.044 |
| Random Forest | 0.593 ± 0.018 | 0.560 ± 0.045 |

Logistic Regression won on macro F1 with the lowest variance. Gradient Boosting led on raw accuracy but trailed on macro F1 — its lack of native `class_weight` support caused it to under-recall minority classes.

### Hyperparameter tuning

Grid search over `C ∈ {0.01, 0.1, 1, 10, 100}` and `penalty ∈ {l1, l2}`. Best: `C=1, penalty=l2`, macro F1 = 0.589.

### Final test set results (held-out 20%)

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| Adventure | 1.000 | 1.000 | 1.000 | 48 |
| Culture | 0.974 | 0.841 | 0.902 | 44 |
| Family | 0.588 | 1.000 | 0.741 | 10 |
| Budget | 0.462 | 0.667 | 0.545 | 9 |
| Luxury | 0.500 | 0.500 | 0.500 | 4 |
| Eco-Tourism | 0.212 | 0.226 | 0.219 | 31 |
| Nightlife | 0.263 | 0.312 | 0.286 | 32 |
| Relaxation | 0.360 | 0.237 | 0.286 | 38 |
| **Macro avg** | **0.545** | **0.598** | **0.560** | **216** |

CV → test gap: 0.589 → 0.560 (Δ 0.029). No overfitting.

**Known limitation:** Eco-Tourism, Nightlife, and Relaxation form a symmetric confusion triangle — each correctly identified ~30–35% of the time. This is a feature separability ceiling, not a class imbalance problem. Resolving it would require new features that distinguish spa-driven, outdoor, and urban downtime — a data problem, not a modeling one.

---

## Agent Design

### Dual-model routing

- **Claude Haiku 4.5** handles all tool selection and argument extraction. Cheap, fast, runs multiple turns per query.
- **Claude Sonnet 4.6** handles final synthesis only — one call per query, after all tools have returned.

### Tool allowlist

```python
ALLOWED_TOOLS = frozenset({"rag_search", "classify_destination", "live_conditions"})
```

Any tool name the LLM invents that is not in this set is refused and the LLM is told which tools are available.

### Cost per query

Based on observed runs during development:

| Component | Tokens | Cost |
|---|---|---|
| Haiku (4–6 turns, tool calls) | ~12,000 input + 1,500 output | ~$0.016 |
| Sonnet (synthesis, 1 call) | ~5,000 input + 2,000 output | ~$0.045 |
| **Total per query** | | **~$0.05–0.08** |

Token usage and cost are logged per run and stored in `agent_runs.estimated_cost_usd`.

### Failure isolation

- Tools return structured `ToolError` objects instead of raising exceptions — the agent loop continues and the LLM reasons about the failure
- Webhook failure is logged and never surfaces to the user-facing response
- Two separate DB sessions per request: one for the agent's read-only tool queries, one for the persistence write — prevents session state corruption across the agent's long synthesis call

---

## Engineering Standards

This project applies the engineering standards from the AIE Bootcamp companion guide throughout:

| Standard | Implementation |
|---|---|
| Async all the way down | All routes, tools, DB calls, LLM SDK calls use async |
| Dependency injection | Every dependency declared with `Depends()` — no globals |
| Lifespan singletons | Engine, embedder, ML model, LLM clients all load once on startup |
| Caching | `lru_cache` on settings; TTL cache (600s) on weather responses |
| pydantic-settings | Single `Settings` class, `extra="forbid"`, typed and validated |
| Pydantic at boundaries | Every HTTP body, tool input, and LLM output has a Pydantic model |
| Errors / retries | `tenacity` with exponential backoff; structured `ToolError` returns |
| Code hygiene | Modular layout, `structlog` JSON logging, `ruff` linting |

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `DATABASE_URL` | Yes | asyncpg connection string |
| `JWT_SECRET` | Yes | Min 32 chars, used to sign JWTs |
| `JWT_ALGORITHM` | No | Default: `HS256` |
| `JWT_EXPIRY_HOURS` | No | Default: `24` |
| `CHEAP_MODEL` | No | Default: `claude-haiku-4-5-20251001` |
| `STRONG_MODEL` | No | Default: `claude-sonnet-4-6` |
| `EMBEDDING_MODEL` | No | Default: `all-MiniLM-L6-v2` |
| `WEATHER_URL` | No | Default: Open-Meteo forecast endpoint |
| `WEATHER_CACHE_TTL` | No | Default: `600` seconds |
| `DISCORD_WEBHOOK_URL` | No | Leave empty to disable webhook |

---

## Running with Docker

To run the full stack (backend + frontend + Postgres) with one command:

```bash
docker compose up --build
```

The backend builds from `backend/Dockerfile`. The frontend builds from `frontend/Dockerfile`. Postgres data persists in the `pgdata` named volume.

**Note:** on first run after a fresh volume, you still need to run migrations and ingestion manually:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m rag.run_ingest
```

---

*Built during the AIE Bootcamp Week 4 project — Hasan's cohort.*
