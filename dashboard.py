import streamlit as st
import pandas as pd
from config import SYMBOLS
from scanner import scan_symbol, DeltaDataError
from backtest import run_backtest

st.set_page_config(page_title="Delta SMC Bot v5 Research", page_icon="📈", layout="wide")
st.title("Delta SMC Bot v5 · Research & Backtesting")
st.caption("Public historical market data · closed candles · NO order execution")
st.warning("SAFE RESEARCH MODE: No API keys, no approvals, and no exchange orders. Backtest results are estimates, not predictions.")
with st.sidebar:
    st.header("Research settings")
    selected = st.multiselect("Instruments", SYMBOLS, default=SYMBOLS)
    days = st.selectbox("Historical window", [30, 60, 90], index=2)
    fee_bps = st.number_input("Estimated fee per side (bps)", min_value=0.0, max_value=50.0, value=5.0, step=0.5)
    slippage_bps = st.number_input("Estimated slippage per side (bps)", min_value=0.0, max_value=50.0, value=2.0, step=0.5)
    st.caption("Strategy filters remain strict: 15m EMA200, 5m swing-break proxy, 3m liquidity (3+ touches) + sweep/reclaim, and 3m FVG.")

tab1, tab2 = st.tabs(["Live scan (research only)", "Historical backtest"])
with tab1:
    if st.button("Fetch candles and scan now", type="primary", disabled=not selected):
        st.session_state["scan_results"] = {}
        for symbol in selected:
            with st.spinner(f"Scanning {symbol}..."):
                try:
                    data, results = scan_symbol(symbol)
                    st.session_state.scan_results[symbol] = {"data": data, "results": results, "error": None}
                except Exception as exc:
                    st.session_state.scan_results[symbol] = {"data": None, "results": [], "error": str(exc)}
    for symbol, item in st.session_state.get("scan_results", {}).items():
        st.markdown(f"### {symbol}")
        if item["error"]:
            st.error(item["error"]); continue
        cols = st.columns(3)
        for col, tf in zip(cols, ("15m", "5m", "3m")):
            df = item["data"][tf]
            col.metric(f"{tf} closed candles", len(df))
            col.caption(f"Last close: {float(df.close.iloc[-1]):,.4f}")
        for res in item["results"]:
            with st.container(border=True):
                st.markdown(f"**{res['side'].upper()} setup evaluation**")
                if res.get("candidate") is False:
                    st.info("No complete setup — at least one mandatory condition failed.")
                    st.write(res["checks"]); st.caption(" · ".join(res.get("reasons", [])))
                else:
                    st.success("Coded filters matched — research candidate only")
                    st.write({k: v for k, v in res.items() if k != "checks"})
                    st.warning("Not executable: retracement/freshness and exchange risk controls are not implemented.")
        st.divider()
with tab2:
    st.write("Walk-forward replay. Candidate detection uses only candles closed at each evaluation time. Entry requires a later revisit to the FVG midpoint.")
    if st.button("Run historical backtest", type="primary", disabled=not selected):
        st.session_state["backtest_results"] = {}
        for symbol in selected:
            with st.spinner(f"Downloading and replaying {days} days for {symbol}; this may take a few minutes..."):
                try:
                    trades, summary = run_backtest(symbol, days=days, fee_bps=fee_bps, slippage_bps=slippage_bps)
                    st.session_state.backtest_results[symbol] = {"trades": trades, "summary": summary, "error": None}
                except Exception as exc:
                    st.session_state.backtest_results[symbol] = {"trades": pd.DataFrame(), "summary": {}, "error": str(exc)}
    for symbol, item in st.session_state.get("backtest_results", {}).items():
        st.markdown(f"### {symbol}")
        if item["error"]:
            st.error(item["error"]); continue
        s = item["summary"]
        a,b,c,d,e = st.columns(5)
        a.metric("Trades", s["trades"]); b.metric("Win rate", f"{s['win_rate_pct']:.2f}%")
        c.metric("Net R", s["net_R"]); d.metric("Profit factor", s["profit_factor"] if s["profit_factor"] is not None else "N/A")
        e.metric("Max drawdown (R)", s["max_drawdown_R"])
        st.caption(s["note"])
        if not item["trades"].empty:
            st.dataframe(item["trades"], use_container_width=True)
            st.download_button(f"Download {symbol} trade log CSV", item["trades"].to_csv(index=False), file_name=f"{symbol.lower()}_backtest.csv", mime="text/csv")

st.subheader("Methodology & limitations")
st.markdown("""
- Native 3m/5m/15m public candles; currently forming candles excluded.
- 15m EMA200 and 5m swing-break proxy are inherited from the V4 scanner; this is not full discretionary BOS/CHoCH labeling.
- Liquidity clustering and FVG definitions are mechanical approximations and need chart-by-chart review.
- Backtest uses FVG midpoint entry only after a later candle revisits that level; no revisit means no trade.
- Stop is sweep-candle extreme; target is fixed 2R. If stop and target are both inside one OHLC candle, stop is assumed first.
- Fees and slippage are user-entered estimates per side; funding, spread variation, latency, contract sizing and liquidation are not modeled.
- Historical API availability/rate limits may constrain 90-day retrieval. Check candle coverage before trusting metrics.
- This is a research prototype, not a validated strategy or investment advice. Never connect exchange keys or enable order execution from this build.
""")
