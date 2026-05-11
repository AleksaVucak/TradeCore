"""Sentiment filter resolver (Phase 17.3).

This module provides the runtime helpers the backtest engines call to decide
whether to allow a new long entry at a given candle, given an optional
``SentimentFilterConfig`` and a pre-loaded history of sentiment scores.

Key design properties:

* **No look-ahead.** The aggregate window for any candle ``c`` only contains
  sentiment rows whose ``published_at`` is strictly before ``c.timestamp``.
* **Pure / stateless.** No DB access here.  The DB loader is exposed separately
  so the backtest task / API can load once and slice many times cheaply.
* **Backwards compatible.** Engines treat ``None`` config / empty samples as
  "no filter" and behave exactly as before.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:  # avoid runtime SQLAlchemy import for the engines
    from sqlalchemy.orm import Session

from app.schemas.strategy_config import SentimentFilterConfig


@dataclass(frozen=True, slots=True)
class SentimentSample:
    """A single point of sentiment data used by the gate.

    Only the fields the resolver needs.  Comes from
    ``app.models.sentiment_score.SentimentScore`` rows.
    """

    published_at: datetime
    score: float
    label: str


@dataclass(frozen=True, slots=True)
class SentimentDecision:
    """Result of evaluating the sentiment gate for one candle."""

    allow_long: bool
    avg_score: float | None
    samples_used: int
    reason: str


def _ensure_utc(dt: datetime) -> datetime:
    """Return *dt* normalized to UTC-aware (naive inputs are assumed UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_sentiment_history(
    db: "Session",
    *,
    symbol_id: int,
    start: datetime,
    end: datetime,
) -> list[SentimentSample]:
    """Load sentiment rows for *symbol_id* between *start* and *end* inclusive.

    Returned list is sorted ascending by ``published_at`` so binary search
    can be used by :func:`evaluate_sentiment_gate`.

    *start*/*end* may be naive — they are coerced to UTC-aware here.
    """
    from app.models.sentiment_score import SentimentScore

    s = _ensure_utc(start)
    e = _ensure_utc(end)

    rows = (
        db.query(
            SentimentScore.published_at,
            SentimentScore.score,
            SentimentScore.label,
        )
        .filter(
            SentimentScore.symbol_id == symbol_id,
            SentimentScore.published_at >= s,
            SentimentScore.published_at <= e,
        )
        .order_by(SentimentScore.published_at.asc())
        .all()
    )
    return [
        SentimentSample(
            published_at=_ensure_utc(r[0]),
            score=float(r[1]),
            label=str(r[2]),
        )
        for r in rows
    ]


def _select_window(
    samples: Sequence[SentimentSample],
    *,
    as_of: datetime,
    lookback_hours: int,
) -> list[SentimentSample]:
    """Return samples published in ``[as_of - lookback, as_of)``.

    Uses binary search since *samples* is sorted ascending by published_at.
    The right bound is **strictly less than** ``as_of`` to avoid look-ahead.
    """
    if not samples:
        return []

    as_of_utc = _ensure_utc(as_of)
    window_start = as_of_utc - timedelta(hours=lookback_hours)

    timestamps = [s.published_at for s in samples]
    left_idx = bisect_left(timestamps, window_start)
    right_idx = bisect_left(timestamps, as_of_utc)
    return list(samples[left_idx:right_idx])


def evaluate_sentiment_gate(
    samples: Sequence[SentimentSample],
    *,
    as_of: datetime,
    config: SentimentFilterConfig | None,
) -> SentimentDecision:
    """Decide whether a new long entry is allowed at *as_of*.

    Returns a :class:`SentimentDecision` with rich diagnostics so callers
    (engine logs, future UI) can surface *why* an entry was blocked.

    Behavior contract:

    * If *config* is ``None`` or ``config.enabled is False``: always allow.
    * Otherwise gather the window's samples (strictly before *as_of*) and
      apply *config.mode*.
    * If fewer than ``min_samples`` are available, return ``allow_when_missing``.
    """
    if config is None or not config.enabled:
        return SentimentDecision(
            allow_long=True,
            avg_score=None,
            samples_used=0,
            reason="filter_disabled",
        )

    window = _select_window(
        samples, as_of=as_of, lookback_hours=config.lookback_hours
    )

    if len(window) < config.min_samples:
        return SentimentDecision(
            allow_long=config.allow_when_missing,
            avg_score=None,
            samples_used=len(window),
            reason="insufficient_samples",
        )

    avg = sum(s.score for s in window) / len(window)

    if config.mode == "block_negative":
        allow = avg >= config.min_score
        reason = "avg_above_min" if allow else "avg_below_min"
    elif config.mode == "require_positive":
        allow = avg > config.min_score
        reason = "avg_strictly_positive" if allow else "avg_not_strictly_positive"
    elif config.mode == "threshold":
        allow = config.min_score <= avg <= config.max_score
        reason = "avg_in_range" if allow else "avg_out_of_range"
    else:  # pragma: no cover - Pydantic guarantees one of the literals
        allow = True
        reason = "unknown_mode"

    return SentimentDecision(
        allow_long=allow,
        avg_score=round(avg, 6),
        samples_used=len(window),
        reason=reason,
    )


__all__ = [
    "SentimentDecision",
    "SentimentSample",
    "evaluate_sentiment_gate",
    "load_sentiment_history",
]
