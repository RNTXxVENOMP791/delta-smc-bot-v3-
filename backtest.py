"""V5.2 walk-forward research backtest with strict trade-geometry and R accounting checks.

Research only: public OHLC candles, no exchange orders, no contract sizing.
"""
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
    """Fetch and cache native historical candles; exclude still-forming bars."""
    if resolution not in TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {resolution}")
    seconds = TIMEFRAMES[resolution]
    now = int(time.time())
    start_all = now - int(days) * 86400
    frames, cursor = [], start_all
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
    if df.empty:
        raise DeltaDataError(f"No closed historical candles for {symbol} {resolution}")
    df["time_utc"] = pd.to_datetime(df.time, unit="s", utc=True)
    return df


def validate_trade_geometry(side: str, entry: float, stop: float, target: float,
                            rr_tolerance: float = 0.03) -> tuple[bool, str, float]:
    """Validate correct SL/TP sides and a target approximately 2R from planned entry."""
    vals = (entry, stop, target)
    if not all(np.isfinite(v) for v in vals):
        return False, "Non-finite entry/stop/target", 0.0
    if entry <= 0 or stop <= 0 or target <= 0:
        return False, "Entry, stop and target must be positive", 0.0
    risk = abs(entry - stop)
    if risk <= max(entry * 1e-9, 1e-12):
        return False, "Stop distance is zero or too small", 0.0
    if side == "long":
        if not stop < entry < target:
            return False, "Invalid LONG geometry: require stop < entry < target", risk
        actual_rr = (target - entry) / risk
    elif side == "short":
        if not target < entry < stop:
            return False, "Invalid SHORT geometry: require target < entry < stop", risk
        actual_rr = (entry - target) / risk
    else:
        return False, f"Unsupported side: {side}", risk
    if abs(actual_rr - 2.0) > rr_tolerance:
        return False, f"Target is not 2R (calculated RR={actual_rr:.4f})", risk
    return True, "OK", risk


def _summary(tdf: pd.DataFrame, risk_pct: float) -> dict:
    if tdf.empty:
        return {"trades": 0, "win_rate_pct": 0.0, "net_R": 0.0, "profit_factor": None,
                "max_drawdown_R": 0.0, "return_pct": 0.0,
                "note": "No valid completed trades under the strict rules in this sample."}
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
            "note": "Research estimate only. Return% = net_R × fixed risk%; not compounded. If SL and TP are both touched in one OHLC bar, SL is assumed first."}


def _bar_exit(side: str, bar: pd.Series, stop: float, target: float):
    """Return (outcome, raw exit) using conservative gap and same-bar rules."""
    o, h, l = float(bar.open), float(bar.high), float(bar.low)
    if side == "long":
        hit_sl, hit_tp = l <= stop, h >= target
        if hit_sl:
            return "SL", min(o, stop)  # gap through stop receives worse open
        if hit_tp:
            return "TP", target        # do not assume favorable target gap improvement
    else:
        hit_sl, hit_tp = h >= stop, l <= target
        if hit_sl:
            return "SL", max(o, stop)
        if hit_tp:
            return "TP", target
    return None, None


