"""V5 walk-forward research backtest scaffold. No order execution."""
from __future__ import annotations
import time
import requests
import pandas as pd
from scanner import TIMEFRAMES, BASE_URL, DeltaDataError, analyze


def fetch_history(symbol: str, resolution: str, days: int = 90, chunk_bars: int = 1800) -> pd.DataFrame:
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
        time.sleep(0.12)
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
    # Keep only candles that have fully closed.
    df = df[df.time + seconds <= now].reset_index(drop=True)
    df["time_utc"] = pd.to_datetime(df.time, unit="s", utc=True)
    return df


def _slice_closed_by(df: pd.DataFrame, timestamp: int, resolution: str) -> pd.DataFrame:
    # A candle is available only after its full interval has elapsed.
    return df[df.time + TIMEFRAMES[resolution] <= timestamp].reset_index(drop=True)


def run_backtest(symbol: str, days: int = 90, fee_bps: float = 5.0, slippage_bps: float = 2.0,
                 max_signals: int = 250) -> tuple[pd.DataFrame, dict]:
    """Walk-forward replay using closed candles only.

    Candidate is evaluated after a 3m candle closes. Entry is only counted if
    subsequent candles revisit the FVG midpoint. Stop is sweep-candle extreme;
    target is 2R. If SL and TP are both touched in one candle, conservatively
    count SL first. Fees/slippage are approximate bps on entry and exit notional.
    """
    d15 = fetch_history(symbol, "15m", days)
    d5 = fetch_history(symbol, "5m", days)
    d3 = fetch_history(symbol, "3m", days)
    if min(len(d15), len(d5), len(d3)) < 210:
        raise DeltaDataError("Not enough aligned history for EMA200 and structure warm-up")
    fee_rate = max(0.0, fee_bps) / 10000.0
    slip_rate = max(0.0, slippage_bps) / 10000.0
    trades = []
    last_signal_key = None
    # Evaluate on a spaced walk-forward sample; every new 3m close after warmup.
    start_i = 205
    for i in range(start_i, len(d3) - 2):
        ts = int(d3.time.iloc[i] + TIMEFRAMES["3m"])
        h15 = _slice_closed_by(d15, ts, "15m")
        h5 = _slice_closed_by(d5, ts, "5m")
        h3 = d3.iloc[: i + 1].reset_index(drop=True)
        if len(h15) < 205 or len(h5) < 20 or len(h3) < 205:
            continue
        try:
            _, candidates = None, analyze(symbol, h15.tail(500), h5.tail(300), h3.tail(700))
        except Exception:
            continue
        for c in candidates:
            if c.get("candidate") is False or "entry" not in c:
                continue
            key = (c["side"], c["signal_time"])
            if key == last_signal_key:
                continue
            last_signal_key = key
            entry_mid = float(c["entry"])
            side = c["side"]
            stop = float(c["stop"])
            risk = abs(entry_mid - stop)
            if risk <= 0:
                continue
            target = entry_mid + 2*risk if side == "long" else entry_mid - 2*risk
            outcome = None
            fill_i = None
            # Search only after signal candle; midpoint must be revisited.
            for j in range(i + 1, min(i + 101, len(d3))):
                bar = d3.iloc[j]
                if float(bar.low) <= entry_mid <= float(bar.high):
                    fill_i = j
                    break
            if fill_i is None:
                continue
            fill = entry_mid * (1 + slip_rate if side == "long" else 1 - slip_rate)
            exit_price = None
            exit_i = None
            for j in range(fill_i, min(fill_i + 101, len(d3))):
                bar = d3.iloc[j]
                lo, hi = float(bar.low), float(bar.high)
                if side == "long":
                    hit_sl, hit_tp = lo <= stop, hi >= target
                else:
                    hit_sl, hit_tp = hi >= stop, lo <= target
                if hit_sl:  # conservative if both touched within same OHLC bar
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
            # Approximate round-trip fee on entry+exit price.
            cost_r = (abs(fill) + abs(exit_exec)) * fee_rate / risk
            net_r = gross_r - cost_r
            trades.append({"symbol": symbol, "side": side, "signal_time": c["signal_time"],
                           "entry_time": d3.time_utc.iloc[fill_i].isoformat(),
                           "exit_time": d3.time_utc.iloc[exit_i].isoformat(),
                           "entry": fill, "stop": stop, "target": target,
                           "outcome": outcome, "gross_R": gross_r, "estimated_cost_R": cost_r,
                           "net_R": net_r, "touches": c.get("touches", 0)})
            if len(trades) >= max_signals:
                break
        if len(trades) >= max_signals:
            break
    tdf = pd.DataFrame(trades)
    if tdf.empty:
        summary = {"trades": 0, "win_rate_pct": 0.0, "net_R": 0.0, "profit_factor": None,
                   "max_drawdown_R": 0.0, "note": "No completed trades under the coded strict rules in this sample."}
        return tdf, summary
    wins = tdf[tdf.net_R > 0]
    losses = tdf[tdf.net_R <= 0]
    equity = tdf.net_R.cumsum()
    drawdown = equity - equity.cummax()
    gross_profit = wins.net_R.sum()
    gross_loss = abs(losses.net_R.sum())
    summary = {"trades": int(len(tdf)), "win_rate_pct": round(100*len(wins)/len(tdf), 2),
               "net_R": round(float(tdf.net_R.sum()), 3),
               "profit_factor": round(float(gross_profit/gross_loss), 3) if gross_loss else None,
               "max_drawdown_R": round(float(drawdown.min()), 3),
               "note": "Research estimate only; OHLC intrabar ordering is unknown. SL is assumed first if SL and TP occur in the same candle."}
    return tdf, summary
