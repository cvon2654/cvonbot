"""
Entry point: polls Kalshi + ESPN + RSS on a timer and renders a live
terminal dashboard. Read-only end to end -- there is no code path in this
project that submits, amends, or cancels a Kalshi order.

Usage:
    python -m src.main --config config.yaml
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import yaml
from dotenv import load_dotenv
from rich.live import Live

from . import espn_client, news_aggregator
from .dashboard import render
from .kalshi_client import KalshiAuth, KalshiClient, KalshiError, sports_events
from .sizing import implied_probability, suggest_stake

DEFAULT_SERIES = list(espn_client.SERIES_TO_ESPN.keys())


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def build_client(cfg: dict) -> KalshiClient:
    env = os.environ.get("KALSHI_ENV", "demo")
    auth = None
    key_id = os.environ.get("KALSHI_API_KEY_ID")
    key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
    if key_id and key_path and os.path.exists(key_path):
        auth = KalshiAuth(key_id=key_id, private_key_path=key_path)
    return KalshiClient(env=env, auth=auth)


def resolve_series(cfg: dict, client: KalshiClient) -> list[dict]:
    """Returns Kalshi events (with nested markets) in scope, tagged with an ESPN mapping."""
    scope = cfg.get("series_scope", "sports")
    if scope == "sports":
        events = sports_events(client)
    else:
        events = [e for e in client.get_events(status="open") if e.get("series_ticker") in scope]
    return [e for e in events if e.get("series_ticker") in espn_client.SERIES_TO_ESPN]


def match_team(text: str, team_name: str, team_abbrev: str) -> bool:
    text_l = text.lower()
    return (team_name or "").lower() in text_l or (team_abbrev or "").lower() in text_l.split()


def gather(cfg: dict, client: KalshiClient) -> tuple[list[dict], list[dict], list[dict], dict | None, list[str]]:
    warnings: list[str] = []
    events = resolve_series(cfg, client)

    espn_games_by_league: dict[tuple[str, str], list[dict]] = {}
    all_games: list[dict] = []
    for series_ticker in {e["series_ticker"] for e in events}:
        sport, league = espn_client.SERIES_TO_ESPN[series_ticker]
        games = espn_client.scoreboard(sport, league)
        espn_games_by_league[(sport, league)] = games
        all_games.extend(games)

    edges = []
    for event in events:
        series_ticker = event["series_ticker"]
        sport, league = espn_client.SERIES_TO_ESPN[series_ticker]
        games = espn_games_by_league.get((sport, league), [])

        for market in event.get("markets", []):
            title = market.get("yes_sub_title") or market.get("title") or market.get("ticker")
            game = next(
                (g for g in games if match_team(title, g["home_team"], g["home_abbrev"])
                 or match_team(title, g["away_team"], g["away_abbrev"])),
                None,
            )
            if game is None:
                continue
            if game["state"] != "in":
                continue  # only compute live edges for in-progress games

            wp = espn_client.win_probability(sport, league, game["event_id"])
            if wp is None:
                continue

            is_home_market = match_team(title, game["home_team"], game["home_abbrev"])
            model_prob = wp["home_win_prob"] if is_home_market else wp["away_win_prob"]

            price = market.get("yes_ask") or market.get("last_price")
            if price is None:
                warnings.append(f"{market.get('ticker')}: no price available, skipped")
                continue

            stake = suggest_stake(
                bankroll_usd=cfg["bankroll_usd"],
                model_prob=model_prob,
                price_cents=price,
                kelly_fraction_multiplier=cfg.get("kelly_fraction_multiplier", 0.25),
                max_stake_pct_of_bankroll=cfg.get("max_stake_pct_of_bankroll", 0.03),
            )
            if abs(stake.edge_pct) < cfg.get("min_edge_to_alert", 0.05):
                continue

            edges.append({
                "title": title,
                "ticker": market.get("ticker"),
                "model_prob": model_prob,
                "market_prob": implied_probability(price),
                "stake": stake,
            })

    all_teams = set()
    for g in all_games:
        all_teams.add(g["home_team"])
        all_teams.add(g["away_team"])
    headlines = news_aggregator.fetch_headlines(cfg.get("news_feeds", []))
    relevant_headlines = news_aggregator.relevant_to(headlines, all_teams)

    portfolio = None
    if cfg.get("show_portfolio") and client.auth:
        try:
            bal = client.get_balance()
            portfolio = {"balance_usd": bal.get("balance", 0) / 100.0}
        except KalshiError as exc:
            warnings.append(f"portfolio fetch failed: {exc}")

    return all_games, edges, relevant_headlines, portfolio, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Live Kalshi sports market monitor (read-only).")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    load_dotenv()
    if not os.path.exists(args.config):
        print(f"Missing {args.config} -- copy config.example.yaml to {args.config} first.", file=sys.stderr)
        sys.exit(1)

    cfg = load_config(args.config)
    client = build_client(cfg)
    interval = cfg.get("poll_interval_seconds", 30)

    with Live(refresh_per_second=1, screen=False) as live:
        while True:
            try:
                games, edges, headlines, portfolio, warnings = gather(cfg, client)
                live.update(render(games, edges, headlines, portfolio))
                for w in warnings:
                    live.console.log(f"[yellow]warning:[/yellow] {w}")
            except KalshiError as exc:
                live.console.log(f"[red]Kalshi API error:[/red] {exc}")
            except Exception as exc:  # keep the loop alive; a transient bad poll shouldn't kill it
                live.console.log(f"[red]unexpected error:[/red] {exc}")
            time.sleep(interval)


if __name__ == "__main__":
    main()
