import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def read_json_with_retry(request, symbol, page):
    for attempt in range(1, 4):
        try:
            with urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8-sig"))
        except HTTPError as error:
            if error.code not in (408, 429, 500, 502, 503, 504) or attempt == 3:
                raise
            delay = 2 * attempt
            print(f"{symbol}: HTTP {error.code} page {page}; retry {attempt}/2 after {delay}s")
            time.sleep(delay)
        except (TimeoutError, URLError, OSError) as error:
            if attempt == 3:
                raise
            delay = 2 * attempt
            print(f"{symbol}: {type(error).__name__} page {page}; retry {attempt}/2 after {delay}s")
            time.sleep(delay)
    raise RuntimeError(f"CafeF returned no response for {symbol} page {page}")

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
    payload = read_json_with_retry(request, symbol, page)

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
        try:
            rows, reported_total = request_page(
                symbol, exchange, start_date, end_date, page
            )
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError) as error:
            if all_rows:
                print(
                    f"{symbol}: page {page} failed after {len(all_rows)} valid rows "
                    f"({type(error).__name__}: {error}); returning partial window"
                )
                break
            raise
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
        time.sleep(0.5)

    all_rows.sort(key=lambda row: row["date"])
    if not all_rows:
        raise RuntimeError(f"CafeF không trả về nến OHLCV hợp lệ cho {symbol}")
    return all_rows



def fetch_index_history(symbol, lookback_days, min_rows=1):
    """Fetch index candles from the free DNSE/Vietcap fallback chain."""
    from vn_market_data import get_ohlcv

    rows = get_ohlcv(
        symbol,
        lookback_days=lookback_days,
        is_index=True,
        ttl_s=0,
    )
    clean = []
    for item in rows or []:
        day = str(item.get("date") or "")
        if not day:
            continue
        row = {
            "date": day,
            "open": as_float(item.get("open")),
            "high": as_float(item.get("high")),
            "low": as_float(item.get("low")),
            "close": as_float(item.get("close")),
            "volume": as_float(item.get("volume")),
        }
        if all(row[key] is not None for key in ("open", "high", "low", "close", "volume")):
            clean.append(row)
    clean.sort(key=lambda row: row["date"])
    if len(clean) < min_rows:
        raise RuntimeError(
            f"Provider trả về quá ít nến chỉ số ({len(clean)}; cần tối thiểu {min_rows})."
        )
    return clean


