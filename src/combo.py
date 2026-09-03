"""
Kalshi has no native multi-leg "parlay" product -- every market is its own
single yes/no contract. This module approximates parlay-style economics by
treating several Kalshi legs as a bundle you'd buy one-by-one, and it is
only mathematically sound when the legs are genuinely independent.

Sports legs are very often NOT independent (two props from the same game,
a team's moneyline and a player's yardage total, etc). combined_probability
below multiplies probabilities as if they were independent; flag_correlated
exists specifically to catch the common ways that assumption breaks, so a
correlated bundle gets a loud warning instead of a confidently wrong number.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ComboLeg:
    ticker: str
    event_ticker: str
    title: str
    model_prob: float
    price_cents: float


@dataclass
class ComboResult:
    legs: list[ComboLeg]
    combined_model_prob: float
    combined_cost_usd: float
    combined_payout_usd: float
    independence_warning: str | None


def flag_correlated(legs: list[ComboLeg]) -> str | None:
    event_tickers = [leg.event_ticker for leg in legs]
    if len(set(event_tickers)) < len(event_tickers):
        return (
            "Two or more legs share the same underlying event -- their outcomes are "
            "correlated, so multiplying probabilities overstates (or understates) the "
            "combo's true odds. Treat this number as illustrative only."
        )
    return None


def evaluate_combo(legs: list[ComboLeg]) -> ComboResult:
    if not legs:
        raise ValueError("evaluate_combo requires at least one leg")

    combined_prob = 1.0
    for leg in legs:
        combined_prob *= leg.model_prob

    cost_usd = sum(leg.price_cents for leg in legs) / 100.0
    payout_usd = float(len(legs))  # each leg pays $1 if you're right on all of them

    return ComboResult(
        legs=legs,
        combined_model_prob=combined_prob,
        combined_cost_usd=cost_usd,
        combined_payout_usd=payout_usd,
        independence_warning=flag_correlated(legs),
    )
