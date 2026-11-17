# Delta SMC Bot v4 — Research Scanner

## What this build does
- Fetches public Delta Exchange India candles for BTCUSD and ETHUSD.
- Retrieves native 15m, 5m and 3m resolutions independently.
- Removes the still-forming candle before analysis.
- Evaluates a strict conjunction of 15m EMA200 trend, 5m swing-structure break proxy, 3m liquidity cluster (>=3 touches) with sweep/reclaim, and 3m three-candle FVG.
- Displays research candidates in Streamlit.

## Safety
This build is **research-only**. It does not use API keys, submit orders, approve orders, size contracts, attach SL/TP, or manage positions. A candidate is not a trade instruction. Do not add live or Demo credentials to this version.

## Deploy
1. Keep the existing GitHub repository private.
2. Replace the existing project files with the files in this folder (upload all changed files; do not upload `.env`).
3. Streamlit Cloud: deploy/reboot the app using `dashboard.py` as the entry point.
4. Requirements are in `requirements.txt`.

## Run locally
`pip install -r requirements.txt`
`streamlit run dashboard.py`

## Strategy definitions and known limitations
- EMA200 is calculated on the latest closed 15m close.
- Swing pivots use two bars on either side; the 5m BOS proxy requires a close beyond one of the recent confirmed pivot levels.
- Liquidity clusters are approximated by at least three swing pivots within 0.07% of a reference level. Sweep/reclaim is checked on the latest closed 3m candle.
- FVG is a three-candle imbalance (`current low > high two candles earlier` for bullish; inverse for bearish). Its midpoint is shown, but a later retracement into the zone is not yet required.
- CHoCH classification, inducement, order blocks, premium/discount arrays, multi-sweep sequencing, setup deduplication, alert expiry, and independent backtest validation are not yet implemented.
- REST candle polling is not tick-level real-time data. Always check the closed-candle timestamp.

## Delta API
Uses public `GET /v2/history/candles` on `https://api.india.delta.exchange`, with `symbol`, `resolution`, `start`, and `end` query parameters. Delta documents native 3m/5m/15m resolutions and a maximum of 2,000 candles per response. See https://docs.delta.exchange/.
