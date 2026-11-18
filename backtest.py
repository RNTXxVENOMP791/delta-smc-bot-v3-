"""V5.1 optimized walk-forward research backtest. No order execution."""
from __future__ import annotations
import time
from typing import Callable, Optional
import requests
import pandas as pd
import numpy as np
import streamlit as st
from scanner import TIMEFRAMES, BASE_URL, DeltaDataError, analyze

ProgressFn = Optional[Callable[[float, str], None]]

@st.cache_data(ttl=6 * 60 * 60, show_spinner=False, max_entries=24)
def fetch_history(symbol: str, resolution: str, days: int = 90, chunk_bars: int = 1800) -> pd.DataFrame:
    """Cached historical candles. Cache key includes symbol, timeframe and window."""
    if resolution not in TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {resolution}")
    seconds = TIMEFRAMES[resolution]
    now = int(time.time())
    start_all = now - int(days) * 86400
    frames = []
    cursor = start_all
    while cursor < now:
        end = min(now, cursor + chunk_bars * seconds)
        response = requests.get(
            f"{BASE_URL}/v2/history/candles",
            params={"resolution": resolution, "symbol": symbol, "start": cursor, "end": end},
            timeout=25,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success") or not isinstance(payload.get("result"), list):
            raise DeltaDataError(f"Unexpected history response for {symbol} {resolution}")
        if payload["result"]:
            frames.append(pd.DataFrame(payload["result"]))
        cursor = end
        # Small pause between API chunks; no sleep after the final chunk.
        if cursor < now:
            time.sleep(0.05)
    if not frames:
        raise DeltaDataError(f"No historical candles for {symbol} {resolution}")
    df = pd.concat(frames, ignore_index=True)
    required = ["time", "open", "high", "low", "close", "volume"]
    if not set(required).issubset(df.columns):
        raise DeltaDataError("Historical response is missing candle fields")
    df = df[required].copy()
    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df = df[df.time + seconds <= now].reset_index(drop=True)
    df["time_utc"] = pd.to_datetime(df.time, unit="s", utc=True)
    return df


def _summary(tdf: pd.DataFrame, risk_pct: float) -> dict:
    if tdf.empty:
        return {"trades": 0, "win_rate_pct": 0.0, "net_R": 0.0, "profit_factor": None,
                "max_drawdown_R": 0.0, "return_pct": 0.0,
                "note": "No completed trades under the coded strict rules in this sample."}
    wins = tdf[tdf.net_R > 0]
    losses = tdf[tdf.net_R <= 0]
    equity_r = tdf.net_R.cumsum()
    drawdown = equity_r - equity_r.cummax()
    gross_profit = float(wins.net_R.sum())
    gross_loss = abs(float(losses.net_R.sum()))
    return {"trades": int(len(tdf)), "win_rate_pct": round(100 * len(wins) / len(tdf), 2),
            "net_R": round(float(tdf.net_R.sum()), 3),
            "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else None,
            "max_drawdown_R": round(float(drawdown.min()), 3),
            "return_pct": round(float(tdf.net_R.sum()) * risk_pct, 3),
            "note": "Research estimate only. Return% is net_R × fixed risk%; it is not compounded. OHLC intrabar ordering is unknown; SL is assumed first if both SL and TP are touched in one candle."}


def run_backtest(symbol: str, days: int = 7, fee_bps: float = 5.0, slippage_bps: float = 2.0,
                 risk_pct: float = 0.5, max_signals: int = 250,
                 progress: ProgressFn = None) -> tuple[pd.DataFrame, dict]:
    """Walk-forward replay using closed candles only; one symbol per run.

    Candidate is evaluated after each 3m candle close. A later midpoint revisit
    is required for entry. Stop is sweep-candle extreme; target is 2R. When both
    are touched in one OHLC bar, stop is counted first (conservative assumption).
    """
    if days not in (7, 30, 90):
        raise ValueError("Choose 7, 30 or 90 days")
    if progress:
        progress(0.02, f"Loading cached/downloaded candles for {symbol}…")
    data = {}
    for idx, tf in enumerate(("15m", "5m", "3m")):
        data[tf] = fetch_history(symbol, tf, days)
        if progress:
            progress(0.08 + (idx + 1) * 0.12, f"{symbol}: {tf} candles ready ({len(data[tf]):,})")
    d15, d5, d3 = data["15m"], data["5m"], data["3m"]
    if min(len(d15), len(d5), len(d3)) < 210:
        raise DeltaDataError("Not enough aligned history for EMA200 and structure warm-up; try a longer window.")

    fee_rate = max(0.0, fee_bps) / 10000.0
    slip_rate = max(0.0, slippage_bps) / 10000.0
    trades = []
    seen_signals = set()
    start_i = 205
    total = max(1, len(d3) - start_i - 2)
    # Pre-convert timestamps once; use searchsorted rather than filtering full frames each iteration.
    t15 = d15.time.to_numpy(dtype="int64")
    t5 = d5.time.to_numpy(dtype="int64")
    t3 = d3.time.to_numpy(dtype="int64")
    step_update = max(1, total // 100)

    for i in range(start_i, len(d3) - 2):
        ts = int(t3[i] + TIMEFRAMES["3m"])
        n15 = int(np.searchsorted(t15 + TIMEFRAMES["15m"], ts, side="right"))
        n5 = int(np.searchsorted(t5 + TIMEFRAMES["5m"], ts, side="right"))
        h15 = d15.iloc[max(0, n15 - 500):n15]
        h5 = d5.iloc[max(0, n5 - 300):n5]
        h3 = d3.iloc[max(0, i + 1 - 700):i + 1]
        if len(h15) < 205 or len(h5) < 20 or len(h3) < 205:
            continue
        try:
            # analyze() returns a list of LONG/SHORT evaluations (not a tuple).
            evaluations = analyze(symbol, h15, h5, h3)
        except Exception:
            continue
        for candidate in evaluations:
            if candidate.get("candidate") is False or "entry" not in candidate:
                continue
            key = (candidate["side"], candidate["signal_time"])
            if key in seen_signals:
                continue
            seen_signals.add(key)
            entry_mid = float(candidate["entry"])
            side = candidate["side"]
            stop = float(candidate["stop"])
            risk = abs(entry_mid - stop)
            if risk <= 0:
                continue
            target = entry_mid + 2 * risk if side == "long" else entry_mid - 2 * risk
            fill_i = None
            # Only later candles may fill the midpoint.
            for j in range(i + 1, min(i + 101, len(d3))):
                bar = d3.iloc[j]
                if float(bar.low) <= entry_mid <= float(bar.high):
                    fill_i = j
                    break
            if fill_i is None:
                continue
            fill = entry_mid * (1 + slip_rate if side == "long" else 1 - slip_rate)
            outcome, exit_price, exit_i = None, None, None
            for j in range(fill_i, min(fill_i + 101, len(d3))):
                bar = d3.iloc[j]
                lo, hi = float(bar.low), float(bar.high)
                if side == "long":
                    hit_sl, hit_tp = lo <= stop, hi >= target
                else:
                    hit_sl, hit_tp = hi >= stop, lo <= target
                if hit_sl:
                    outcome, exit_price, exit_i = "SL", stop, j
                    break
                if hit_tp:
                    outcome, exit_price, exit_i = "TP", target, j
                    break
            if outcome is None:
                continue
            exit_exec = exit_price * (1 - slip_rate if side == "long" else 1 + slip_rate)
            direction = 1 if side == "long" else -1
            gross_r = direction * (exit_exec - fill) / risk
            cost_r = (abs(fill) + abs(exit_exec)) * fee_rate / risk
            net_r = gross_r - cost_r
            trades.append({"symbol": symbol, "side": side, "signal_time": candidate["signal_time"],
                           "entry_time": d3.time_utc.iloc[fill_i].isoformat(),
                           "exit_time": d3.time_utc.iloc[exit_i].isoformat(),
                           "entry": fill, "stop": stop, "target": target, "outcome": outcome,
                           "gross_R": gross_r, "estimated_cost_R": cost_r, "net_R": net_r,
                           "risk_pct_assumption": risk_pct, "touches": candidate.get("touches", 0)})
            if len(trades) >= max_signals:
                break
        if progress and ((i - start_i) % step_update == 0 or i == len(d3) - 3):
            frac = (i - start_i + 1) / total
            progress(0.32 + 0.66 * min(1.0, frac), f"{symbol}: replaying 3m candles {int(frac * 100)}% · {len(trades)} completed trades")
        if len(trades) >= max_signals:
            break

    tdf = pd.DataFrame(trades)
    summary = _summary(tdf, risk_pct)
    summary["candles_3m"] = int(len(d3))
    summary["candles_5m"] = int(len(d5))
    summary["candles_15m"] = int(len(d15))
    summary["risk_pct"] = risk_pct
    summary["note"] += " Fees/slippage are approximate; funding, variable spread, contract sizing, liquidation and compounding are not modeled."
    return tdf, summary


def side_summaries(trades: pd.DataFrame, risk_pct: float) -> dict:
    return {side: _summary(trades[trades.side == side].reset_index(drop=True), risk_pct)
            for side in ("long", "short")}
