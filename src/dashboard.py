"""Renders the live terminal dashboard with `rich`."""

from __future__ import annotations

from datetime import datetime

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def render(
    games: list[dict], edges: list[dict], other_markets: list[dict],
    headlines: list[dict], portfolio: dict | None,
) -> Group:
    parts = []

    if portfolio is not None:
        bal = portfolio.get("balance_usd")
        parts.append(Text(f"Kalshi balance: ${bal:,.2f}" if bal is not None else "Kalshi balance: unavailable",
                           style="dim"))

    games_table = Table(title="Live games", expand=True)
    games_table.add_column("Matchup")
    games_table.add_column("Score", justify="right")
    games_table.add_column("Status")
    for g in games:
        score = f"{g['away_abbrev']} {g['away_score']} - {g['home_score']} {g['home_abbrev']}"
        games_table.add_row(g["name"], score, g.get("detail") or g.get("state") or "")
    parts.append(games_table if games else Text("No live games in the tracked scope right now.", style="dim"))

    edges_table = Table(title="Market edges (model vs. Kalshi price)", expand=True)
    edges_table.add_column("Market")
    edges_table.add_column("Model")
    edges_table.add_column("Kalshi")
    edges_table.add_column("Edge", justify="right")
    edges_table.add_column("Suggested stake", justify="right")
    for e in sorted(edges, key=lambda x: x["stake"].edge_pct, reverse=True):
        stake = e["stake"]
        edge_style = "bold green" if stake.edge_pct > 0 else "dim"
        edges_table.add_row(
            e["title"],
            f"{e['model_prob']:.0%}",
            f"{e['market_prob']:.0%}",
            Text(f"{stake.edge_pct:+.1%}", style=edge_style),
            f"${stake.suggested_usd:,.2f}" if stake.suggested_usd > 0 else "-",
        )
    parts.append(edges_table if edges else Text("No markets clear your min-edge threshold yet.", style="dim"))

    if other_markets:
        other_table = Table(title="Other Kalshi sports markets (no live-score model for these yet)", expand=True)
        other_table.add_column("Series")
        other_table.add_column("Market")
        other_table.add_column("Yes price", justify="right")
        for m in other_markets[:20]:
            price = m["price_cents"]
            other_table.add_row(m["series"] or "-", m["title"], f"{price}¢" if price is not None else "-")
        parts.append(other_table)

    if headlines:
        news_lines = [f"[dim]{h['source']}[/dim]  {h['title']}" for h in headlines[:8]]
        parts.append(Panel("\n".join(news_lines), title="Related headlines", expand=True))

    parts.append(Text(f"Updated {datetime.now().strftime('%H:%M:%S')} -- monitor only, no orders are ever placed.",
                       style="italic dim"))
    return Group(*parts)
