"""
Analyzes YOUR actual open Kalshi positions: for each one, the current
odds of it winning, and -- for positions in a mapped sport whose game
hasn't started yet -- when it kicks off. Finishes with a combined
"all positions win" probability.

Read-only: GET /portfolio/positions, GET /markets/{ticker}, and ESPN's
public scoreboard/summary. Nothing here places, amends, or cancels an
order, and nothing here can -- nothing in this file imports order-related
methods at all.

Requires a Kalshi API key (KALSHI_API_KEY_ID / KALSHI_PRIVATE_KEY_PATH in
.env) -- /portfolio/positions is authenticated-only, unlike the market
data the rest of this bot uses.

A caveat worth reading: this sandbox's network egress to docs.kalshi.com
was blocked while building this, so the exact field names on
/portfolio/positions couldn't be confirmed against the live docs first-hand
-- they're taken from Kalshi's published API reference found via search.
parse_position() tries the documented field names first, falls back to
older-style ones, and the CLI prints one raw position's JSON on first run
so you can eyeball it against what got parsed. If the parsed numbers look
wrong, that raw JSON is exactly what to send back for a fix.

Usage:
    python -m src.positions --config config.yaml
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field

import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from . import espn_client
from .kalshi_client import KalshiAuth, KalshiClient, KalshiError
from .main import match_team
from .sizing import implied_probability


@dataclass
class Position:
    ticker: str
    side: str  # "YES", "NO", or "FLAT"
    quantity: float
    exposure_usd: float | None
    title: str = ""
    status: str = "unknown"  # "live", "upcoming", "final", "no-model"
    win_prob: float | None = None
    prob_source: str = "market"  # "espn-live" | "espn-final" | "market"
    start_time_utc: str | None = None
    detail: str = ""
    event_key: str = ""  # used only to flag correlated positions, not a real Kalshi field
    raw: dict = field(default_factory=dict)


def parse_position(raw: dict) -> Position:
    qty = None
    for key in ("position_fp", "position"):
        if key in raw and raw[key] is not None:
            try:
                qty = float(raw[key])
            except (TypeError, ValueError):
                pass
            break

    exposure_usd = None
    if raw.get("market_exposure_dollars") is not None:
        try:
            exposure_usd = float(raw["market_exposure_dollars"])
        except (TypeError, ValueError):
            pass
    elif raw.get("market_exposure") is not None:
        exposure_usd = raw["market_exposure"] / 100.0

    qty = qty or 0.0
    side = "YES" if qty > 0 else "NO" if qty < 0 else "FLAT"
    return Position(ticker=raw.get("ticker", "?"), side=side, quantity=abs(qty),
                     exposure_usd=exposure_usd, raw=raw)


def guess_series_ticker(market_ticker: str) -> str:
    """Kalshi tickers are always "{series_ticker}-{...}" -- e.g. KXNFLGAME-25SEP04KCLAC-KC."""
    return market_ticker.split("-")[0]


def enrich_with_market(client: KalshiClient, pos: Position) -> None:
    try:
        market = client.get_market(pos.ticker)
    except KalshiError as exc:
        pos.status = "unknown"
        pos.detail = f"could not load market: {exc}"
        return

    pos.title = market.get("yes_sub_title") or market.get("title") or pos.ticker
    price = market.get("yes_ask") or market.get("last_price")
    if price is not None:
        market_yes_prob = implied_probability(price)
        pos.win_prob = market_yes_prob if pos.side == "YES" else (1 - market_yes_prob)
    pos.status = "no-model"
    pos.prob_source = "market"


def enrich_with_espn(pos: Position, games_by_league: dict) -> None:
    series_ticker = guess_series_ticker(pos.ticker)
    mapping = espn_client.SERIES_TO_ESPN.get(series_ticker)
    if not mapping:
        return  # stays market-priced; not a sport we have a score/win-prob source for

    sport, league = mapping
    games = games_by_league.setdefault((sport, league), espn_client.scoreboard(sport, league))
    game = next(
        (g for g in games if match_team(pos.title, g["home_team"], g["home_abbrev"])
         or match_team(pos.title, g["away_team"], g["away_abbrev"])),
        None,
    )
    if game is None:
        return

    pos.event_key = game["event_id"]
    is_home_side = match_team(pos.title, game["home_team"], game["home_abbrev"])

    if game["state"] == "pre":
        pos.status = "upcoming"
        pos.start_time_utc = game["start_time_utc"]
        return

    if game["state"] == "in":
        wp = espn_client.win_probability(sport, league, game["event_id"])
        if wp is None:
            return
        team_win_prob = wp["home_win_prob"] if is_home_side else wp["away_win_prob"]
        pos.win_prob = team_win_prob if pos.side == "YES" else (1 - team_win_prob)
        pos.status = "live"
        pos.detail = game.get("detail", "")
        pos.prob_source = "espn-live"
        return

    if game["state"] == "post":
        try:
            home_won = int(game["home_score"]) > int(game["away_score"])
            tied = int(game["home_score"]) == int(game["away_score"])
        except (TypeError, ValueError):
            return
        team_won = (home_won if is_home_side else not home_won) and not tied
        game_win_prob = 0.5 if tied else (1.0 if team_won else 0.0)
        pos.win_prob = game_win_prob if pos.side == "YES" else (1 - game_win_prob)
        pos.status = "final"
        pos.detail = "final score -- game has ended, Kalshi settlement may still be pending"
        pos.prob_source = "espn-final"


def analyze(client: KalshiClient, raw_positions: list[dict] | None = None) -> list[Position]:
    if not client.auth:
        raise KalshiError(
            "Reading your positions needs a Kalshi API key. Set KALSHI_API_KEY_ID and "
            "KALSHI_PRIVATE_KEY_PATH in .env -- see README.md 'Getting a Kalshi API key'."
        )

    if raw_positions is None:
        raw_positions = client.get_positions()
    positions = [parse_position(p) for p in raw_positions]
    positions = [p for p in positions if p.side != "FLAT"]

    games_by_league: dict = {}
    for pos in positions:
        enrich_with_market(client, pos)
        enrich_with_espn(pos, games_by_league)

    return positions


def combined_probability(positions: list[Position]) -> tuple[float | None, str | None]:
    known = [p for p in positions if p.win_prob is not None]
    if not known:
        return None, None
    combined = 1.0
    for p in known:
        combined *= p.win_prob
    warning = None
    event_keys = [p.event_key for p in known if p.event_key]
    if len(set(event_keys)) < len(event_keys):
        warning = (
            "Two or more of these positions are on the same underlying game -- their "
            "outcomes are correlated, so this combined number overstates/understates the "
            "real odds. Treat it as illustrative, not exact."
        )
    return combined, warning


def render(positions: list[Position], console: Console) -> None:
    if not positions:
        console.print("[dim]No open positions found.[/dim]")
        return

    table = Table(title="Your open Kalshi positions")
    table.add_column("Market")
    table.add_column("Side")
    table.add_column("Qty", justify="right")
    table.add_column("Exposure", justify="right")
    table.add_column("Status")
    table.add_column("Win odds", justify="right")
    table.add_column("Source")

    for p in positions:
        if p.status == "upcoming" and p.start_time_utc:
            status_text = f"starts {p.start_time_utc}"
        elif p.detail:
            status_text = p.detail
        else:
            status_text = p.status
        odds_text = f"{p.win_prob:.0%}" if p.win_prob is not None else "-"
        table.add_row(
            p.title or p.ticker, p.side, f"{p.quantity:g}",
            f"${p.exposure_usd:,.2f}" if p.exposure_usd is not None else "-",
            status_text, odds_text, p.prob_source,
        )
    console.print(table)

    combined, warning = combined_probability(positions)
    if combined is not None:
        console.print(f"\n[bold]Odds every position above wins: {combined:.1%}[/bold]")
        if warning:
            console.print(f"[yellow]Note:[/yellow] {warning}")
    else:
        console.print("\n[dim]Not enough price/model data yet to compute a combined figure.[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze your open Kalshi positions (read-only).")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--show-raw", action="store_true",
                         help="Print one raw position's JSON, to check the parsed fields against it.")
    args = parser.parse_args()

    load_dotenv()
    console = Console()

    env = os.environ.get("KALSHI_ENV", "demo")
    key_id = os.environ.get("KALSHI_API_KEY_ID")
    key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
    auth = KalshiAuth(key_id=key_id, private_key_path=key_path) if key_id and key_path and os.path.exists(key_path) else None
    client = KalshiClient(env=env, auth=auth)

    try:
        if not client.auth:
            raise KalshiError(
                "Reading your positions needs a Kalshi API key. Set KALSHI_API_KEY_ID and "
                "KALSHI_PRIVATE_KEY_PATH in .env -- see README.md 'Getting a Kalshi API key'."
            )
        raw_positions = client.get_positions()
        if args.show_raw and raw_positions:
            console.print("[dim]Raw position (first one) -- check this against the parsed table:[/dim]")
            console.print(raw_positions[0])
            console.print()
        positions = analyze(client, raw_positions=raw_positions)
        render(positions, console)
    except KalshiError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
