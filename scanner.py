"""V4 research scanner: public market data only; never places orders."""
from __future__ import annotations
from datetime import datetime, timezone
import time
import requests
import pandas as pd

BASE_URL = "https://api.india.delta.exchange"
TIMEFRAMES = {"3m": 180, "5m": 300, "15m": 900}

class DeltaDataError(RuntimeError):
    pass

def fetch_candles(symbol: str, resolution: str, bars: int = 500) -> pd.DataFrame:
    if resolution not in TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {resolution}")
    bars = max(220, min(int(bars), 1900))
    end = int(time.time())
    start = end - bars * TIMEFRAMES[resolution]
    url = f"{BASE_URL}/v2/history/candles"
    try:
        r = requests.get(url, params={"resolution": resolution, "symbol": symbol,
                                     "start": start, "end": end}, timeout=20)
        r.raise_for_status()
        payload = r.json()
    except (requests.RequestException, ValueError) as exc:
        raise DeltaDataError(f"Delta candle request failed ({symbol} {resolution}): {exc}") from exc
    if not payload.get("success") or not isinstance(payload.get("result"), list):
        raise DeltaDataError(f"Unexpected Delta response for {symbol} {resolution}: {payload}")
    df = pd.DataFrame(payload["result"])
    if df.empty:
        raise DeltaDataError(f"No candles returned for {symbol} {resolution}")
    required = ["time", "open", "high", "low", "close", "volume"]
    if not set(required).issubset(df.columns):
        raise DeltaDataError(f"Missing candle fields for {symbol} {resolution}")
    df = df[required].copy()
    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().drop_duplicates("time").sort_values("time").reset_index(drop=True)
    # Remove the currently forming candle. Delta timestamps represent candle open time.
    now = int(time.time())
    df = df[df["time"] + TIMEFRAMES[resolution] <= now].reset_index(drop=True)
    if len(df) < 205:
        raise DeltaDataError(f"Need at least 205 closed {resolution} candles; received {len(df)}")
    df["time_utc"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df

def _pivots(df: pd.DataFrame, left: int = 2, right: int = 2):
    highs, lows = [], []
    for i in range(left, len(df)-right):
        h = df.high.iloc[i]
        l = df.low.iloc[i]
        if h >= df.high.iloc[i-left:i+right+1].max(): highs.append((i, float(h)))
        if l <= df.low.iloc[i-left:i+right+1].min(): lows.append((i, float(l)))
    return highs, lows

def _touch_count(pivots, level: float, tolerance: float):
    return sum(abs(price-level) <= tolerance for _, price in pivots)

def _liquidity_level(df: pd.DataFrame, side: str):
    # Longs sweep clustered swing lows; shorts sweep clustered swing highs.
    hi, lo = _pivots(df.iloc[-180:].reset_index(drop=True))
    pivots = lo if side == "long" else hi
    if not pivots: return None
    current = float(df.close.iloc[-1])
    candidates = []
    for _, price in pivots[:-1]:
        tol = max(current * 0.0007, 1e-8)
        touches = _touch_count(pivots, price, tol)
        if touches >= 3:
            candidates.append((touches, price, tol))
    if not candidates: return None
    candidates.sort(key=lambda x: (x[0], -abs(current-x[1])), reverse=True)
    return candidates[0]

def _structure_break(df: pd.DataFrame, side: str):
    # Confirmed 5m swing level broken by the most recent closed candle.
    swings_h, swings_l = _pivots(df.iloc[-100:].reset_index(drop=True))
    if len(df) < 5: return False, "Insufficient structure candles"
    close = float(df.close.iloc[-1])
    if side == "long":
        levels = [p for i,p in swings_h if i < len(df)-3]
        ok = bool(levels and close > max(levels[-4:]))
        return ok, "5m close broke recent swing high" if ok else "No confirmed bullish BOS/CHoCH"
    levels = [p for i,p in swings_l if i < len(df)-3]
    ok = bool(levels and close < min(levels[-4:]))
    return ok, "5m close broke recent swing low" if ok else "No confirmed bearish BOS/CHoCH"

def _fvg(df: pd.DataFrame, side: str):
    # Three-candle imbalance on the latest closed 3m candles; use midpoint entry.
    if len(df) < 3: return None
    a, c = df.iloc[-3], df.iloc[-1]
    if side == "long" and float(c.low) > float(a.high):
        lo, hi = float(a.high), float(c.low)
        return lo, hi, (lo+hi)/2
    if side == "short" and float(c.high) < float(a.low):
        lo, hi = float(c.high), float(a.low)
        return lo, hi, (lo+hi)/2
    return None

def analyze(symbol: str, d15: pd.DataFrame, d5: pd.DataFrame, d3: pd.DataFrame):
    close15 = d15.close.astype(float)
    ema200 = close15.ewm(span=200, adjust=False).mean().iloc[-1]
    px15 = float(close15.iloc[-1])
    trend = "long" if px15 > ema200 else "short" if px15 < ema200 else "neutral"
    results = []
    for side in ("long", "short"):
        reasons, checks = [], {}
        checks["15m EMA200 trend"] = trend == side
        if not checks["15m EMA200 trend"]: reasons.append(f"15m price not aligned {side} of EMA200")
        bos, bos_text = _structure_break(d5, side)
        checks["5m structure break"] = bos
        if not bos: reasons.append(bos_text)
        liq = _liquidity_level(d3, side)
        swept = False
        if liq:
            touches, level, tol = liq
            last = d3.iloc[-1]
            if side == "long": swept = float(last.low) < level-tol*0.15 and float(last.close) > level
            else: swept = float(last.high) > level+tol*0.15 and float(last.close) < level
            checks["3m liquidity (3+ touches) + sweep/reclaim"] = swept
            if not swept: reasons.append("Liquidity cluster found, but no confirmed sweep/reclaim")
        else:
            checks["3m liquidity (3+ touches) + sweep/reclaim"] = False
            reasons.append("No swing liquidity cluster with at least 3 touches")
        fvg = _fvg(d3, side)
        checks["3m FVG"] = fvg is not None
        if fvg is None: reasons.append("No fresh 3m FVG on latest closed candle")
        if all(checks.values()) and liq and fvg:
            entry = fvg[2]
            # Stop beyond the sweep candle extreme; 2R target.
            sweep_candle = d3.iloc[-1]
            stop = float(sweep_candle.low) if side == "long" else float(sweep_candle.high)
            risk = abs(entry-stop)
            if risk > 0:
                target = entry + 2*risk if side == "long" else entry - 2*risk
                results.append({"symbol":symbol,"side":side,"entry":entry,"stop":stop,"target":target,
                                "touches":liq[0],"liquidity_level":liq[1],"fvg_low":fvg[0],"fvg_high":fvg[1],
                                "checks":checks,"signal_time":d3.time_utc.iloc[-1].isoformat(),
                                "note":"Research candidate only; confirm FVG retracement before any trade."})
        else:
            results.append({"symbol":symbol,"side":side,"candidate":False,"checks":checks,"reasons":reasons,
                            "trend":trend,"ema200":float(ema200),"last_price":float(d3.close.iloc[-1])})
    return results

def scan_symbol(symbol: str):
    data = {tf: fetch_candles(symbol, tf, 500 if tf == "15m" else 700) for tf in ("15m","5m","3m")}
    return data, analyze(symbol, data["15m"], data["5m"], data["3m"])
