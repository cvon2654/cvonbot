import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.kalshi_client import extract_price_cents, is_illiquid
from src.main import market_title


def test_extract_price_cents_prefers_dollar_fields():
    # Real shape confirmed against a live account: dollar strings, not cent ints.
    market = {"yes_ask_dollars": "0.5500", "yes_ask": 999}
    assert abs(extract_price_cents(market) - 55.0) < 1e-9


def test_extract_price_cents_falls_back_to_last_price_dollars():
    market = {"last_price_dollars": "0.0020"}
    assert abs(extract_price_cents(market) - 0.2) < 1e-9


def test_extract_price_cents_falls_back_to_legacy_cent_fields():
    market = {"yes_ask": 55}
    assert extract_price_cents(market) == 55.0


def test_extract_price_cents_missing_everything():
    assert extract_price_cents({}) is None


def test_extract_price_cents_zero_dollar_price_is_not_missing():
    # 0 is falsy in Python -- must not be treated the same as "no price".
    market = {"yes_ask_dollars": "0.0000"}
    assert extract_price_cents(market) == 0.0


def test_extract_price_cents_ignores_ask_with_no_real_size():
    # Found on real illiquid custom multi-leg markets: yes_ask_dollars defaults
    # to "1.0000" when nobody is actually offering to sell -- not a real 100%
    # probability. Must fall back to the actual last executed trade instead.
    market = {"yes_ask_dollars": "1.0000", "yes_ask_size_fp": "0.00",
              "last_price_dollars": "0.0020"}
    assert abs(extract_price_cents(market) - 0.2) < 1e-9


def test_extract_price_cents_trusts_ask_with_real_size():
    market = {"yes_ask_dollars": "0.6000", "yes_ask_size_fp": "50.00",
              "last_price_dollars": "0.0020"}
    assert abs(extract_price_cents(market) - 60.0) < 1e-9


def test_extract_price_cents_trusts_ask_when_size_field_absent():
    # Normal single-game markets may not report a size field at all -- absence
    # isn't evidence of illiquidity, only an explicit zero is.
    market = {"yes_ask_dollars": "0.6000"}
    assert abs(extract_price_cents(market) - 60.0) < 1e-9


def test_is_illiquid_true_when_no_real_quotes():
    market = {"yes_ask_size_fp": "0.00", "yes_bid_size_fp": "0.00"}
    assert is_illiquid(market) is True


def test_is_illiquid_false_with_real_size():
    market = {"yes_ask_size_fp": "50.00", "yes_bid_size_fp": "0.00"}
    assert is_illiquid(market) is False


def test_market_title_collapses_multivariate_bundle():
    market = {"mve_selected_legs": [{"market_ticker": "A"}, {"market_ticker": "B"}],
              "title": "yes A,yes B"}
    assert market_title(market) == "Multi-pick bundle (2 legs)"


def test_market_title_normal_market_uses_subtitle():
    market = {"yes_sub_title": "Will the Chiefs win?", "title": "fallback"}
    assert market_title(market) == "Will the Chiefs win?"
