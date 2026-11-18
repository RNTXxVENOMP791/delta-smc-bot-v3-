# Delta SMC Bot v5.1 — Optimized Research Backtester

Research-only Streamlit application for BTCUSD and ETHUSD public historical candles. **No API keys, approvals, or exchange order execution are included.**

## Files
- `dashboard.py` — Streamlit dashboard, duration selector, per-symbol run, progress, LONG/SHORT reports.
- `backtest.py` — walk-forward historical replay and six-hour cached candle downloads.
- `scanner.py` — V4 mechanical SMC research scanner (strict mandatory conditions).
- `config.py` — supported symbols.
- `requirements.txt` — Python dependencies.

## Run
```bash
pip install -r requirements.txt
streamlit run dashboard.py
```

## Suggested test sequence
1. Select one symbol and run 7 days.
2. Repeat for the other symbol.
3. If both complete, test 30 days, then 90 days.

Candle data is cached for six hours by symbol/timeframe/window. The backtest processes one instrument at a time and displays progress. Re-running with the same cache key should avoid downloading the same candle history again.

## Strategy rules retained
- 15m EMA200 directional filter.
- 5m confirmed swing-break proxy.
- 3m liquidity cluster with at least 3 touches plus sweep/reclaim.
- 3m FVG.
- All mandatory conditions must pass.
- 2R target. The risk assumption defaults to 0.5% per trade.

The 0.5% risk is used only to illustrate `net_R × risk%` as a non-compounded return estimate. Contract quantity sizing is not implemented.

## Important limitations
- The BOS/CHoCH logic is a mechanical swing-break proxy, not discretionary structure labeling.
- Liquidity and FVG detection are simplified mechanical definitions.
- Fees/slippage are estimates; funding, variable spread, latency, liquidation and contract sizing are not modeled.
- Intrabar ordering is unknown; if SL and TP occur in the same OHLC candle, SL is assumed first.
- A backtest is not evidence of future profitability. Review trades chart-by-chart before considering paper trading.
- **Never add exchange credentials or enable live/demo order execution in this research build.**
