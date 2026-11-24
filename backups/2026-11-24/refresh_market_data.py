import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "data" / "symbols.json"
OUTPUT_PATH = ROOT / "data" / "market.json"
TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
BASE_URL = "https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/PriceHistory.ashx"
PAGE_SIZE = 30
MAX_PAGES = 60

# Fallback only. Preferred exchange mapping lives in data/symbols.json
# so newly added watchlist symbols retain the exchange selected in the app.
EXCHANGE_BY_SYMBOL = {
    "BVB": "UPCOM",
    "MST": "HNX",
}


def load_config():
    # Private Cloudflare Worker is the live source of the user's watchlist.
    # data/symbols.json is retained as a bootstrap reference, not the active list.
    worker_url = "https://vietstock-portfolio-syncolio-sync.pttamdng.workers.dev/"
    request = Request(worker_url, headers={"User-Agent": "VietStock-Lab-CafeF-Refresh"})
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    watchlist = payload.get("watchlist") or {}
    stocks = watchlist.get("stocks")
    exchanges = watchlist.get("exchanges")
    if not isinstance(stocks, list) or not isinstance(exchanges, dict):
        raise RuntimeError("Cloudflare Worker chưa trả về watchlist hợp lệ; dừng để tránh tải sai danh sách.")
    clean = []
    for symbol in stocks:
        symbol = str(symbol).strip().upper()
        if not symbol or symbol in clean:
            raise RuntimeError(f"Watchlist có mã rỗng hoặc trùng: {symbol!r}")
        clean.append(symbol)
    print(f"Loaded private watchlist from GitHub: {', '.join(clean) if clean else '(empty)'}")
    return {"stocks": clean, "exchanges": exchanges, "indices": ["VNINDEX", "HNXINDEX", "UPCOMINDEX"]}


