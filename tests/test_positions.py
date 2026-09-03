import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.positions import Position, combined_probability, guess_series_ticker, parse_position


def test_guess_series_ticker():
    assert guess_series_ticker("KXNFLGAME-25SEP04KCLAC-KC") == "KXNFLGAME"
    assert guess_series_ticker("KXNBAGAME-26jun03nyksas") == "KXNBAGAME"


def test_parse_position_new_schema_yes_side():
    raw = {"ticker": "KXNFLGAME-25SEP04KCLAC-KC", "position_fp": "10.00",
           "market_exposure_dollars": "5.60"}
    pos = parse_position(raw)
    assert pos.side == "YES"
    assert pos.quantity == 10.0
    assert pos.exposure_usd == 5.60


def test_parse_position_new_schema_no_side():
    raw = {"ticker": "KXNFLGAME-25SEP04KCLAC-KC", "position_fp": "-4.00",
           "market_exposure_dollars": "2.00"}
    pos = parse_position(raw)
    assert pos.side == "NO"
    assert pos.quantity == 4.0


def test_parse_position_legacy_schema_fallback():
    raw = {"ticker": "KXNFLGAME-25SEP04KCLAC-KC", "position": 7, "market_exposure": 350}
    pos = parse_position(raw)
    assert pos.side == "YES"
    assert pos.quantity == 7.0
    assert pos.exposure_usd == 3.50


def test_parse_position_flat():
    raw = {"ticker": "X", "position_fp": "0"}
    pos = parse_position(raw)
    assert pos.side == "FLAT"


def test_combined_probability_multiplies_and_flags_correlation():
    p1 = Position(ticker="A", side="YES", quantity=1, exposure_usd=1, win_prob=0.6, event_key="EVT-1")
    p2 = Position(ticker="B", side="YES", quantity=1, exposure_usd=1, win_prob=0.5, event_key="EVT-1")
    combined, warning = combined_probability([p1, p2])
    assert abs(combined - 0.30) < 1e-9
    assert warning is not None


def test_combined_probability_independent_no_warning():
    p1 = Position(ticker="A", side="YES", quantity=1, exposure_usd=1, win_prob=0.6, event_key="EVT-1")
    p2 = Position(ticker="B", side="YES", quantity=1, exposure_usd=1, win_prob=0.5, event_key="EVT-2")
    combined, warning = combined_probability([p1, p2])
    assert abs(combined - 0.30) < 1e-9
    assert warning is None


def test_combined_probability_no_data():
    p1 = Position(ticker="A", side="YES", quantity=1, exposure_usd=1, win_prob=None)
    combined, warning = combined_probability([p1])
    assert combined is None
    assert warning is None
