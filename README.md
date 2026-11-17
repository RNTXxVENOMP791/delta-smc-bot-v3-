# Delta SMC Bot V5 — Research & Backtesting

Research-only Streamlit app for BTCUSD and ETHUSD. No API keys or order execution.

## Features
- Native public 3m, 5m and 15m candle retrieval.
- Strict V4 scanner filters (15m EMA200, 5m swing-break proxy, 3m liquidity cluster + sweep/reclaim, 3m FVG).
- Walk-forward historical replay for 30/60/90 days.
- FVG midpoint entry only after a later candle revisits the level.
- Fixed 2R target, sweep-candle stop reference, estimated per-side fee/slippage inputs.
- Trade log CSV export.

## Run locally
```bash
pip install -r requirements.txt
streamlit run dashboard.py
```

## Deploy
Streamlit Community Cloud: repository root `dashboard.py`. Keep repository private where possible. No secrets are required.

## Important limitations
This is a research prototype, not a validated trading strategy. BOS/CHoCH is a swing-break proxy; liquidity and FVG are mechanical approximations. Funding, spread variation, latency, contract sizing, liquidation and exact intrabar price path are not modeled. If SL and TP are both touched within one OHLC candle, the backtest assumes SL first. API rate limits and historical data coverage must be checked. No order execution is implemented or enabled.
