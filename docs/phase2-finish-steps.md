# How to Finish Phase 2 (Step-by-Step)

Phase 2 is about getting your **database and migrations** fully working. Right now the code is in place, but the **migration file** that tells the database how to create all the tables has not been created yet. These steps create that file and apply it.

---

## What You Need Before Starting

- **Docker Desktop** running (so Postgres is up).
- **Terminal** open (same place you run `docker compose up`).

---

## Step 1: Start the App (If It’s Not Already Running)

You need the backend and database containers running so Alembic can talk to Postgres.

1. Open Terminal.
2. Go to your project folder:
   ```bash
   cd /Users/aleksavucak/Desktop/tradecore
   ```
3. Start everything:
   ```bash
   docker compose up -d
   ```
   (`-d` means “in the background.”)

4. Wait until the containers are up (usually 10–20 seconds). You can check with:
   ```bash
   docker compose ps
   ```
   You should see `backend`, `postgres`, `redis`, `frontend`, and `worker` with state “Up.”

---

## Step 2: Create the Migration File (Describe the Tables)

A **migration** is a small script that says “create this table” or “add this column.” We use Alembic to **generate** the first migration from your Python models (User, Symbol, Candle, etc.), then **run** it so Postgres actually creates the tables.

1. In Terminal, from the project root, run:
   ```bash
   docker compose exec backend alembic revision --autogenerate -m "initial_schema"
   ```
   - `docker compose exec backend` = “run this command inside the backend container.”
   - `alembic revision --autogenerate` = “look at my models and write a new migration file.”
   - `-m "initial_schema"` = “name this migration ‘initial_schema’.”

2. You should see something like:
   ```text
   Generating /app/alembic/versions/xxxx_initial_schema.py ...  done
   ```
   That means a new file was created under `backend/alembic/versions/`.

3. **Optional:** Open that file in your editor to see the “create table” commands. You don’t need to change it unless you know what you’re doing.

---

## Step 3: Apply the Migration (Create the Tables in the Database)

Now we run that migration so Postgres creates all the tables (users, symbols, candles, strategies, backtest_runs, trades, etc.).

1. In Terminal, run:
   ```bash
   docker compose exec backend alembic upgrade head
   ```
   - `alembic upgrade head` = “run every pending migration up to the latest.”

2. You should see something like:
   ```text
   INFO  [alembic.runtime.migration] Running upgrade  -> xxxx, initial_schema
   ```
   No error = Phase 2 migrations are done.

3. **Check:** Open http://localhost:8000/ready in your browser. You should see:
   ```json
   {"status": "ready"}
   ```
   That means the app can reach both Postgres and Redis.

---

## Step 4 (Optional): Add BTC and ETH to the Symbols Table

Your app has a “symbols” table. For market data and backtests you’ll want rows for BTC and ETH. There’s a small script that inserts them if they’re missing.

**Option A – Run a one-off script inside the container**

1. In Terminal:
   ```bash
   docker compose exec backend python -c "
   from app.db.session import SessionLocal
   from app.scripts.seed_symbols import seed_symbols

   db = SessionLocal()
   try:
       seed_symbols(db)
       db.commit()
       print('Symbols seeded.')
   finally:
       db.close()
   "
   ```
2. You should see: `Symbols seeded.`

**Option B – Skip for now**

You can add symbols later (e.g. when you build the “ingest market data” or “create backtest” screens). Phase 2 is still complete without this.

---

## Summary Checklist

- [ ] **Step 1:** `docker compose up -d` (containers running).
- [ ] **Step 2:** `docker compose exec backend alembic revision --autogenerate -m "initial_schema"` (migration file created).
- [ ] **Step 3:** `docker compose exec backend alembic upgrade head` (tables created in Postgres).
- [ ] **Step 4 (optional):** Run the seed script to add BTCUSD and ETHUSD.

When all of the above are done (and `/ready` returns `{"status":"ready"}`), **Phase 2 is complete.** You can then move on to Phase 3 (API client + dashboard) or Phase 4 (market data ingestion).
