"""
Client for ESPN's public scoreboard/summary JSON endpoints.

These are undocumented but widely used, free, and require no key -- ESPN
serves them to power espn.com itself. No guarantee they stay stable; if
ESPN reshapes a payload, the getters below return {} / [] rather than
raising, so the dashboard degrades instead of crashing.
"""

from __future__ import annotations

from typing import Optional

import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports"

# Kalshi sports series ticker -> ESPN (sport path, league) used to fetch scores.
SERIES_TO_ESPN = {
    "KXNFLGAME": ("football", "nfl"),
    "KXNBAGAME": ("basketball", "nba"),
    "KXMLBGAME": ("baseball", "mlb"),
    "KXNHLGAME": ("hockey", "nhl"),
    "KXNCAAFGAME": ("football", "college-football"),
    "KXNCAABGAME": ("basketball", "mens-college-basketball"),
}


def _get(url: str, params: Optional[dict] = None) -> dict:
    try:
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError):
        return {}


def scoreboard(sport: str, league: str) -> list[dict]:
    """Today's games for a sport/league, each with teams, score, and status."""
    data = _get(f"{BASE}/{sport}/{league}/scoreboard")
    games = []
    for event in data.get("events", []):
        comp = (event.get("competitions") or [{}])[0]
        competitors = comp.get("competitors", [])
        home = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away = next((c for c in competitors if c.get("homeAway") == "away"), {})
        games.append({
            "event_id": event.get("id"),
            "name": event.get("shortName") or event.get("name"),
            "state": (event.get("status", {}).get("type", {}) or {}).get("state"),  # pre/in/post
            "detail": (event.get("status", {}).get("type", {}) or {}).get("shortDetail"),
            "start_time_utc": event.get("date"),  # ISO 8601, only meaningful while state == "pre"
            "home_team": (home.get("team") or {}).get("displayName"),
            "home_abbrev": (home.get("team") or {}).get("abbreviation"),
            "home_score": home.get("score"),
            "away_team": (away.get("team") or {}).get("displayName"),
            "away_abbrev": (away.get("team") or {}).get("abbreviation"),
            "away_score": away.get("score"),
        })
    return games


def win_probability(sport: str, league: str, event_id: str) -> Optional[dict]:
    """Most recent ESPN win-probability estimate for a live game, if published for this sport."""
    data = _get(f"{BASE}/{sport}/{league}/summary", {"event": event_id})
    wp_series = data.get("winprobability")
    if not wp_series:
        return None
    latest = wp_series[-1]
    home_pct = latest.get("homeWinPercentage")
    if home_pct is None:
        return None
    return {"home_win_prob": home_pct, "away_win_prob": 1 - home_pct}


def leaders(sport: str, league: str, event_id: str) -> list[dict]:
    """Top statistical performers ESPN is highlighting for a game (its 'leaders' box)."""
    data = _get(f"{BASE}/{sport}/{league}/summary", {"event": event_id})
    out = []
    for group in data.get("leaders", []) or []:
        team = (group.get("team") or {}).get("displayName", "")
        for cat in group.get("leaders", []) or []:
            for entry in cat.get("leaders", [])[:1]:  # top performer per category
                athlete = entry.get("athlete", {})
                out.append({
                    "team": team,
                    "category": cat.get("displayName"),
                    "player": athlete.get("displayName"),
                    "value": entry.get("displayValue"),
                })
    return out
