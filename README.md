# Delta SMC Bot v3.0 — Human Approval + Delta Demo foundation

## Selected configuration
- Virtual balance: user chooses a custom amount in dashboard
- Risk display: 0.5% per signal by default
- Human approval required
- Explicit typed confirmation: `SUBMIT DEMO`
- Demo API host only: `https://cdn-ind.testnet.deltaex.org`
- Telegram + dashboard notifications
- Intended symbols: BTCUSD and ETHUSD

## Implemented
- Streamlit approval inbox and signal history
- SQLite persistence
- Reject workflow
- Demo-only signed REST order client
- Stale-signal expiry after 180 seconds
- Explicit second confirmation before Demo market entry
- Telegram notification helper
- Dummy signal generator for UI testing

## Critical limitations
- The live market scanner is NOT connected yet. `scanner.py` is an implementation checklist.
- The dummy signal is not a genuine SMC setup. Do not submit it to Demo unless intentionally testing a tiny Demo order and you understand the consequences.
- Demo market entry only: no attached SL/TP, no exit management, no fill reconciliation, no position monitoring.
- Contract size is manually entered as an integer. The 0.5% risk display is NOT converted into Delta contract quantity. Product multiplier, minimum quantity, tick size, margin and liquidation rules must be validated first.
- Do not deploy this approval app publicly without authentication. Keep it private and protect credentials.
- Never use production API credentials. Do not enable withdrawal permission.

## Run locally
```bash
python -m venv .venv
# Android cloud environment or macOS/Linux:
source .venv/bin/activate
# Windows:
.venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
streamlit run dashboard.py
```

## Telegram
1. Create a bot with Telegram's official BotFather.
2. Obtain the bot token and chat ID.
3. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in the private server environment or local `.env`.
4. Never paste tokens into chat, screenshots, source files or GitHub commits.

## Delta Demo API
The client uses the India Demo REST host and Delta's documented HMAC-SHA256 prehash:
HTTP method + timestamp + request path + query string + exact JSON body.
Required headers include api-key, signature, timestamp, User-Agent, Content-Type and Accept.
The market order payload uses `product_symbol`, integer `size`, `side`, `order_type=market_order`, and `time_in_force=ioc`.
Verify current documentation and Demo product metadata before enabling API credentials. Demo keys must only be used with the Demo host.

## Next mandatory work before strategy-generated Demo orders
1. Complete and audit the scanner with native timeframe candles and closed-bar synchronization.
2. Validate product metadata for BTCUSD/ETHUSD, contract multipliers, size increments, tick sizes and margin.
3. Convert risk budget to valid contract size and cap maximum notional exposure.
4. Add price freshness recheck immediately before approval submission.
5. Add attached protective stop and take-profit order handling; verify order state and fills.
6. Add idempotency, retry handling, API health checks and emergency cancel/close controls.
7. Add authentication/HTTPS and secret management before any remote deployment.
