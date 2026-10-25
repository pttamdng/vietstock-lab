# VietStock Lab PWA — MVP 0.3 (auto EOD data)

## Chức năng hiện có
- Tải snapshot OHLCV cuối ngày từ `data/market.json`; tính toán lại MA10/MA50, RSI(14), Bollinger và tỷ lệ khối lượng.
- Bảng VN-Index/HNX-Index/UPCoM-Index khi nguồn trả dữ liệu.
- GitHub Actions cập nhật theo lịch ngày làm việc sau phiên (khoảng 17:15 giờ Việt Nam), có thể chạy thủ công trong tab Actions.
- Giao diện responsive ưu tiên điện thoại, 5 màn hình: tổng quan, phân tích, danh mục, dữ liệu, cài đặt.
- Theo dõi nhiều mã HOSE/HNX/UPCOM.
- Nhập OHLCV thủ công, import CSV, export/backup JSON.
- Tính MA10/MA50, RSI(14), Bollinger Bands và tỷ lệ khối lượng so với trung bình 20 phiên.
- Bộ quy tắc VSA/Wyckoff sơ bộ, cảnh báo giá, tính khối lượng theo ngân sách/rủi ro.
- Lưu cục bộ bằng localStorage; không gửi dữ liệu cá nhân tới máy chủ.
- Manifest và service worker cho PWA khi triển khai qua HTTPS.

## Bật cập nhật tự động lần đầu
1. Đẩy các tệp trong gói này lên repository, giữ nguyên cấu trúc thư mục, đặc biệt `.github/workflows/refresh-market-data.yml`, `scripts/refresh_market_data.py`, `data/symbols.json` và `data/market.json`.
2. Vào **Settings → Actions → General → Workflow permissions** và chọn **Read and write permissions**, lưu lại.
3. Mở tab **Actions**, chọn **Refresh Vietnam market data**, bấm **Run workflow**. Chờ workflow kết thúc rồi tải lại trang Pages.
4. Lịch chạy tự động là các ngày thứ Hai–thứ Sáu, sau phiên; GitHub có thể chạy trễ. Nếu workflow lỗi, xem log từng mã trong Actions.
5. Muốn bổ sung mã cổ phiếu vào nguồn tự động, sửa `data/symbols.json` rồi commit thay đổi. Việc thêm mã trong giao diện app hiện chỉ thêm vào danh sách cục bộ; chưa tự sửa file cấu hình trên GitHub.

Nguồn dự kiến là thư viện cộng đồng Vnstock, gọi VCI cho cổ phiếu và KBS cho chỉ số. Đây không phải API chính thức do CafeF/Vietstock/FireAnt cung cấp; nguồn có thể đổi cấu trúc, giới hạn truy cập, chậm hoặc ngừng hoạt động. Không cam kết dữ liệu realtime hay tính liên tục. Kiểm tra timestamp trong app và đối chiếu nguồn môi giới trước khi giao dịch.

## Quan trọng về dữ liệu
DHC khởi tạo bằng đúng 3 phiên do người dùng cung cấp (09/10, 12/10, 13/10/2026), không tự điền các phiên thiếu. Chuỗi này chưa đủ tính MA10/MA50/RSI(14). Số liệu DHC chụp lúc 14:48 ngày 23/10 chưa được xem là giá/khối lượng chốt phiên và không được nạp vào như nến hoàn tất. Nhập thêm lịch sử CSV đã xác minh trước khi dùng các chỉ báo hoặc tín hiệu để ra quyết định.

SSI FastConnect là ứng viên đầu tiên để tích hợp: tài liệu chính thức mô tả REST API, OHLCV lịch sử và WebSocket streaming cho dữ liệu thị trường. Cần đăng ký/được cấp API key, xác nhận gói dữ liệu, quyền sử dụng/phân phối lại và phí. Không đưa API secret vào frontend. Tích hợp sản xuất cần backend proxy có HTTPS, quản lý secrets và giới hạn truy cập.

FireAnt có cổng API công khai nhưng cần kiểm tra endpoint dữ liệu giá cụ thể, quyền truy cập và điều khoản trước khi tích hợp. Không scrape trái điều khoản.

## Chạy thử trên máy tính
- Mở `index.html` trực tiếp để thử các chức năng chính; Service Worker/PWA sẽ không hoạt động trong chế độ file.
- Để thử PWA, chạy trong thư mục này qua một web server HTTPS (hoặc localhost). Ví dụ: `python -m http.server 8080`, sau đó mở `http://localhost:8080` trên máy tính. Để cài trên điện thoại, triển khai lên hosting HTTPS rồi mở URL bằng Chrome Android.

## CSV format
`symbol,date,open,high,low,close,volume`
Ngày theo `YYYY-MM-DD`. Giá nhập theo nghìn đồng/cổ phiếu (ví dụ 36.8 = 36.800 đồng), khối lượng theo cổ phiếu. Giá trị danh mục và lãi/lỗ hiển thị bằng đồng. Có thể tải CSV mẫu ngay trong app.

## Giới hạn MVP
- Chưa có backend, tài khoản đăng nhập hoặc đồng bộ nhiều thiết bị. Snapshot tự động là dữ liệu cuối ngày được commit vào repository; GitHub Pages không chạy backend. Mã mới thêm trong giao diện chưa tự động được đưa vào danh sách lấy dữ liệu.
- Cảnh báo hiện được đánh giá khi mở app/tính lại, chưa có push notification nền.
- VSA/Wyckoff dùng heuristic minh bạch; chưa có nhận diện cấu trúc pha Wyckoff tự động. Cần ít nhất nhiều tuần dữ liệu đã xác minh để chỉ báo và so sánh khối lượng đáng tin hơn.
- Không kết nối giao dịch, không đặt lệnh.
