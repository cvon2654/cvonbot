"""
Edge and position-size math. Everything here produces a *suggestion* --
nothing in this module or anywhere else in the bot places an order.

Kalshi prices are in cents and represent the cost of a "yes" contract that
pays out $1 if the event happens, $0 otherwise -- so price/100 doubles as
the market's implied probability.
"""

from __future__ import annotations

from dataclasses import dataclass


def implied_probability(price_cents: float) -> float:
    return price_cents / 100.0


def edge(model_prob: float, market_prob: float) -> float:
    """Positive = you believe the true probability is higher than the market's price."""
    return model_prob - market_prob


@dataclass
class StakeSuggestion:
    edge_pct: float
    raw_kelly_pct: float
    suggested_pct_of_bankroll: float
    suggested_usd: float
    rationale: str


def kelly_fraction(model_prob: float, price_cents: float) -> float:
    """
    Fraction of bankroll full Kelly would stake on a "yes" contract, given
    your estimate of the true probability and the contract's price.

    Buying 1 yes-contract costs `p` (=price_cents/100) and pays 1 if it
    resolves yes -- so profit-per-dollar-staked on a win is b = (1-p)/p.
    Standard binary Kelly: f* = q - (1-q)/b, clamped to [0, 1].
    """
    p = implied_probability(price_cents)
    q = model_prob
    if p <= 0 or p >= 1:
        return 0.0
    b = (1 - p) / p
    f = q - (1 - q) / b
    return max(0.0, min(1.0, f))


def suggest_stake(
    bankroll_usd: float,
    model_prob: float,
    price_cents: float,
    kelly_fraction_multiplier: float = 0.25,
    max_stake_pct_of_bankroll: float = 0.03,
) -> StakeSuggestion:
    market_prob = implied_probability(price_cents)
    e = edge(model_prob, market_prob)
    raw_kelly = kelly_fraction(model_prob, price_cents)
    scaled = raw_kelly * kelly_fraction_multiplier
    capped_pct = min(scaled, max_stake_pct_of_bankroll)
    usd = round(bankroll_usd * capped_pct, 2)

    if e <= 0 or raw_kelly <= 0:
        rationale = "No edge at this price -- market implied probability meets or beats the model estimate."
        return StakeSuggestion(e, raw_kelly, 0.0, 0.0, rationale)

    hit_cap = scaled > max_stake_pct_of_bankroll
    rationale = (
        f"Model {model_prob:.0%} vs market {market_prob:.0%} ({e:+.1%} edge). "
        f"{kelly_fraction_multiplier:.0%}-Kelly wants {scaled:.1%} of bankroll"
        + (f", capped to your {max_stake_pct_of_bankroll:.0%} max." if hit_cap else ".")
    )
    return StakeSuggestion(e, raw_kelly, capped_pct, usd, rationale)
