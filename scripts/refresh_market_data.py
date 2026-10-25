"""Refresh public daily OHLCV snapshots for VietStock Lab.

Uses the community Vnstock library and its VCI/KBS sources. Third-party data
can be delayed, adjusted, rate-limited, or unavailable; this script records
errors per symbol rather than fabricating values.
"""
from __future__ import annotations
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "data" / "symbols.json").read_text(encoding="utf-8"))
OUT = ROOT / "data" / "market.json"
TZ = ZoneInfo("Asia/Ho_Chi_Minh")

def norm_rows(df):
    if df is None or getattr(df, "empty", True):
        return []
    cols = {str(c).lower(): c for c in df.columns}
    time_col = next((cols[k] for k in ("time", "date", "tradingdate", "trading_date") if k in cols), None)
    if time_col is None:
        # Some dataframes return the timestamp as their index.
        df = df.reset_index()
        cols = {str(c).lower(): c for c in df.columns}
        time_col = next((cols[k] for k in ("time", "date", "tradingdate", "trading_date", "index") if k in cols), None)
    if time_col is None:
        raise ValueError(f"Cannot find date column; received columns {list(df.columns)}")
    def col(*names):
        for name in names:
            if name in cols: return cols[name]
        raise ValueError(f"Missing columns {names}; received {list(df.columns)}")
    oc = col("open")
    hc = col("high")
    lc = col("low")
    cc = col("close")
    vc = col("volume", "vol")
    rows=[]
    for _, r in df.iterrows():
        try:
            dt = r[time_col]
            if hasattr(dt, "to_pydatetime"): dt = dt.to_pydatetime()
            date = str(dt)[:10]
            o,h,l,c,v = (float(r[k]) for k in (oc,hc,lc,cc,vc))
            if not date[:4].isdigit() or not all(map(lambda n: n == n and abs(n) != float("inf"), (o,h,l,c,v))): continue
            rows.append({"date":date,"open":o,"high":h,"low":l,"close":c,"volume":int(v),"source":"Vnstock / VCI-KBS"})
        except (TypeError, ValueError, KeyError):
            continue
    dedup={x["date"]:x for x in rows}
    return sorted(dedup.values(), key=lambda x:x["date"])[-260:]

def main():
    from vnstock import Market
    market = Market()
    stocks={}; indices={}; errors=[]
    for symbol in CONFIG.get("stocks", []):
        try:
            df = market.equity(symbol).ohlcv(length=CONFIG.get("lookback", "1Y"), source="vci")
            rows = norm_rows(df)
            if rows: stocks[symbol] = rows
            else: errors.append(f"{symbol}: nguồn trả về dữ liệu rỗng")
        except Exception as exc:
            errors.append(f"{symbol}: {type(exc).__name__}: {str(exc)[:180]}")
        time.sleep(0.6)
    for symbol in CONFIG.get("indices", []):
        try:
            df = market.index(symbol).ohlcv(length=CONFIG.get("lookback", "1Y"), source="kbs")
            rows = norm_rows(df)
            if rows: indices[symbol] = rows
            else: errors.append(f"{symbol}: nguồn trả về dữ liệu rỗng")
        except Exception as exc:
            errors.append(f"{symbol}: {type(exc).__name__}: {str(exc)[:180]}")
        time.sleep(0.6)
    payload={"updated_at":datetime.now(TZ).isoformat(timespec="seconds"),"source":"Vnstock community library (VCI for stocks; KBS for indices)","timezone":"Asia/Ho_Chi_Minh","stocks":stocks,"indices":indices,"errors":errors}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))+"\n", encoding="utf-8")
    print(f"Updated {len(stocks)} stocks and {len(indices)} indices; {len(errors)} source errors.")
    if not stocks and not indices:
        raise SystemExit("No data returned from any source; keeping diagnostics in market.json but failing the workflow.")

if __name__ == "__main__": main()
