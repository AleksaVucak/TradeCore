# TradeCore

A full-stack strategy research and paper-trading platform for crypto spot markets (BTC, ETH). Features historical data ingestion, backtesting, paper trading, and ML-based market regime detection.

## Quick start

1. Copy environment file and start services:

   ```bash
   cp .env.example .env
   docker compose up --build
   ```

2. Open the app and API:

   - **Frontend:** http://localhost:3000  
   - **Backend API:** http://localhost:8000  
   - **API docs:** http://localhost:8000/docs  

3. Stop: `Ctrl+C` then `docker compose down`.

## Stack

- **Frontend:** Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui  
- **Backend:** FastAPI, SQLAlchemy, Pydantic  
- **Worker:** Celery  
- **Data:** PostgreSQL, Redis  

## Project structure

```
tradecore/
  frontend/     # Next.js app
  backend/      # FastAPI app + Celery tasks
  docker-compose.yml
  README.md
```

## Development

- Backend and frontend use volume mounts for hot reload in dev.  
- Run tests: from `backend/`, run `pytest`.

### Market data ingestion

"Load last 30 days" on the Market data page enqueues Celery tasks; the **worker** does the actual fetch and DB write. If you see "Ingestion started" but "Check candle counts" stays at 0:

1. **Ensure the worker is running:** `docker compose ps` — you should see `worker` as running. If not, start it: `docker compose up -d worker` (or `docker compose up -d` to start all services).
2. **Check worker logs:** `docker compose logs -f worker` — look for "Ingest completed" or an error (e.g. missing `httpx`, Binance timeout, DB connection). Fix any error, then trigger "Load last 30 days" again.
3. Rebuild the backend/worker image if you added dependencies: `docker compose build backend worker`.

### Migrations

Run Alembic **inside the backend container** (recommended; all deps including `psycopg2` are installed):

```bash
docker compose exec backend alembic upgrade head
```

To run migrations **on your host** instead, install backend deps and point at Postgres:

```bash
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql://tradecore:tradecore@localhost:5432/tradecore  # if Postgres is in Docker
alembic upgrade head
```
