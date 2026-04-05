"""Celery tasks for regime labeling and model training."""

from __future__ import annotations

from typing import Any

from app.celery_app import celery_app
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services.ml.inference import get_latest_model, label_candles

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=10)
def label_regimes_for_run_task(
    self,
    run_id: str,
    symbol_id: int,
    timeframe: str,
    start_time: str,
    end_time: str,
) -> dict[str, Any]:
    """Label regime data for the date range of a completed backtest run.

    Skipped silently when no trained model exists for the symbol+timeframe
    (regimes are opt-in; training must happen first via CLI or scheduled job).
    """
    from datetime import datetime, timezone

    def _parse_dt(dt_str: str) -> datetime:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    db = SessionLocal()
    try:
        meta = get_latest_model(db, symbol_id, timeframe)
        if meta is None:
            logger.info(
                "regime_labeling_skipped_no_model",
                run_id=run_id,
                symbol_id=symbol_id,
                timeframe=timeframe,
            )
            return {
                "status": "skipped",
                "reason": "no_trained_model",
                "run_id": run_id,
            }

        start_dt = _parse_dt(start_time)
        end_dt = _parse_dt(end_time)

        result = label_candles(
            db,
            symbol_id=symbol_id,
            timeframe=timeframe,
            start=start_dt,
            end=end_dt,
            backtest_run_id=run_id,
        )

        logger.info(
            "regime_labeling_completed",
            run_id=run_id,
            symbol_id=symbol_id,
            timeframe=timeframe,
            labeled_bars=result["labeled_bars"],
        )

        return {
            "status": "ok",
            "run_id": run_id,
            **result,
        }
    except Exception as exc:
        logger.exception(
            "regime_labeling_failed",
            run_id=run_id,
            symbol_id=symbol_id,
            timeframe=timeframe,
            error=str(exc),
        )
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {
                "status": "failed",
                "run_id": run_id,
                "error": str(exc),
            }
    finally:
        db.close()

    return {"status": "failed", "run_id": run_id}


