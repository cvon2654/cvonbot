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
| Headlines | RSS feeds you configure (ESPN, CBS Sports, etc. by default) |

### On "parlays"

Kalshi doesn't have parlays — every market is its own single yes/no
contract, settled independently. `src/combo.py` lets you evaluate a
bundle of legs as if you'd bought each one separately, but it's only
correct when the legs are truly independent. Sports outcomes from the
same game usually aren't, so the tool actively flags legs that share an
event and labels the combined number as illustrative rather than pretending
it's a real product Kalshi sells you.

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
