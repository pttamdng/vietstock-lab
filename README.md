# VietStock Lab PWA — MVP 0.2

## Chức năng hiện có
- Giao diện responsive ưu tiên điện thoại, 5 màn hình: tổng quan, phân tích, danh mục, dữ liệu, cài đặt.
- Theo dõi nhiều mã HOSE/HNX/UPCOM.
- Nhập OHLCV thủ công, import CSV, export/backup JSON.
- Tính MA10/MA50, RSI(14), Bollinger Bands và tỷ lệ khối lượng so với trung bình 20 phiên.
- Bộ quy tắc VSA/Wyckoff sơ bộ, cảnh báo giá, tính khối lượng theo ngân sách/rủi ro.
- Lưu cục bộ bằng localStorage; không gửi dữ liệu cá nhân tới máy chủ.
- Manifest và service worker cho PWA khi triển khai qua HTTPS.

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
- Chưa có backend, tài khoản đăng nhập, đồng bộ nhiều thiết bị hoặc dữ liệu tự động.
- Cảnh báo hiện được đánh giá khi mở app/tính lại, chưa có push notification nền.
- VSA/Wyckoff dùng heuristic minh bạch; chưa có nhận diện cấu trúc pha Wyckoff tự động. Cần ít nhất nhiều tuần dữ liệu đã xác minh để chỉ báo và so sánh khối lượng đáng tin hơn.
- Không kết nối giao dịch, không đặt lệnh.
