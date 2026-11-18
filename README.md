# Delta SMC Bot V5.2 — Accounting & Trade Validation Research

**Research-only build. No API keys, approvals, exchange orders, or live/demo execution.**

## V5.2 changes

- Rejects invalid trade geometry before replay: LONG requires `stop < entry < target`; SHORT requires `target < entry < stop`.
- Validates that the supplied target is approximately 2R from the planned entry.
- Calculates realized R from the adverse entry fill to the stop distance, rather than using an absolute distance that can hide a stop on the wrong side.
- Applies adverse entry/exit slippage and estimated fees on both sides.
- Models gap-through stops at the worse candle open; if stop and target are both touched in one OHLC candle, stop is assumed first.
- Allows only one open simulated position per instrument at a time; unresolved positions at the end of the replay are excluded.
- Displays and exports rejected candidate reasons separately from valid completed trades.
- Preserves the existing strict strategy filters, 0.5% default risk assumption, and 1:2 target rule.

## Run

Streamlit Cloud entry point: `dashboard.py`.

Local install:

```bash
pip install -r requirements.txt
streamlit run dashboard.py
```

Start with 7 days and one instrument at a time. Run BTCUSD and ETHUSD separately, then inspect both the completed-trade CSV and rejected-candidate audit CSV.

## Important limitations

- 15m EMA200, 5m swing-break proxy, liquidity clustering/sweep and FVG remain mechanical research approximations inherited from V4. They are not full discretionary BOS/CHoCH labeling.
- OHLC candles cannot reveal exact intrabar event ordering. The backtest uses conservative stop-first handling when both barriers are touched in one candle.
- Fees and slippage are user estimates. Funding, variable spread, latency, contract metadata/sizing, liquidation, partial fills and compounding are not modeled.
- The 0.5% setting is only an illustrative R-to-equity assumption; it is not exchange position sizing or a promise of fixed realized account risk.
- A valid backtest is not evidence of future profitability. Review trade logs and rejected candidates before considering any further testing.

Never add exchange credentials to this research build. Demo/live execution is not implemented.
