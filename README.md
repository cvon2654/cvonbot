# Kalshi Live Bot

A read-only terminal dashboard for Kalshi's sports markets: live scores,
each market's price vs. a real win-probability model, related headlines,
and Kelly-sized bet **suggestions**.

**This bot never places, amends, or cancels an order.** There is no code
path anywhere in this repo that can touch your Kalshi balance. It reads
public market data (and, optionally, your balance/positions for display),
computes numbers, and prints them. Every trade is still yours to make by
hand in the Kalshi app.

## What it actually shows

| Panel | Source |
|---|---|
| Live games & scores | ESPN's public scoreboard JSON (no key needed) |
| Market prices | Kalshi's public `/markets` and `/events` endpoints |
| "Model" win probability | ESPN's own published win-probability estimate for in-progress games |
| Edge & suggested stake | Your model-vs-market gap run through fractional Kelly, hard-capped |
| Other sports markets | Every other open Kalshi sports market (soccer, tennis, golf, MMA, futures, ...) listed with its price, with no edge computed |
| Headlines | RSS feeds you configure (ESPN, CBS Sports, etc. by default) |

`series_scope: sports` (the default) pulls **every** open Kalshi event
categorized as a sport — not just NFL/NBA/MLB/NHL/college. Full edge
analysis (model probability vs. price, Kelly sizing) only runs for the
leagues `src/espn_client.py` has a live-score mapping for; every other
sport still shows up, just in the plainer "Other sports markets" list
with no model comparison, instead of being silently dropped.

### On "parlays"

**Correction from an earlier version of this README:** Kalshi does have a
real multi-leg product — "Multivariate Event" markets (tickers like
`KXMVECROSSCATEGORY-...`), which bundle several picks (`mve_selected_legs`
in the raw market data) into one all-or-nothing contract that settles
atomically, closer to an actual sportsbook parlay than anything this repo
builds itself. `src/positions.py` recognizes these (shown as "Multi-pick
bundle (N legs)" rather than their real title, which is a comma-joined
list of every leg and can run to dozens of names) and prices them like
any other position.