def load_previous_snapshot():
    """Load the last known-good snapshot; keep history across incremental refreshes."""
    try:
        with OUTPUT_PATH.open("r", encoding="utf-8") as file:
            previous = json.load(file)
        return previous if isinstance(previous, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def merge_rows(previous_rows, fresh_rows):
    """Merge OHLCV by trading date; fresh rows replace overlapping dates."""
    merged = {}
    for row in previous_rows or []:
        if isinstance(row, dict) and row.get("date"):
            merged[str(row["date"])] = row
    for row in fresh_rows or []:
        if isinstance(row, dict) and row.get("date"):
            merged[str(row["date"])] = row
    return [merged[key] for key in sorted(merged)]


def incremental_start(previous_rows, full_start, overlap_days=10):
    """Start shortly before the last stored session to repair gaps/revisions."""
    dates = [
        parse_date(row.get("date"))
        for row in (previous_rows or [])
        if isinstance(row, dict)
    ]
    dates = [day for day in dates if day]
    if not dates:
        return full_start
    return max(full_start, max(dates) - timedelta(days=overlap_days))


def main():
    run_started = time.perf_counter()
    config = load_config()
    end_date = date.today()
    start_date = date(2024, 1, 1)
    previous = load_previous_snapshot()
    previous_stocks = previous.get("stocks") if isinstance(previous.get("stocks"), dict) else {}
    previous_indices = previous.get("indices") if isinstance(previous.get("indices"), dict) else {}
    stocks = dict(previous_stocks)
    indices = dict(previous_indices)
    errors = []
    refreshed_stocks = set()

    symbols = [str(item).strip().upper() for item in config.get("stocks", []) if str(item).strip()]
    if not symbols:
        raise RuntimeError("Watchlist từ Cloudflare Worker đang rỗng; dừng để không chạy cập nhật chỉ số giả như đã tải cổ phiếu.")

    configured_exchanges = {
        str(symbol).strip().upper(): str(exchange).strip().upper()
        for symbol, exchange in (config.get("exchanges") or {}).items()
    }
    valid_exchanges = {"HOSE", "HNX", "UPCOM"}

    def refresh_one_stock(symbol):
        symbol_started = time.perf_counter()
        exchange = configured_exchanges.get(
            symbol, EXCHANGE_BY_SYMBOL.get(symbol, "HOSE")
        )
        old_rows = previous_stocks.get(symbol) or []
        if exchange not in valid_exchanges:
            return symbol, None, 0, f"Invalid exchange '{exchange}'", time.perf_counter() - symbol_started
        fetch_start = incremental_start(old_rows, start_date)
        mode = "incremental" if old_rows else "full backfill"
        try:
            print(f"Fetching {symbol} from CafeF ({exchange}), {fetch_start} to {end_date} [{mode}]")
            rows_by_date = {}
            # Build <=365-day windows, then fetch newest first. A slow old
            # historical window must never prevent today's candles from landing.
            windows = []
            window_start = fetch_start
            while window_start <= end_date:
                window_end = min(window_start + timedelta(days=364), end_date)
                windows.append((window_start, window_end))
                window_start = window_end + timedelta(days=1)

            for window_start, window_end in reversed(windows):
                print(f"{symbol}: requesting window {window_start} to {window_end}")
                try:
                    window_rows = fetch_history(symbol, exchange, window_start, window_end)
                    for row in window_rows:
                        rows_by_date[row["date"]] = row
                except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError) as window_error:
                    print(
                        f"{symbol}: skip failed historical window {window_start}..{window_end}: "
                        f"{type(window_error).__name__}: {window_error}"
                    )
                time.sleep(0.15)
            fresh_rows = [rows_by_date[key] for key in sorted(rows_by_date)]
            merged_rows = merge_rows(old_rows, fresh_rows)
            if not merged_rows:
                raise RuntimeError(f"Không có dữ liệu cũ hoặc mới cho {symbol}")
            print(
                f"SUCCESS {symbol}: +{len(fresh_rows)} fetched, {len(merged_rows)} total; "
                f"elapsed={time.perf_counter()-symbol_started:.1f}s"
            )
            return symbol, merged_rows, len(fresh_rows), None, time.perf_counter() - symbol_started
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError) as error:
            return symbol, None, 0, f"{type(error).__name__}: {error}", time.perf_counter() - symbol_started

    # CafeF calls are independent. Bounded concurrency prevents a slow/timeout
    # ticker from making all other symbols wait in series.
    worker_count = min(2, len(symbols))
    print(f"Refreshing {len(symbols)} stocks with bounded concurrency={worker_count}")
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {pool.submit(refresh_one_stock, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                result_symbol, rows, fetched_count, error, elapsed = future.result()
            except Exception as error:
                result_symbol, rows, fetched_count, elapsed = symbol, None, 0, 0.0
                error = f"{type(error).__name__}: {error}"
            if error:
                message = f"{result_symbol}: {error}"
                errors.append(message)
                print(f"SOURCE ERROR: {message}; elapsed={elapsed:.1f}s")
                if previous_stocks.get(result_symbol):
                    stocks[result_symbol] = previous_stocks[result_symbol]
                    print(f"KEEP previous snapshot {result_symbol}: {len(previous_stocks[result_symbol])} rows")
            elif rows:
                stocks[result_symbol] = rows
                refreshed_stocks.add(result_symbol)

    if not refreshed_stocks:
        print("ERROR: no configured stock was refreshed successfully; refusing to mark this run as successful.")
        for message in errors:
            print(message)
        sys.exit(1)

    # Fetch indices from the free GitHub library. It uses DNSE first and
    # Vietcap as fallback, with normalized daily OHLCV and index units unscaled.
    # Keep the previous series per index if every provider fails or returns thin data.
    index_sources = dict(previous.get("index_sources") or {})
    for symbol in config.get("indices", []):
        symbol = str(symbol).strip().upper()
        if not symbol:
            continue
        old_rows = previous_indices.get(symbol) or []
        fetch_start = incremental_start(old_rows, start_date)
        lookback_days = max(14, (end_date - fetch_start).days + 1)
        index_started = time.perf_counter()
        try:
            print(
                f"Fetching index {symbol} via vn-market-data, lookback={lookback_days} days "
                f"[{'incremental' if old_rows else 'full backfill'}]"
            )
            fresh_rows = fetch_index_history(symbol, lookback_days, min_rows=1)
            fresh_rows = [
                row for row in fresh_rows
                if fetch_start.isoformat() <= row["date"] <= end_date.isoformat()
            ]
            if not fresh_rows:
                raise RuntimeError("Provider không trả nến mới trong cửa sổ cập nhật.")
            merged_rows = merge_rows(old_rows, fresh_rows)
            indices[symbol] = merged_rows
            index_sources[symbol] = "vn-market-data (DNSE/Vietcap fallback)"
            print(
                f"SUCCESS index {symbol}: +{len(fresh_rows)} fetched, {len(merged_rows)} total; "
                f"first={merged_rows[0]['date']}, last={merged_rows[-1]['date']}; "
                f"elapsed={time.perf_counter()-index_started:.1f}s"
            )
        except Exception as error:
            message = f"Index {symbol}: {type(error).__name__}: {error}"
            errors.append(message)
            print(f"SOURCE ERROR: {message}")
            if old_rows:
                indices[symbol] = old_rows
                index_sources[symbol] = "previous-known-good snapshot (provider failed)"
                print(f"KEEP previous index snapshot {symbol}: {len(old_rows)} rows")
        time.sleep(0.1)

    # Never replace a populated snapshot with an empty result.
    if not stocks and not indices:
        print("ERROR: no usable current or previous market data; refusing to overwrite snapshot.")
        for message in errors:
            print(message)
        sys.exit(1)

    payload = {
        "updated_at": datetime.now(TIMEZONE).isoformat(),
        "source": "CafeF (stocks) + vn-market-data (indices)",
        "index_sources": index_sources,
        "timezone": "Asia/Ho_Chi_Minh",
        "lookback_days": (end_date - start_date).days,
        "lookback_mode": "full-history-plus-incremental-overlap",
        "refresh_mode": "incremental",
        "refreshed_stocks": sorted(refreshed_stocks),
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
        f"Completed: {len(refreshed_stocks)} stocks refreshed / {len(stocks)} retained, "
        f"{len(indices)} indices, {len(errors)} source errors; "
        f"total elapsed={time.perf_counter()-run_started:.1f}s"
    )
    print(f"Saved CafeF snapshot to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
