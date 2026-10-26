
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
    """Chuyển dữ liệu OHLCV thành danh sách dictionary dùng được trong JSON."""
    if df is None or df.empty:
        return []

    df = df.copy()
    df.columns = [str(column).lower().strip() for column in df.columns]

    # Chuẩn hóa tên cột ngày giao dịch
    date_column = None
    for candidate in ("time", "date", "trading_date"):
        if candidate in df.columns:
            date_column = candidate
            break

    if date_column is None:
        return []

    result = []

    for _, row in df.iterrows():
        try:
            date_value = row[date_column]

            if hasattr(date_value, "strftime"):
                date_value = date_value.strftime("%Y-%m-%d")
            else:
                date_value = str(date_value)[:10]

            item = {"date": date_value}

            for column in ("open", "high", "low", "close", "volume"):
                if column not in df.columns:
                    item[column] = None
                    continue

                value = row[column]

                if value is None:
                    item[column] = None
                else:
                    try:
                        if value != value:
                            item[column] = None
                        else:
                            item[column] = float(value)
                    except (TypeError, ValueError):
                        item[column] = None

            result.append(item)

        except Exception as error:
            print(f"WARNING: Không chuẩn hóa được một dòng: {error}")

    return result


def fetch_one(market, symbol, kind, length, errors):
    """Thử lần lượt VCI và KBS; trả về dữ liệu đầu tiên lấy được."""
    for source in ("vci", "kbs"):
        try:
            print(f"Fetching {kind} {symbol} from {source}...")

            if kind == "stock":
                df = market.equity(symbol).ohlcv(
                    start="",
                    end="",
                    resolution="1D",
                    count_back=365 if length == "1Y" else 100,
                    source=source,
                )
            else:
                df = market.index(symbol).ohlcv(
                    start="",
                    end="",
                    resolution="1D",
                    count_back=365 if length == "1Y" else 100,
                    source=source,
                )

            rows = normalize_rows(df)

            if rows:
                print(f"SUCCESS: {symbol}, source={source}, rows={len(rows)}")
                return rows

            errors.append(
                f"{kind} {symbol} ({source}): Không có dữ liệu OHLCV."
            )

        except Exception as error:
            message = f"{kind} {symbol} ({source}): {type(error).__name__}: {error}"
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
            "Thiếu VNSTOCK_API_KEY. Hãy kiểm tra GitHub Settings > Secrets and variables > Actions."
        )

    # Xác thực API key trước khi gọi nguồn dữ liệu
    vnstock.login(api_key)

    config = load_config()
    length = config.get("lookback", "1Y")
    errors = []

    market = Market()

    stocks = {}
    indices = {}

    for symbol in config.get("stocks", []):
        rows = fetch_one(market, symbol, "stock", length, errors)
        if rows:
            stocks[symbol] = rows

    for symbol in config.get("indices", []):
        rows = fetch_one(market, symbol, "index", length, errors)
        if rows:
            indices[symbol] = rows

    # Không ghi đè dữ liệu cũ nếu tất cả nguồn đều thất bại
    if not stocks and not indices:
        print("ERROR: Không lấy được dữ liệu của bất kỳ mã nào.")
        for error in errors:
            print(error)
        sys.exit(1)

    payload = {
        "updated_at": datetime.now(TIMEZONE).isoformat(),
        "source": "Vnstock community / VCI-KBS",
        "timezone": "Asia/Ho_Chi_Minh",
        "stocks": stocks,
        "indices": indices,
        "errors": errors,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    print(
        f"Completed: {len(stocks)} stocks, "
        f"{len(indices)} indices, {len(errors)} source errors."
    )
    print(f"Saved data to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
