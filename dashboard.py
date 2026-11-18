import streamlit as st
import pandas as pd
from config import SYMBOLS
from scanner import scan_symbol
from backtest import run_backtest, side_summaries

st.set_page_config(page_title="Delta SMC Bot v5.4 EMA200 Removed", page_icon="📈", layout="wide")
st.title("Delta SMC Bot v5.4 · EMA200 Removed")
st.caption("Public historical market data · closed candles · NO order execution")
st.warning("SAFE RESEARCH MODE: No API keys, no approvals, and no exchange orders. Results are historical estimates, not predictions.")
with st.sidebar:
    st.header("Research settings")
    selected = st.multiselect("Instruments", SYMBOLS, default=SYMBOLS)
    days = st.selectbox("Historical window", [7, 30, 90], index=0,
                        format_func=lambda x: f"{x} days" + (" · recommended first test" if x == 7 else ""))
    fee_bps = st.number_input("Estimated fee per side (bps)", min_value=0.0, max_value=50.0, value=5.0, step=0.5)
    slippage_bps = st.number_input("Estimated slippage per side (bps)", min_value=0.0, max_value=50.0, value=2.0, step=0.5)
    risk_pct = st.number_input("Risk assumption per trade (%)", min_value=0.1, max_value=2.0, value=0.5, step=0.1)
    st.caption("EMA200 is informational only — it does NOT block trades. Mandatory: 5m structure break + 3m liquidity (3+ touches) + sweep/reclaim + 3m FVG.")
    st.caption("Historical candle cache: 6 hours. One instrument is replayed at a time.")

tab1, tab2 = st.tabs(["Live scan (research only)", "Historical backtest"])
with tab1:
    if st.button("Fetch candles and scan now", type="primary", disabled=not selected):
        st.session_state["scan_results"] = {}
        for symbol in selected:
            with st.spinner(f"Scanning {symbol}…"):
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
                    st.warning("Not executable: retracement and exchange risk controls are not implemented.")
        st.divider()

with tab2:
    st.write("Walk-forward replay: only closed candles are used. Entry requires a later revisit to the FVG midpoint. Candle downloads are cached for six hours.")
    st.info("Start with 7 days. Run one instrument at a time to reduce CPU load. The 0.5% risk setting is an R-to-equity illustration only; no exchange contract sizing is performed.")
    run_symbol = st.selectbox("Instrument to backtest", selected or SYMBOLS, key="backtest_symbol")
    if st.button("Run historical backtest", type="primary", disabled=not selected):
        progress_bar = st.progress(0, text="Preparing backtest…")
        status = st.empty()
        try:
            def update_progress(value, message):
                progress_bar.progress(min(1.0, max(0.0, value)), text=message)
                status.caption(message)
            trades, summary, rejected = run_backtest(run_symbol, days=days, fee_bps=fee_bps,
                                           slippage_bps=slippage_bps, risk_pct=risk_pct,
                                           progress=update_progress)
            st.session_state["backtest_results"] = {run_symbol: {"trades": trades, "summary": summary, "rejected": rejected, "error": None}}
            progress_bar.progress(1.0, text="Backtest complete")
            status.success(f"{run_symbol} {days}-day backtest completed.")
        except Exception as exc:
            st.session_state["backtest_results"] = {run_symbol: {"trades": pd.DataFrame(), "summary": {}, "rejected": pd.DataFrame(), "error": str(exc)}}
            status.error(f"Backtest failed: {exc}")
    for symbol, item in st.session_state.get("backtest_results", {}).items():
        st.markdown(f"### {symbol} · {days}-day results")
        if item["error"]:
            st.error(item["error"]); continue
        s, trades = item["summary"], item["trades"]
        rejected = item.get("rejected", pd.DataFrame())
        a, b, c, d, e = st.columns(5)
        a.metric("Trades", s["trades"]); b.metric("Win rate", f"{s['win_rate_pct']:.2f}%")
        c.metric("Net R", s["net_R"]); d.metric("Profit factor", s["profit_factor"] if s["profit_factor"] is not None else "N/A")
        e.metric("Max drawdown (R)", s["max_drawdown_R"])
        st.metric("Illustrative return (non-compounded)", f"{s['return_pct']:.3f}%", help="Net R multiplied by selected fixed risk percentage. Not a live account return.")
        st.caption(s["note"])
        st.markdown("#### Separate LONG / SHORT reports")
        sides = side_summaries(trades, float(s["risk_pct"]))
        lcol, scol = st.columns(2)
        for col, side, label in ((lcol, "long", "LONG"), (scol, "short", "SHORT")):
            ss = sides[side]
            with col:
                st.markdown(f"**{label}**")
                st.write({"trades": ss["trades"], "win_rate_pct": ss["win_rate_pct"],
                          "net_R": ss["net_R"], "profit_factor": ss["profit_factor"],
                          "max_drawdown_R": ss["max_drawdown_R"]})
        if not trades.empty:
            st.markdown("#### Valid completed trades")
            st.dataframe(trades, use_container_width=True)
        else:
            st.info("No completed trades in this sample. This is a valid result; do not loosen mandatory filters just to force trades.")
        st.download_button(f"Download {symbol} trade log CSV", trades.to_csv(index=False),
                           file_name=f"{symbol.lower()}_{days}d_backtest.csv", mime="text/csv")
        st.metric("Rejected invalid candidates", s.get("rejected_candidates", 0))
        if not rejected.empty:
            with st.expander("Review rejected candidates and reasons"):
                st.dataframe(rejected, use_container_width=True)
                st.download_button(f"Download {symbol} rejected-candidate audit CSV",
                                   rejected.to_csv(index=False),
                                   file_name=f"{symbol.lower()}_{days}d_rejected_audit.csv",
                                   mime="text/csv")


st.subheader("Methodology & limitations")
st.markdown("""
- Native 3m/5m/15m public candles; currently forming candles excluded.
- Candle downloads are cached in Streamlit for six hours; cache is keyed by symbol, timeframe and days.
- One symbol is replayed at a time; progress is shown during download and candle replay.
- 15m EMA200 is informational only and never blocks a setup; 5m swing-break proxy is inherited from V4 and is not full discretionary BOS/CHoCH labeling.
- Liquidity clustering and FVG definitions are mechanical approximations and require chart-by-chart review.
- Entry is the FVG midpoint only after a later candle revisits that level. Stop is sweep-candle extreme; invalid stop/target geometry is rejected. Target must validate at 2R.
- LONG requires stop < entry < target; SHORT requires target < entry < stop. R is calculated from adverse entry fill to stop. If SL and TP are both touched in one OHLC candle, SL is assumed first. Gap-through stops use the worse candle open. Fees and slippage are estimates; funding, variable spread, latency, contract sizing and liquidation are not modeled.
- Risk% is used only to illustrate net_R × fixed risk%; no position size or exchange order is calculated.
- EMA200 filter is disabled in this experiment. All other SMC scanner gates remain mandatory. This is a research prototype, not a validated strategy or investment advice. Never connect exchange keys or enable order execution from this build.
""")
