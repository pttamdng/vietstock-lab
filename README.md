# VietStock Lab PWA — CafeF direct history

## Chức năng
- GitHub Actions gọi trực tiếp endpoint lịch sử giao dịch JSON của CafeF, không phụ thuộc Excel/Power Query trên máy người dùng.
- Mỗi lần cập nhật lấy khoảng 365 ngày gần nhất và tự động phân trang cho từng mã trong `data/symbols.json`.
- Lưu snapshot vào `data/market.json`; GitHub Pages đọc snapshot này để tính MA10/MA50, RSI(14), Bollinger và tỷ lệ khối lượng.
- Giao diện responsive, watchlist, danh mục, nhập OHLCV thủ công, import CSV, export/backup JSON, cảnh báo và bộ quy tắc Wyckoff/VSA sơ bộ.
- Lịch tự động chạy ngày thứ Hai–thứ Sáu khoảng 17:15 giờ Việt Nam; cũng có thể chạy thủ công trong tab Actions.

## Kiến trúc dữ liệu
1. GitHub Actions chạy `scripts/refresh_market_data.py` trên máy runner của GitHub.
2. Script gọi CafeF `PriceHistory.ashx`, lấy từng trang và chuẩn hóa dữ liệu.
3. Script commit snapshot mới vào `data/market.json`.
4. Ứng dụng GitHub Pages tải snapshot từ repository; trình duyệt không gọi trực tiếp CafeF.

Cách này tránh phụ thuộc file Power Query trên máy cá nhân và tránh giới hạn CORS của trình duyệt. Đây là cập nhật theo snapshot cuối ngày, không phải dữ liệu realtime.

## Cấu hình
- Danh sách mã: `data/symbols.json`.
- Nguồn dữ liệu: `scripts/refresh_market_data.py`.
- Lịch chạy và commit snapshot: `.github/workflows/refresh-market-data.yml`.
- Không cần `VNSTOCK_API_KEY` hoặc đăng nhập Vnstock.
- Trong **Settings → Actions → General → Workflow permissions**, cho phép **Read and write permissions** để workflow commit được `data/market.json`.
- Mã mới thêm trong giao diện app hiện chỉ nằm trong localStorage; muốn đồng bộ vào lần tải tự động phải thêm mã vào `data/symbols.json` rồi commit.

## Trường dữ liệu
Mỗi nến có:
- `date`: ngày giao dịch `YYYY-MM-DD`
- `open`, `high`, `low`, `close`: OHLC gốc từ CafeF
- `adjusted_close`: giá điều chỉnh của CafeF, lưu riêng, không thay thế `close`
- `volume`: khối lượng khớp lệnh
- `value`, `negotiated_volume`, `negotiated_value`: các trường bổ sung

Giá OHLC được giữ theo đơn vị hiển thị của CafeF (thường là nghìn đồng/cổ phiếu, ví dụ 36.8 tương ứng 36.800 đồng); khối lượng là số cổ phiếu. Giá trị giao dịch giữ theo đơn vị API CafeF trả về. Cần đối chiếu dữ liệu trước khi sử dụng trong quyết định đầu tư.

## Kiểm thử lần đầu
1. Mở **Actions → Refresh Vietnam market data (CafeF)**.
2. Chọn **Run workflow** trên nhánh cần kiểm tra.
3. Xem log từng mã. Một số mã có thể thất bại nếu CafeF thay endpoint, giới hạn truy cập, hoặc mã/sàn chưa khớp.
4. Khi ít nhất một mã có dữ liệu hợp lệ, workflow tạo `data/market.json`. Nếu tất cả mã đều lỗi, script thoát lỗi và giữ snapshot cũ.
5. Kiểm tra trường `updated_at`, `lookback_start`, `lookback_end`, số dòng mỗi mã và đối chiếu vài phiên với CafeF.

## Quan trọng
- CafeF endpoint là nguồn web có thể thay đổi hoặc giới hạn yêu cầu; script chưa được bảo đảm chạy ổn định trên GitHub Actions cho đến khi workflow được chạy thử thành công.
- Nếu một mã HNX/UPCoM không trả dữ liệu, kiểm tra cấu hình sàn trong `EXCHANGE_BY_SYMBOL` của script.
- `adjusted_close` chỉ được giữ riêng; chưa tự tính adjusted OHLC. Với phân tích Wyckoff/VSA cần dùng OHLC cùng hệ giá nhất quán và kiểm tra sự kiện doanh nghiệp.
- Nếu mọi mã lỗi, dữ liệu cũ không bị ghi đè.
- App lưu danh mục/vị thế người dùng trong localStorage của trình duyệt; dữ liệu này không được gửi lên GitHub.
- Wyckoff/VSA hiện là quy tắc sàng lọc sơ bộ, không phải khuyến nghị mua bán tự động. Không kết nối đặt lệnh.

## CSV format
`symbol,date,open,high,low,close,volume`
Ngày theo `YYYY-MM-DD`. Giá theo nghìn đồng/cổ phiếu, khối lượng theo cổ phiếu.
