# Sentiment: Local Setup & Troubleshooting

Everything you need to get the sentiment pipeline running locally, verify it works, and debug common issues.

---

## 1. Prerequisites

| Requirement | How to check |
|---|---|
| Docker Desktop running | `docker compose ps` shows containers |
| Project root `.env` file | `ls .env` in the `tradecore/` folder |
| NewsAPI key | Free tier at [newsapi.org/register](https://newsapi.org/register) (100 requests/day) |

---

## 2. Environment Variables

All sentiment-related config lives in your **project root `.env`** file (not `backend/.env`).

```bash
# Required — get a free key from https://newsapi.org/register
NEWSAPI_KEY=your-key-here
```

The `.env` file is already in `.gitignore` — it will **never** be committed.

See `.env.example` for all available variables and their defaults.

---

## 3. Docker Compose Services

The sentiment pipeline uses these services:

| Service | Role |
|---|---|
| `postgres` | Stores sentiment scores, symbols, strategies |
| `redis` | Celery broker for background tasks |
| `backend` | FastAPI server — serves `/api/v1/sentiment/*` endpoints |
| `worker` | Celery worker — runs `fetch_sentiment_task` (fetch + score + store) |
| `beat` | Celery beat — schedules `refresh_all_sentiment_task` every 6 hours |
| `frontend` | Next.js UI — displays sentiment panel, filter editor |

**Start everything:**

```bash
cd /path/to/tradecore
docker compose up -d postgres redis backend worker beat frontend
```

**Verify:**

```bash
docker compose ps
# All 6 services should show "Running" (not "Exited")
```

---

## 4. Quick Verification (Step by Step)

### 4a. Run automated tests (no API key needed)

```bash
docker compose exec backend pytest tests/test_sentiment.py tests/test_sentiment_api.py tests/test_sentiment_filter.py tests/test_sentiment_golden_path.py -q
```

All tests should pass. These use mocks — they do **not** hit NewsAPI.

### 4b. Check pipeline status

Log in and check the status endpoint:

```bash
# Get a token (replace email/password with yours)
TOKEN=$(curl -s -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=YOUR_EMAIL" \
  -d "password=YOUR_PASSWORD" \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# Check pipeline health
curl -s "http://localhost:8000/api/v1/sentiment/status" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**What to look for:**

- `newsapi_key_set: true` — your key is loaded
- Each symbol shows `total_scores`, `data_age_hours`, `is_stale`

### 4c. Trigger a refresh

```bash
# Synchronous refresh (immediate result, good for debugging)
curl -s -X POST "http://localhost:8000/api/v1/sentiment/refresh?async=false" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"symbol_id": 1, "lookback_days": 7}' | python3 -m json.tool
```

**Expected output includes:**

- `fetched` — number of articles from NewsAPI
- `new` — newly stored (after dedup)
- `skipped` — duplicates filtered out
- `fetch_status` — `"ok"` if everything worked
- `duration_ms` — how long the pipeline took
- `correlation_id` — for log correlation

### 4d. Verify in the UI

1. Open `http://localhost:3000`
2. Log in and navigate to **Market Data**
3. Select a symbol — the **Sentiment Panel** should show headlines with scores
4. On a strategy page, toggle the **Sentiment Filter** editor

---

## 5. How the Pipeline Works

```
Celery Beat (every 6h)
  └→ refresh_all_sentiment_task
       └→ fetch_sentiment_task (per symbol, staggered 10s apart)
            ├→ NewsAPI: fetch headlines
            ├→ VADER: score each headline
            ├→ Dedup: skip existing headlines/URLs
            └→ Store: new SentimentScore rows in Postgres
```

**Backtest integration:**

When a strategy has `sentiment_filter` enabled, the backtest task loads
`SentimentScore` rows from the DB and passes them to the engine. The engine
gates new long entries based on the aggregate score over the configured
lookback window. Exits are never gated.

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `newsapi_key_set: false` | `NEWSAPI_KEY` not in `.env` or containers not restarted | Add key to `.env`, then `docker compose down && docker compose up -d` |
| `fetch_status: "no_api_key"` | Same as above | Same as above |
| `fetch_status: "invalid_api_key"` | Key is wrong or expired | Verify at [newsapi.org/account](https://newsapi.org/account), update `.env`, restart |
| `fetch_status: "rate_limited"` | Free tier allows 100 requests/day | Wait until the next day, or upgrade your plan |
| `fetch_status: "no_articles"` | No news found for this symbol/date range | Try a more popular symbol (BTC, ETH), or widen `lookback_days` |
| `fetch_status: "network_error"` | Container cannot reach the internet | Check Docker network settings and DNS |
| `total_scores: 0` in status | Pipeline never ran, or no articles found | Trigger a manual refresh (section 4c above) |
| `is_stale: true` | Data is older than 48 hours | Trigger a refresh; check that `worker` and `beat` are running |
| UI shows "No sentiment data yet" | No scores in DB for this symbol | Refresh data first (section 4c), then reload the page |
| UI shows 20 headlines but API says 50 | UI default display limit is 20 | Click **Load more** in the Sentiment Panel |
| Backtest unchanged with filter on | No sentiment data in the backtest date range | Ensure sentiment scores exist overlapping the backtest period |
| `LookupError: vader_lexicon` | NLTK data not downloaded in container | Rebuild: `docker compose build backend worker beat` |

---

## 7. API Quick Reference

All endpoints require `Authorization: Bearer <token>`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/sentiment/status` | Pipeline health: per-symbol counts, staleness, API key status |
| `POST` | `/api/v1/sentiment/refresh` | Trigger refresh (async by default; add `?async=false` for sync) |
| `GET` | `/api/v1/sentiment/{symbol}` | List headline scores (supports `?limit=`, `?start=`, `?end=`, `?label=`) |
| `GET` | `/api/v1/sentiment/{symbol}/aggregate` | Aggregated stats: avg score, label counts |

---

## 8. Security Reminders

> **Never commit secrets.** The `.env` file is in `.gitignore` and must stay there.

- Do **not** paste API keys, passwords, JWT tokens, or TOTP codes in chat messages, issues, pull requests, or screenshots.
- If a key is ever exposed, rotate it immediately at [newsapi.org/account](https://newsapi.org/account).
- Use `.env.example` (which **is** committed) as the template — it contains placeholder values only.
- When sharing terminal output for debugging, redact any lines containing tokens or passwords.

---

## 9. Running All Sentiment Tests (CI / Local)

A single command runs the full sentiment test suite:

```bash
docker compose exec backend pytest \
  tests/test_sentiment.py \
  tests/test_sentiment_api.py \
  tests/test_sentiment_filter.py \
  tests/test_sentiment_golden_path.py \
  -q
```

This is the same set that runs in CI on every push/PR. All tests use mocks and do not require a NewsAPI key or internet access.