def run_backtest(symbol: str, days: int = 7, fee_bps: float = 5.0, slippage_bps: float = 2.0,
                 risk_pct: float = 0.5, max_signals: int = 250,
                 progress: ProgressFn = None, use_ema_filter: bool = False,
                 history_data: Optional[dict] = None) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Walk-forward replay with strict geometry validation and fill-based R accounting.

    A signal is only evaluated after closed candles. A later 3m candle must revisit
    the FVG midpoint. The planned target is 2R from signal entry. Stop is the
    scanner's sweep-candle extreme. Invalid stop/target geometry is rejected.
    One position per symbol at a time; overlapping candidate windows are skipped.
    """
    if days not in (7, 30, 90):
        raise ValueError("Choose 7, 30 or 90 days")
    if not (0.0 <= fee_bps <= 50.0 and 0.0 <= slippage_bps <= 50.0):
        raise ValueError("Fee and slippage must be between 0 and 50 bps per side")
    if not (0.1 <= risk_pct <= 2.0):
        raise ValueError("Risk assumption must be between 0.1% and 2.0%")
    if progress:
        progress(0.02, f"Loading cached/downloaded candles for {symbol}…")
    data = history_data if history_data is not None else {}
    for idx, tf in enumerate(("15m", "5m", "3m")):
        if tf not in data:
            data[tf] = fetch_history(symbol, tf, days)
        if progress:
            progress(0.08 + (idx + 1) * 0.12, f"{symbol}: {tf} candles ready ({len(data[tf]):,})")
    d15, d5, d3 = data["15m"], data["5m"], data["3m"]
    if min(len(d15), len(d5), len(d3)) < 210:
        raise DeltaDataError("Not enough aligned history for EMA200 and structure warm-up; try a longer window.")

    fee_rate, slip_rate = fee_bps / 10000.0, slippage_bps / 10000.0
    trades, rejected = [], []
    seen_signals = set()
    start_i = 205
    total = max(1, len(d3) - start_i - 2)
    t15 = d15.time.to_numpy(dtype="int64")
    t5 = d5.time.to_numpy(dtype="int64")
    t3 = d3.time.to_numpy(dtype="int64")
    step_update = max(1, total // 100)
    busy_until = start_i - 1

    for i in range(start_i, len(d3) - 2):
        if i <= busy_until:
            continue
        ts = int(t3[i] + TIMEFRAMES["3m"])
        n15 = int(np.searchsorted(t15 + TIMEFRAMES["15m"], ts, side="right"))
        n5 = int(np.searchsorted(t5 + TIMEFRAMES["5m"], ts, side="right"))
        h15 = d15.iloc[max(0, n15 - 500):n15]
        h5 = d5.iloc[max(0, n5 - 300):n5]
        h3 = d3.iloc[max(0, i + 1 - 700):i + 1]
        if len(h15) < 205 or len(h5) < 20 or len(h3) < 205:
            continue
        try:
            evaluations = analyze(symbol, h15, h5, h3, use_ema_filter=use_ema_filter)
        except Exception as exc:
            rejected.append({"symbol": symbol, "signal_time": d3.time_utc.iloc[i].isoformat(),
                             "reason": f"Scanner error: {type(exc).__name__}: {exc}"})
            continue
        for candidate in evaluations:
            if candidate.get("candidate") is False or "entry" not in candidate:
                continue
            side = str(candidate.get("side", "")).lower()
            signal_time = candidate.get("signal_time", d3.time_utc.iloc[i].isoformat())
            key = (side, signal_time)
            if key in seen_signals:
                continue
            seen_signals.add(key)
            try:
                planned_entry = float(candidate["entry"])
                stop = float(candidate["stop"])
                supplied_target = float(candidate.get("target", np.nan))
            except (TypeError, ValueError, KeyError):
                rejected.append({"symbol": symbol, "side": side, "signal_time": signal_time,
                                 "reason": "Missing or non-numeric entry/stop/target"})
                continue
            valid, reason, planned_risk = validate_trade_geometry(side, planned_entry, stop, supplied_target)
            if not valid:
                rejected.append({"symbol": symbol, "side": side, "signal_time": signal_time,
                                 "entry": planned_entry, "stop": stop, "target": supplied_target,
                                 "reason": reason})
                continue

            fill_i = None
            for j in range(i + 1, min(i + 101, len(d3))):
                bar = d3.iloc[j]
                if float(bar.low) <= planned_entry <= float(bar.high):
                    fill_i = j
                    break
            if fill_i is None:
                continue

            direction = 1 if side == "long" else -1
            entry_fill = planned_entry * (1 + slip_rate if side == "long" else 1 - slip_rate)
            # Risk is measured from the actual adverse entry fill to the original stop.
            actual_risk = direction * (entry_fill - stop)
            if not np.isfinite(actual_risk) or actual_risk <= max(entry_fill * 1e-9, 1e-12):
                rejected.append({"symbol": symbol, "side": side, "signal_time": signal_time,
                                 "entry": entry_fill, "stop": stop, "target": supplied_target,
                                 "reason": "Adverse entry slippage crossed or invalidated the stop"})
                continue

            outcome = exit_raw = exit_i = None
            for j in range(fill_i, min(fill_i + 101, len(d3))):
                outcome, exit_raw = _bar_exit(side, d3.iloc[j], stop, supplied_target)
                if outcome:
                    exit_i = j
                    break
            if outcome is None:
                continue  # open/unresolved trades are not counted as completed

            exit_fill = exit_raw * (1 - slip_rate if side == "long" else 1 + slip_rate)
            gross_r = direction * (exit_fill - entry_fill) / actual_risk
            cost_quote = (abs(entry_fill) + abs(exit_fill)) * fee_rate
            cost_r = cost_quote / actual_risk
            net_r = gross_r - cost_r
            # Sanity guard: after valid geometry, SL must not be a positive gross result.
            if outcome == "SL" and gross_r > 1e-9:
                rejected.append({"symbol": symbol, "side": side, "signal_time": signal_time,
                                 "reason": "Accounting invariant failed: SL produced positive gross R"})
                continue
            trades.append({"symbol": symbol, "side": side, "signal_time": signal_time,
                           "entry_time": d3.time_utc.iloc[fill_i].isoformat(),
                           "exit_time": d3.time_utc.iloc[exit_i].isoformat(),
                           "planned_entry": planned_entry, "entry_fill": entry_fill,
                           "stop": stop, "target": supplied_target, "actual_risk_per_unit": actual_risk,
                           "exit_raw": exit_raw, "exit_fill": exit_fill, "outcome": outcome,
                           "gross_R": gross_r, "estimated_cost_R": cost_r, "net_R": net_r,
                           "fee_bps_per_side": fee_bps, "slippage_bps_per_side": slippage_bps,
                           "risk_pct_assumption": risk_pct, "touches": candidate.get("touches", 0)})
            busy_until = exit_i
            break  # only one position at a time per instrument
        if progress and ((i - start_i) % step_update == 0 or i == len(d3) - 3):
            frac = (i - start_i + 1) / total
            progress(0.32 + 0.66 * min(1.0, frac),
                     f"{symbol}: replaying 3m candles {int(frac * 100)}% · {len(trades)} trades · {len(rejected)} rejected")
        if len(trades) >= max_signals:
            break

    tdf = pd.DataFrame(trades)
    summary = _summary(tdf, risk_pct)
    summary.update({"candles_3m": int(len(d3)), "candles_5m": int(len(d5)),
                    "candles_15m": int(len(d15)), "risk_pct": risk_pct,
                    "ema200_filter": "mandatory" if use_ema_filter else "removed",
                    "rejected_candidates": len(rejected)})
    summary["note"] += (" Fees and slippage are estimated per side. Funding, variable spread, contract sizing, "
                        "liquidation, latency and compounding are not modeled. Invalid trade geometry is rejected. "
                        "Unresolved open trades at the end of the replay are excluded.")
    rejected_df = pd.DataFrame(rejected)
    return tdf, summary, rejected_df


def side_summaries(trades: pd.DataFrame, risk_pct: float) -> dict:
    return {side: _summary(trades[trades.side == side].reset_index(drop=True), risk_pct)
            for side in ("long", "short")}