@celery_app.task(bind=True, max_retries=1, default_retry_delay=30)
def train_regime_model_task(
    self,
    symbol_id: int,
    timeframe: str,
    start_time: str | None = None,
    end_time: str | None = None,
    tune: bool = False,
) -> dict[str, Any]:
    """Train a regime classification model in the background.

    Reports progress via update_state so the frontend can show a progress bar.
    Returns a summary dict with model_id, accuracy, etc. on success.
    """
    from datetime import datetime, timezone

    from app.services.ml.training import (
        _build_dataset,
        _fetch_candles,
        ARTIFACT_DIR,
        FEATURE_KEYS,
    )

    def _parse_dt(dt_str: str | None) -> datetime | None:
        if not dt_str:
            return None
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _progress(pct: int, phase: str) -> None:
        self.update_state(
            state="PROGRESS",
            meta={"progress_pct": pct, "phase": phase},
        )

    db = SessionLocal()
    try:
        start = _parse_dt(start_time)
        end = _parse_dt(end_time)

        _progress(5, "Fetching candles")
        candles = _fetch_candles(db, symbol_id, timeframe, start, end)
        if len(candles) < 60:
            raise ValueError(
                f"Not enough candles to train ({len(candles)}). "
                "Need at least 60 bars after filtering."
            )

        _progress(15, "Computing features and labels")
        X, y, timestamps = _build_dataset(candles)
        if len(X) < 30:
            raise ValueError(
                f"Not enough labeled samples ({len(X)}). "
                "Need at least 30 usable rows after warmup."
            )

        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score, classification_report
        from sklearn.model_selection import (
            RandomizedSearchCV,
            StratifiedKFold,
            train_test_split,
        )

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        _progress(25, "Training model" + (" with hyperparameter tuning" if tune else ""))

        tuning_info: dict[str, Any] = {}
        if tune:
            from app.services.ml.training import DEFAULT_PARAM_GRID

            base_clf = RandomForestClassifier(
                random_state=42, class_weight="balanced", n_jobs=-1
            )
            cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
            search = RandomizedSearchCV(
                base_clf,
                param_distributions=DEFAULT_PARAM_GRID,
                n_iter=30,
                cv=cv,
                scoring="f1_weighted",
                random_state=42,
                n_jobs=-1,
                refit=True,
            )
            search.fit(X_train, y_train)
            clf = search.best_estimator_

            best_params = search.best_params_
            serializable_params = {
                k: (int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
                for k, v in best_params.items()
            }
            tuning_info = {
                "tuned": True,
                "best_params": serializable_params,
                "cv_best_score": round(float(search.best_score_), 4),
                "cv_folds": 5,
                "n_iter": 30,
            }
        else:
            clf = RandomForestClassifier(
                n_estimators=200, max_depth=12, random_state=42,
                class_weight="balanced", n_jobs=-1,
            )
            clf.fit(X_train, y_train)
            tuning_info = {
                "tuned": False,
                "best_params": {"n_estimators": 200, "max_depth": 12},
            }

        _progress(80, "Evaluating model")
        y_pred = clf.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)

        _progress(90, "Saving model artifact")
        import joblib

        from app.models.ml_model_metadata import MLModelMetadata

        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        ts_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        suffix = "_tuned" if tune else ""
        filename = f"regime_rf{suffix}_{symbol_id}_{timeframe}_{ts_tag}.joblib"
        artifact_path = str(ARTIFACT_DIR / filename)
        joblib.dump({"model": clf, "feature_keys": FEATURE_KEYS}, artifact_path)

        training_start = timestamps[0] if timestamps else None
        training_end = timestamps[-1] if timestamps else None

        meta = MLModelMetadata(
            name="regime_rf",
            symbol_id=symbol_id,
            timeframe=timeframe,
            training_start=training_start,
            training_end=training_end,
            artifact_path=artifact_path,
            metrics={
                "accuracy": round(acc, 4),
                "n_train": len(y_train),
                "n_test": len(y_test),
                "classification_report": report,
                **tuning_info,
            },
        )
        db.add(meta)
        db.commit()
        db.refresh(meta)

        label_dist: dict[str, int] = {}
        for lbl in y:
            label_dist[lbl] = label_dist.get(lbl, 0) + 1

        result = {
            "model_id": meta.id,
            "artifact_path": artifact_path,
            "accuracy": round(acc, 4),
            "n_train": len(y_train),
            "n_test": len(y_test),
            "label_distribution": label_dist,
            **tuning_info,
        }

        serializable_report: dict[str, Any] = {}
        for k, v in report.items():
            if isinstance(v, dict):
                serializable_report[k] = {
                    rk: round(float(rv), 4) if isinstance(rv, float) else rv
                    for rk, rv in v.items()
                }
            else:
                serializable_report[k] = round(float(v), 4) if isinstance(v, float) else v

        _progress(100, "Complete")

        logger.info(
            "regime_model_training_completed",
            symbol_id=symbol_id,
            timeframe=timeframe,
            model_id=result["model_id"],
            accuracy=result["accuracy"],
        )

        return {
            "status": "ok",
            "model_id": result["model_id"],
            "artifact_path": result["artifact_path"],
            "accuracy": result["accuracy"],
            "n_train": result["n_train"],
            "n_test": result["n_test"],
            "label_distribution": result["label_distribution"],
            "classification_report": serializable_report,
            "tuned": result.get("tuned", False),
            "best_params": result.get("best_params"),
        }
    except Exception as exc:
        logger.exception(
            "regime_model_training_failed",
            symbol_id=symbol_id,
            timeframe=timeframe,
            error=str(exc),
        )
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {
                "status": "failed",
                "error": str(exc),
            }
    finally:
        db.close()

    return {"status": "failed"}
