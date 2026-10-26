"""Fetch daily market data for VietStock Lab."""
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CONFIG = json.loads(
    (DATA_DIR / "symbols.json").read_text(encoding="utf-8")
)
OUT = DATA_DIR / "market.json"
TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def norm_rows(df):
    if df is None or getattr(df, "empty", True):
        return []

    cols = {str(c).lower(): c for c in df.columns}
    time_col = next(
        (cols[k] for k in
         ("time", "date", "tradingdate", "trading_date")
         if k in cols), None
    )

    if time_col is None:
        df = df.reset_index()
        cols = {str(c).lower(): c for c in df.columns}
        time_col = next(
            (cols[k] for k in
             ("time", "date", "tradingdate", "trading_date", "index")
             if k in cols), None
        )

    if time_col is None:
        raise ValueError(f"No date column; columns={list(df.columns)}")

    def col(*names):
        for name in names:
            if name in cols:
                return cols[name]
        raise ValueError(f"Missing {names}; columns={list(df.columns)}")

    oc, hc, lc, cc, vc = (
        col("open"), col("high"), col("low"),
        col("close"), col("volume", "vol")
    )

    rows = []
    for _, r in df.iterrows():
        try:
            dt = r[time_col]
            if hasattr(dt, "to_pydatetime"):
                dt = dt.to_pydatetime()
            date = str(dt)[:10]
            o, h, l, c, v = (
                float(r[k]) for k in (oc, hc, lc, cc, vc)
            )
            values = (o, h, l, c, v)
            if not date[:4].isdigit() or not all(
                n == n and abs(n) != float("inf") for n in values
            ):
                continue
            rows.append({
                "date": date,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": int(v),
                "source": "Vnstock"
            })
        except (TypeError, ValueError, KeyError):
            continue

    dedup = {x["date"]: x for x in rows}
    return sorted(dedup.values(), key=lambda x: x["date"])[-260:]


def fetch_one(market, symbol, kind, length, errors):
    for source in ("vci", "kbs"):
        try:
            if kind == "stock":
                df = market.equity(symbol).ohlcv(
                    length=length, source=source
                )
            else:
                df = market.index(symbol).ohlcv(
                    length=length, source=source
                )

            rows = norm_rows(df)
            if rows:
                for row in rows:
                    row["source"] = source.upper()
                print(
                    f"OK {kind} {symbol}: {len(rows)} rows "
                    f"from {source.upper()}"
                )
                return rows

            message = "empty result"
        except Exception as exc:
            message = f"{type(exc).__name__}: {str(exc)[:250]}"

        error = f"{kind} {symbol} [{source}]: {message}"
        errors.append(error)
        print("SOURCE ERROR:", error)

        time.sleep(0.5)

    return []


def main():
    from vnstock import Market
   
    import os
    import vnstock

    api_key = os.environ.get("VNSTOCK_API_KEY")
    if not api_key:
    raise RuntimeError("Missing VNSTOCK_API_KEY GitHub secret")

    vnstock.login(api_key)
    market = Market()

    length = CONFIG.get("lookback", "1Y")
    stocks, indices, errors = {}, {}, []

    for symbol in CONFIG.get("stocks", []):
        rows = fetch_one(market, symbol, "stock", length, errors)
        if rows:
            stocks[symbol] = rows
        time.sleep(0.5)

    for symbol in CONFIG.get("indices", []):
        rows = fetch_one(market, symbol, "index", length, errors)
        if rows:
            indices[symbol] = rows
        time.sleep(0.5)

    print(
        f"Result: {len(stocks)} stocks, {len(indices)} indices, "
        f"{len(errors)} source errors."
    )

    if not stocks and not indices:
        print("No data obtained. Existing market.json will be preserved.")
        raise SystemExit(
            "All data sources failed. See SOURCE ERROR lines above."
        )

    payload = {
        "updated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "source": "Vnstock community (VCI/KBS fallback)",
        "timezone": "Asia/Ho_Chi_Minh",
        "stocks": stocks,
        "indices": indices,
        "errors": errors
    }

    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8"
    )
    print(f"Saved market data to {OUT}")


if __name__ == "__main__":
    main()
            
