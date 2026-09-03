import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.sizing import edge, implied_probability, kelly_fraction, suggest_stake


def test_implied_probability():
    assert implied_probability(55) == 0.55
    assert implied_probability(0) == 0.0
    assert implied_probability(100) == 1.0


def test_edge_sign():
    assert edge(0.6, 0.5) > 0
    assert edge(0.4, 0.5) < 0
    assert edge(0.5, 0.5) == 0


def test_kelly_fraction_no_edge_is_zero():
    # Model agrees exactly with market price -> no edge -> Kelly stakes nothing.
    assert kelly_fraction(0.55, 55) == 0.0


def test_kelly_fraction_positive_edge():
    # Model thinks 65% true, market prices it at 50c -> real edge, Kelly should be positive.
    f = kelly_fraction(0.65, 50)
    assert 0 < f <= 1
    # Hand check: p=0.5, b=(1-0.5)/0.5=1, f* = q - (1-q)/b = 0.65 - 0.35 = 0.30
    assert abs(f - 0.30) < 1e-9


def test_kelly_fraction_clamped_at_bad_prices():
    assert kelly_fraction(0.5, 0) == 0.0
    assert kelly_fraction(0.5, 100) == 0.0


def test_suggest_stake_respects_cap():
    s = suggest_stake(
        bankroll_usd=1000,
        model_prob=0.9,
        price_cents=50,  # huge edge -> full/quarter Kelly would want a lot
        kelly_fraction_multiplier=1.0,
        max_stake_pct_of_bankroll=0.03,
    )
    assert s.suggested_pct_of_bankroll == 0.03
    assert s.suggested_usd == 30.0


def test_suggest_stake_no_edge_suggests_nothing():
    s = suggest_stake(bankroll_usd=1000, model_prob=0.5, price_cents=50)
    assert s.suggested_usd == 0.0
    assert s.edge_pct == 0.0
