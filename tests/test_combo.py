import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.combo import ComboLeg, evaluate_combo, flag_correlated


def leg(ticker, event, prob, price):
    return ComboLeg(ticker=ticker, event_ticker=event, title=ticker, model_prob=prob, price_cents=price)


def test_independent_legs_no_warning():
    legs = [leg("A", "EVT-A", 0.6, 55), leg("B", "EVT-B", 0.7, 65)]
    assert flag_correlated(legs) is None


def test_shared_event_flags_correlation():
    legs = [leg("A", "EVT-1", 0.6, 55), leg("B", "EVT-1", 0.3, 25)]
    assert flag_correlated(legs) is not None


def test_combined_probability_multiplies():
    legs = [leg("A", "EVT-A", 0.5, 50), leg("B", "EVT-B", 0.5, 50)]
    result = evaluate_combo(legs)
    assert abs(result.combined_model_prob - 0.25) < 1e-9
    assert result.combined_cost_usd == 1.0
    assert result.combined_payout_usd == 2.0
    assert result.independence_warning is None
