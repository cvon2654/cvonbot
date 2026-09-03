import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.kalshi_client import extract_price_cents
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


def test_market_title_collapses_multivariate_bundle():
    market = {"mve_selected_legs": [{"market_ticker": "A"}, {"market_ticker": "B"}],
              "title": "yes A,yes B"}
    assert market_title(market) == "Multi-pick bundle (2 legs)"


def test_market_title_normal_market_uses_subtitle():
    market = {"yes_sub_title": "Will the Chiefs win?", "title": "fallback"}
    assert market_title(market) == "Will the Chiefs win?"
