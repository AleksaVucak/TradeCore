"""Sentiment scoring using VADER (Phase 17.1).

VADER is lightweight, requires no GPU, and performs well on short
financial headlines. Each headline gets a compound score in [-1, 1]
and a categorical label (positive / negative / neutral).
"""

from __future__ import annotations

from dataclasses import dataclass

from nltk.sentiment.vader import SentimentIntensityAnalyzer

_analyzer: SentimentIntensityAnalyzer | None = None


def _get_analyzer() -> SentimentIntensityAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentIntensityAnalyzer()
    return _analyzer


@dataclass(frozen=True, slots=True)
class SentimentResult:
    score: float
    label: str


def _classify(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


def score_text(text: str) -> SentimentResult:
    """Score a single headline and return compound score + label."""
    analyzer = _get_analyzer()
    scores = analyzer.polarity_scores(text)
    compound = scores["compound"]
    return SentimentResult(score=round(compound, 4), label=_classify(compound))


def score_texts(texts: list[str]) -> list[SentimentResult]:
    """Score multiple headlines in batch."""
    analyzer = _get_analyzer()
    results: list[SentimentResult] = []
    for text in texts:
        scores = analyzer.polarity_scores(text)
        compound = scores["compound"]
        results.append(SentimentResult(score=round(compound, 4), label=_classify(compound)))
    return results