def as_float(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace(" ", "")
    try:
        return float(text)
    except ValueError:
        return None


def parse_date(value):
    value = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def request_page(symbol, exchange, start_date, end_date, page):
    params = urlencode({
        "ExchangeType": exchange,
        "Symbol": symbol,
        "StartDate": start_date.strftime("%m/%d/%Y"),
        "EndDate": end_date.strftime("%m/%d/%Y"),
        "PageIndex": str(page),
        "PageSize": str(PAGE_SIZE),
    })
    request = Request(
        f"{BASE_URL}?{params}",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
            ),
            "Referer": (
                f"https://cafef.vn/du-lieu/lich-su-giao-dich/"
                f"{exchange.lower()}/{symbol.lower()}-1.chn"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
        },
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8-sig"))

    if not payload.get("Success", True):
        raise RuntimeError(
            f"CafeF trả Success=false: {payload.get('Message', 'không có thông báo')}"
        )

    data = payload.get("Data") or {}
    rows = data.get("Data") or []
    total_count = data.get("TotalCount")
    try:
        total_count = int(total_count) if total_count is not None else None
    except (TypeError, ValueError):
        total_count = None
    return rows, total_count


def fetch_history(symbol, exchange, start_date, end_date):
    all_rows = []
    seen_dates = set()
    total_count = None

    for page in range(1, MAX_PAGES + 1):
        rows, reported_total = request_page(
            symbol, exchange, start_date, end_date, page
        )
        if reported_total is not None:
            total_count = reported_total
        if not rows:
            break

        for item in rows:
            trading_date = parse_date(item.get("Ngay"))
            if not trading_date or not (start_date <= trading_date <= end_date):
                continue
            date_key = trading_date.isoformat()
            if date_key in seen_dates:
                continue
            seen_dates.add(date_key)

            # Keep raw OHLC for candle/VSA analysis. CafeF's GiaDieuChinh is
            # retained separately and is not substituted for the traded close.
            row = {
                "date": date_key,
                "open": as_float(item.get("GiaMoCua")),
                "high": as_float(item.get("GiaCaoNhat")),
                "low": as_float(item.get("GiaThapNhat")),
                "close": as_float(item.get("GiaDongCua")),
                "adjusted_close": as_float(item.get("GiaDieuChinh")),
                "volume": as_float(item.get("KhoiLuongKhopLenh")),
                "value": as_float(item.get("GiaTriKhopLenh")),
                "negotiated_volume": as_float(item.get("KLThoaThuan")),
                "negotiated_value": as_float(item.get("GtThoaThuan")),
            }
            # Skip records that cannot be used as OHLC candles.
            if all(row[key] is not None for key in ("open", "high", "low", "close", "volume")):
                all_rows.append(row)

        print(
            f"{symbol}: page {page}, received={len(rows)}, "
            f"valid_total={len(all_rows)}"
        )

        if total_count is not None and page * PAGE_SIZE >= total_count:
            break
        if len(rows) < PAGE_SIZE:
            break
        time.sleep(0.35)

    all_rows.sort(key=lambda row: row["date"])
    if not all_rows:
        raise RuntimeError(f"CafeF không trả về nến OHLCV hợp lệ cho {symbol}")
    return all_rows


def main():
    config = load_config()
    end_date = date.today()
    start_date = date(2024, 1, 1)
    stocks = {}
    indices = {}
    errors = []

    symbols = config.get("stocks", [])
    configured_exchanges = {
        str(symbol).strip().upper(): str(exchange).strip().upper()
        for symbol, exchange in (config.get("exchanges") or {}).items()
    }
    valid_exchanges = {"HOSE", "HNX", "UPCOM"}
    for symbol in symbols:
        symbol = str(symbol).strip().upper()
        if not symbol:
            continue
        exchange = configured_exchanges.get(
            symbol, EXCHANGE_BY_SYMBOL.get(symbol, "HOSE")
        )
        if exchange not in valid_exchanges:
            errors.append(f"{symbol}: sàn không hợp lệ '{exchange}', bỏ qua mã.")
            print(f"SOURCE ERROR: {symbol}: invalid exchange '{exchange}'")
            continue
        try:
            print(f"Fetching {symbol} from CafeF ({exchange}), {start_date} to {end_date}")
            # CafeF may cap wide date queries to roughly one year.
            # Split into <=365-day windows and merge by actual trading date.
            rows_by_date = {}
            window_start = start_date
            while window_start <= end_date:
                window_end = min(window_start + timedelta(days=364), end_date)
                print(f"{symbol}: requesting window {window_start} to {window_end}")
                window_rows = fetch_history(symbol, exchange, window_start, window_end)
                for row in window_rows:
                    rows_by_date[row["date"]] = row
                window_start = window_end + timedelta(days=1)
                time.sleep(0.25)
            rows = [rows_by_date[key] for key in sorted(rows_by_date)]
            stocks[symbol] = rows
            print(f"SUCCESS {symbol}: {len(rows)} sessions, first={rows[0]['date']}, last={rows[-1]['date']}")
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError) as error:
            message = f"{symbol}: {type(error).__name__}: {error}"
            errors.append(message)
            print(f"SOURCE ERROR: {message}")
        time.sleep(0.4)

    # Try index symbols through the same endpoint. Some CafeF deployments may
    # not expose index candles here; failures are logged without losing stocks.
    for symbol in config.get("indices", []):
        symbol = str(symbol).strip().upper()
        if not symbol:
            continue
        try:
            print(f"Fetching index {symbol} from CafeF")
            rows_by_date = {}
            window_start = start_date
            while window_start <= end_date:
                window_end = min(window_start + timedelta(days=364), end_date)
                print(f"{symbol}: requesting window {window_start} to {window_end}")
                for row in fetch_history(symbol, "HOSE", window_start, window_end):
                    rows_by_date[row["date"]] = row
                window_start = window_end + timedelta(days=1)
                time.sleep(0.25)
            rows = [rows_by_date[key] for key in sorted(rows_by_date)]
            indices[symbol] = rows
            print(f"SUCCESS index {symbol}: {len(rows)} sessions, first={rows[0]['date']}, last={rows[-1]['date']}")
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError) as error:
            message = f"Index {symbol}: {type(error).__name__}: {error}"
            errors.append(message)
            print(f"SOURCE ERROR: {message}")
        time.sleep(0.4)

    # Preserve the last known-good snapshot if every symbol failed.
    if not stocks and not indices:
        print("ERROR: CafeF returned no usable history for any configured symbol.")
        for message in errors:
            print(message)
        sys.exit(1)

    payload = {
        "updated_at": datetime.now(TIMEZONE).isoformat(),
        "source": "CafeF PriceHistory API",
        "timezone": "Asia/Ho_Chi_Minh",
        "lookback_days": (end_date - start_date).days,
        "lookback_mode": "2024-calendar-start",
        "lookback_start": start_date.isoformat(),
        "lookback_end": end_date.isoformat(),
        "stocks": stocks,
        "indices": indices,
        "errors": errors,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = OUTPUT_PATH.with_suffix(".json.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    temp_path.replace(OUTPUT_PATH)

    print(
        f"Completed: {len(stocks)} stocks, {len(indices)} indices, "
        f"{len(errors)} source errors."
    )
    print(f"Saved CafeF snapshot to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
