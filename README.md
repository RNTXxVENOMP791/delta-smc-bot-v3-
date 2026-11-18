# Delta SMC Bot V5.4 — EMA200 Removed Research Build

**Variant B only.** The 15m EMA200 value/trend may still be displayed for context, but it is informational and does not block a setup or backtest entry.

## Mandatory conditions (unchanged)
- 5m structure break (mechanical BOS/CHoCH proxy)
- 3m liquidity cluster with at least 3 touches
- 3m sweep and reclaim
- 3m fair value gap (FVG)
- Backtest still requires a later FVG midpoint revisit, valid stop/target geometry, and the 1:2 target rule.

## Run
Streamlit Cloud entry point: `dashboard.py`. Start with 7 days and one instrument at a time.

## Safety and limitations
- Public market data only. No API keys, approvals, exchange orders, or demo/live execution.
- Fees and slippage are estimates; funding, variable spread, latency, contract sizing and liquidation are not modeled.
- The 0.5% risk value is illustrative only, not exchange position sizing or guaranteed realized risk.
- The 5m structure, liquidity and FVG definitions are mechanical research approximations, not full discretionary SMC interpretation.
- More trades do not automatically mean a better strategy. Review trade logs; small samples are inconclusive.
