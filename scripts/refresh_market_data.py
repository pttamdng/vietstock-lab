import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "data" / "symbols.json"
OUTPUT_PATH = ROOT / "data" / "market.json"

TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def normalize_rows(df):
    """Chuẩn hóa dữ liệu OHLCV thành danh sách dictionary."""
    if df is None or df.empty:
        return []

    df = df.copy()
    df.columns = [str(column).lower().strip() for column in df.columns]

    # Vnstock thường trả cột thời gian tên là time.
    date_column = next(
        (
            column
            for column in ("time", "date", "trading_date")
            if column in df.columns
        ),
        None,
    )

    if date_column is None:
        raise ValueError(
            f"Không tìm thấy cột ngày giao dịch. "
            f"Các cột nhận được: {list(df.columns)}"
        )

    rows = []

    for _, row in df.iterrows():
        date_value = row[date_column]

        if hasattr(date_value, "strftime"):
            date_value = date_value.strftime("%Y-%m-%d")
        else:
            date_value = str(date_value)[:10]

        item = {"date": date_value}

        for column in ("open", "high", "low", "close", "volume"):
            value = row[column] if column in df.columns else None

            try:
                if value is None or value != value:
                    item[column] = None
                else:
                    item[column] = float(value)
            except (TypeError, ValueError):
                item[column] = None

        rows.append(item)

    return rows


def fetch_one(market, symbol, kind, length, errors):
    """Thử lần lượt VCI và KBS, trả về dữ liệu đầu tiên lấy được."""
    for source in ("vci", "kbs"):
        try:
            print(f"Fetching {kind} {symbol} from {source}...")

            if kind == "stock":
                asset = market.equity(symbol)
            else:
                asset = market.index(symbol)

            df = asset.ohlcv(
                length=length,
                interval="1D",
                source=source,
            )

            rows = normalize_rows(df)

            if rows:
                print(
                    f"SUCCESS: {symbol}, "
                    f"source={source}, rows={len(rows)}"
                )
                return rows

            message = (
                f"{kind} {symbol} ({source}): "
                "Nguồn không trả về dữ liệu."
            )
            print(f"SOURCE ERROR: {message}")
            errors.append(message)

        except Exception as error:
            message = (
                f"{kind} {symbol} ({source}): "
                f"{type(error).__name__}: {error}"
            )
            print(f"SOURCE ERROR: {message}")
            errors.append(message)

        time.sleep(0.5)

    return []


def main():
    import vnstock
    from vnstock import Market

    api_key = os.environ.get("VNSTOCK_API_KEY")

    if not api_key:
        raise RuntimeError(
            "Thiếu VNSTOCK_API_KEY. Hãy kiểm tra GitHub Secrets."
        )

    # Đăng nhập bằng API key được lưu trong GitHub Secrets.
    vnstock.login(api_key)

    config = load_config()
    length = config.get("lookback", "1Y")
    errors = []

    market = Market()

    stocks = {}
    indices = {}

    for symbol in config.get("stocks", []):
        rows = fetch_one(
            market, symbol, "stock", length, errors
        )
        if rows:
            stocks[symbol] = rows

    for symbol in config.get("indices", []):
        rows = fetch_one(
            market, symbol, "index", length, errors
        )
        if rows:
            indices[symbol] = rows

    # Không ghi đè file cũ nếu tất cả mã đều thất bại.
    if not stocks and not indices:
        print("ERROR: Không lấy được dữ liệu của bất kỳ mã nào.")
        for message in errors:
            print(message)
        sys.exit(1)

    payload = {
        "updated_at": datetime.now(TIMEZONE).isoformat(),
        "source": "Vnstock / VCI-KBS",
        "timezone": "Asia/Ho_Chi_Minh",
        "stocks": stocks,
        "indices": indices,
        "errors": errors,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"Completed: {len(stocks)} stocks, "
        f"{len(indices)} indices, "
        f"{len(errors)} source errors."
    )
    print(f"Saved data to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
                
