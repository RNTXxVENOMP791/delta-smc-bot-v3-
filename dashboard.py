import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from config import SYMBOLS
from scanner import scan_symbol, DeltaDataError

st.set_page_config(page_title="Delta SMC Bot v4 Research", page_icon="📈", layout="wide")
st.title("Delta SMC Bot v4 · Market Scanner")
st.caption("Public Delta market data · closed candles only · research alerts · NO order execution")
st.warning("SAFE RESEARCH MODE: API keys are not used. This build cannot submit, approve, or execute orders. Signals are candidates for manual review, not financial advice.")

with st.sidebar:
    st.header("Scanner settings")
    selected = st.multiselect("Instruments", SYMBOLS, default=SYMBOLS)
    st.caption("Fixed strategy filters: 15m EMA200, 5m structure break, 3m liquidity cluster (minimum 3 touches) + sweep/reclaim, and 3m FVG.")
    st.caption("Risk model target: 0.5% risk and 1:2 RR are not used for position sizing in this research-only build.")

st.subheader("Run market scan")
if st.button("Fetch candles and scan now", type="primary", disabled=not selected):
    st.session_state["scan_results"] = {}
    for symbol in selected:
        with st.spinner(f"Fetching native 15m / 5m / 3m candles for {symbol}..."):
            try:
                data, results = scan_symbol(symbol)
                st.session_state["scan_results"][symbol] = {"data":data,"results":results,"error":None}
            except Exception as exc:
                st.session_state["scan_results"][symbol] = {"data":None,"results":[],"error":str(exc)}

results = st.session_state.get("scan_results", {})
if results:
    for symbol, item in results.items():
        st.markdown(f"### {symbol}")
        if item["error"]:
            st.error(item["error"])
            continue
        data = item["data"]
        cols = st.columns(3)
        for col, tf in zip(cols, ("15m","5m","3m")):
            df = data[tf]
            col.metric(f"{tf} closed candles", len(df))
            col.caption(f"Last close: {float(df.close.iloc[-1]):,.4f}")
            col.caption(f"Last closed: {df.time_utc.iloc[-1]}")
        for res in item["results"]:
            with st.container(border=True):
                side = res["side"].upper()
                st.markdown(f"**{side} setup evaluation**")
                if res.get("candidate") is False:
                    st.info("No complete setup — at least one mandatory condition failed.")
                    st.write("Checks", res["checks"])
                    if res.get("reasons"): st.caption(" · ".join(res["reasons"]))
                else:
                    st.success("All coded filters matched — research candidate only")
                    a,b,c = st.columns(3)
                    a.metric("FVG midpoint entry", f"{res['entry']:,.4f}")
                    b.metric("Sweep candle stop ref", f"{res['stop']:,.4f}")
                    c.metric("Illustrative 2R target", f"{res['target']:,.4f}")
                    st.write({k:v for k,v in res.items() if k not in ("checks",)})
                    st.warning("This is not an executable signal. FVG retracement, fresh-price validity, contract sizing, SL/TP order attachment and fill reconciliation are not implemented.")
        st.divider()
else:
    st.info("No scan has been run in this session. Tap 'Fetch candles and scan now'.")

st.subheader("Methodology and limitations")
st.markdown("""
- Each timeframe is fetched natively from Delta's public historical candle endpoint; no timeframe resampling.
- The currently forming candle is removed before analysis.
- EMA200 trend uses the latest closed 15m candle.
- 5m structure break uses confirmed local swing pivots; this is a transparent BOS proxy, not a complete discretionary CHoCH model.
- 3m liquidity uses swing pivot clusters with at least three nearby touches, followed by sweep and close-back-through.
- 3m FVG uses a three-candle high/low imbalance. The dashboard reports its midpoint but does not wait for a later retracement.
- Historical REST polling is not a tick-level real-time feed. Use the timestamp shown to judge freshness.

Before any Demo execution is considered, this scanner needs independent signal-label validation, backtests with fees/slippage, setup deduplication/expiry, actual FVG retracement trigger, risk-to-contract conversion, attached protective SL/TP, order/fill reconciliation, and a kill switch.
""")