Separately, `src/combo.py` still exists for evaluating a *hypothetical*
bundle of legs bought one-by-one on your own — useful for sanity-checking
an idea before building it as a real Kalshi multivariate event, but only
mathematically correct when the legs are truly independent. Sports
outcomes from the same game usually aren't, so it actively flags legs that
share an event rather than silently overstating the odds.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml   # edit bankroll, thresholds, feeds
cp .env.example .env                 # only needed for the optional balance/positions view
```

Edit `config.yaml`:
- `bankroll_usd` — used only to size suggestions, never sent anywhere.
- `kelly_fraction_multiplier` — 0.25 (quarter-Kelly) by default; full Kelly
  is too aggressive for real staking and is not recommended.
- `max_stake_pct_of_bankroll` — hard ceiling on any single suggestion.
- `min_edge_to_alert` — filters out noise-level edges.

Run it:

```bash
python -m src.main --config config.yaml
```

By default `KALSHI_ENV` is `demo`, pointed at Kalshi's paper-trading
environment — safe to leave running without touching real markets, though
again, nothing here ever submits an order regardless of environment.

## Floating overlay (Windows)

Instead of (or alongside) the terminal dashboard, `src/overlay.py` is a
small always-on-top window — drag it by the title bar, resize from the
bottom-right corner, close with the ✕. It shows the same live games, top
edges, and headlines, refreshed on the same `poll_interval_seconds`.

```bash
python -m src.overlay --config config.yaml
```

It uses Tk, which ships with the official [python.org](https://www.python.org/downloads/windows/)
Windows installer (check "tcl/tk and IDLE" during setup — it's on by
default). If you installed Python from the Microsoft Store instead and
`import tkinter` fails, that's why; reinstall from python.org.

The window is always-on-top but **not** click-through — clicks on it stay
on it, so it won't fire mouse events at whatever's underneath. It's a
plain window, not a native game/stream overlay hooked into DirectX/OpenGL,
so it sits *above* other windows on the desktop but won't render inside a
full-screen exclusive game the way an in-game overlay (Discord's, Nvidia's)
does — alt-tab or run the game in borderless-windowed mode if you want both
visible at once.

## Analyzing your open positions

```bash
python -m src.positions --config config.yaml
```

For every position currently on your Kalshi account, this prints: the
market, which side you're on, your exposure, and its current odds of
winning — using ESPN's live win-probability while the game is in
progress, the actual final score if the game's already over (Kalshi
settlement can lag the final score), a scheduled kickoff time if it
hasn't started yet, and the market's own implied price for anything
outside a mapped sport. It finishes with the combined probability of
every listed position winning, flagged if two positions share a game
(their outcomes aren't independent, so multiplying probabilities
overstates/understates the real number).

This needs a Kalshi API key (see below) — `/portfolio/positions` is
authenticated-only, unlike the rest of this bot.

**On the position schema:** this was built without a live Kalshi account
to test against, and this sandbox couldn't reach docs.kalshi.com to
confirm the current response shape first-hand — the field names
(`position_fp`, `market_exposure_dollars`, ...) come from Kalshi's
published API reference via search, with a fallback to older-style field
names in case your account gets served a different shape. Run once with
`--show-raw` to print one raw position's JSON before it's parsed, and
sanity-check it against the table underneath:

```bash
python -m src.positions --config config.yaml --show-raw
```

If the parsed side/quantity/exposure look wrong compared to the raw JSON,
that raw JSON is exactly what's needed to fix `parse_position()` in
`src/positions.py`.

## Getting a Kalshi API key (optional — only needed to show your balance)

Market data needs no login at all. If you also want your live balance and
open positions shown alongside the dashboard:

1. Log into Kalshi, go to **Settings → API Keys**.
2. Generate a new key. Kalshi gives you back a **Key ID** and a private
   key file (`.pem`) — save the `.pem` somewhere local, e.g. next to this
   project as `kalshi_private_key.pem`. **Never commit it** (it's already
   in `.gitignore`).
3. Put the Key ID and the path to the `.pem` into `.env`:
   ```
   KALSHI_API_KEY_ID=your-key-id
   KALSHI_PRIVATE_KEY_PATH=./kalshi_private_key.pem
   ```
4. Set `show_portfolio: true` in `config.yaml`.

Requests are signed with RSA-PSS (SHA-256) per Kalshi's current auth
scheme — see `src/kalshi_client.py` for the exact implementation, and
Kalshi's own docs at [docs.kalshi.com](https://docs.kalshi.com/getting_started/api_keys)
if anything about their auth flow changes.

## Known limitations, plainly

- **Team matching is heuristic.** Kalshi market titles are matched to ESPN
  games by substring on team name/abbreviation. Unusual title formats can
  fail to match — the market still shows up with no model/edge computed
  rather than a wrong one.
- **ESPN's endpoints are undocumented.** They're the same ones espn.com
  itself uses and have been stable for years, but ESPN could reshape a
  payload without notice. Every getter in `espn_client.py` fails soft
  (returns `{}`/`[]`/`None`) rather than crashing the dashboard.
- **Polling, not streaming.** Updates every `poll_interval_seconds`
  (default 30s) via REST, not a websocket. Real-time enough for
  human-speed decisions; a websocket feed would cut the latency further
  if you want to extend it later.
- **The "model" is ESPN's win probability, not a proprietary edge.**
  It's a legitimate, named, independent data source to compare the market
  against — it is not a guarantee of anything, and it can be wrong, most
  often early in a game when little has happened yet.
- **Market pricing field names were wrong until verified against a real
  account.** Public API examples document integer-cent fields (`yes_ask`,
  `last_price`); a live account actually returns dollar-string fields
  (`yes_ask_dollars`, `last_price_dollars`). `extract_price_cents()` in
  `kalshi_client.py` checks both, dollar fields first, but if Kalshi
  changes this again, "every position shows blank odds" is the symptom
  to look for.

## Tests

The parts that are actually deterministic (edge math, Kelly sizing, combo
correlation flagging) have unit tests:

```bash
pip install pytest
pytest tests/
```

`kalshi_client.py`, `espn_client.py`, and `news_aggregator.py` talk to
live external services and are not covered by these tests — treat first
runs against `config.yaml` as your integration test, watched at the
terminal.
