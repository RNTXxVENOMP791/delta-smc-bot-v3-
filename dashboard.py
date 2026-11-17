import json
import pandas as pd
import streamlit as st
from config import DEFAULT_VIRTUAL_BALANCE, SYMBOLS
from store import init_db, add_signal, all_signals, get_signal, update_signal
from telegram_notify import send_telegram
from demo_execution import submit_approved_demo_entry

st.set_page_config(page_title="Delta SMC v3.0", page_icon="📈", layout="wide")
init_db()
st.title("Delta SMC Bot v3.0")
st.caption("Human-approved entries · Delta Demo only · Telegram + dashboard")

st.warning("DEMO ENTRY ONLY. This version does not attach protective stop-loss/take-profit orders or manage exits. Do not use live credentials. Verify product specs and contract sizing before any Demo submission.")

with st.sidebar:
    st.header("Risk settings")
    virtual_balance = st.number_input("Custom virtual balance (USD)", min_value=50.0,
                                      value=float(DEFAULT_VIRTUAL_BALANCE), step=50.0)
    risk_percent = st.select_slider("Risk per signal (%)", options=[0.25, 0.5, 0.75, 1.0], value=0.5)
    st.metric("Risk budget per signal", f"${virtual_balance * risk_percent / 100:.2f}")
    st.divider()
    st.caption("Virtual balance and risk budget are informational in this approval-workflow build. They do not determine exchange contract quantity.")

st.subheader("Signal inbox")
signals = all_signals()
pending = [s for s in signals if s["status"] == "PENDING_APPROVAL"]

if pending:
    for signal in pending:
        with st.container(border=True):
            st.markdown(f"### #{signal['id']} · {signal['symbol']} · {signal['side'].upper()}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Signal entry", f"{signal['entry']:,.2f}")
            c2.metric("Stop reference", f"{signal['stop']:,.2f}")
            c3.metric("Target reference", f"{signal['target']:,.2f}")
            st.caption("Check current market price and setup validity yourself. Signal auto-expires after 3 minutes.")
            st.error("No protective SL/TP is attached by this build. Demo entry only.")
            if st.button("Reject signal", key=f"reject{signal['id']}"):
                update_signal(signal["id"], "REJECTED", "Rejected by user.")
                send_telegram(f"Delta SMC signal #{signal['id']} {signal['symbol']} rejected.")
                st.rerun()
            with st.form(f"approve{signal['id']}"):
                st.write("Demo order confirmation")
                product_symbol = st.selectbox("Confirm Demo product symbol", SYMBOLS,
                                              index=SYMBOLS.index(signal["symbol"]))
                contract_size = st.number_input("Contract quantity (integer)", min_value=1, value=1, step=1)
                confirmation = st.text_input('Type "SUBMIT DEMO" to enable submission')
                submitted = st.form_submit_button("Approve and submit to Delta Demo")
                if submitted:
                    try:
                        result = submit_approved_demo_entry(signal["id"], product_symbol,
                                                            int(contract_size), confirmation)
                        st.success("Demo entry submitted. API response:")
                        st.json(result)
                        send_telegram(f"Delta SMC: Demo entry submitted for #{signal['id']} {signal['symbol']} {signal['side']}. Check Demo account for order/fill.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
else:
    st.info("No pending signals. The live SMC scanner is not connected in this build.")

st.subheader("Signal history")
history = all_signals()
if history:
    frame = pd.DataFrame(history)
    st.dataframe(frame.drop(columns=["order_response"], errors="ignore"), use_container_width=True)
    st.download_button("Download history CSV", frame.to_csv(index=False),
                       "delta_smc_signal_history.csv", "text/csv")

st.divider()
st.subheader("Create a test approval card")
st.caption("This creates a dummy signal only to test the dashboard workflow. It is not a market-generated SMC signal.")
with st.form("dummy"):
    sym = st.selectbox("Test instrument", SYMBOLS)
    direction = st.selectbox("Test direction", ["long", "short"])
    default_entry = 65000.0 if sym == "BTCUSD" else 3500.0
    entry = st.number_input("Illustrative entry", min_value=0.01, value=default_entry)
    stop = st.number_input("Illustrative stop", min_value=0.01,
                           value=entry - 500 if direction == "long" else entry + 30)
    make = st.form_submit_button("Create dummy approval card")
    if make:
        if (direction == "long" and stop >= entry) or (direction == "short" and stop <= entry):
            st.error("Stop is on the wrong side of entry.")
        else:
            target = entry + 2 * abs(entry-stop) if direction == "long" else entry - 2 * abs(entry-stop)
            from datetime import datetime, timezone
            signal = {"symbol":sym, "side":direction, "entry":entry, "stop":stop,
                      "target":target, "risk_cash":virtual_balance*risk_percent/100,
                      "created_at":datetime.now(timezone.utc).isoformat(), "note":"DUMMY TEST ONLY"}
            sid = add_signal(signal)
            ok, message = send_telegram(f"TEST signal #{sid}: {sym} {direction.upper()} Entry {entry}, SL {stop}, TP {target}. Dashboard approval required.")
            st.success(f"Dummy signal #{sid} created. Telegram: {message}")
            st.rerun()
