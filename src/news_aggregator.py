"""
Pulls headlines from configured RSS/Atom feeds and filters to the ones
mentioning a given game's teams. This is "what experts/reporters are
saying" sourced from real, named, publicly syndicated feeds -- not
scraped from arbitrary sites and not fabricated.
"""

from __future__ import annotations

from typing import Iterable

import feedparser


def fetch_headlines(feed_urls: Iterable[str], max_per_feed: int = 25) -> list[dict]:
    headlines = []
    for url in feed_urls:
        parsed = feedparser.parse(url)
        source = parsed.feed.get("title", url)
        for entry in parsed.entries[:max_per_feed]:
            headlines.append({
                "source": source,
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
            })
    return headlines


def relevant_to(headlines: list[dict], team_names: Iterable[str]) -> list[dict]:
    """Headlines whose title mentions any of the given team names (case-insensitive)."""
    needles = [t.lower() for t in team_names if t]
    if not needles:
        return []
    out = []
    for h in headlines:
        title_lower = h["title"].lower()
        if any(n in title_lower for n in needles):
            out.append(h)
    return out
