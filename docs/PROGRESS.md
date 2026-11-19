# Tiến độ triển khai Acunetix vào Deep Review trên Docker

## Nhật ký công việc

| Mã task | Trạng thái | Ngày | Tóm tắt kết quả / Bằng chứng | Việc còn treo |
|---------|------------|------|------------------------------|---------------|
| T0.1 | Hoàn thành | 2026-11-19 | Đã kiểm tra image acunetix:24.4 (inspect, ps). Image tự chứa (all-in-one). Chốt pod giả gồm 2 container (Acunetix + Driver). | Không |
| T0.2 | Hoàn thành | 2026-11-19 | Chạy container sạch không mount volume, xác thực đăng nhập tự động qua API POST /api/v1/me/login thành công (HTTP 204), không cần giao diện. | Lưu ý cấp quyền thư mục license cho acunetix user |
| T0.3 | Hoàn thành | 2026-11-19 | Kích hoạt license tự động qua file (license_info.json, wa_data.dat) không qua UI. API /api/v1/info xác nhận activated=true, hạn đến năm 2123. | Không |
| T0.4 | Hoàn thành | 2026-11-19 | Lấy thông tin xác thực API bằng lệnh (API key & Session token). Ghi rõ đặc tả header gửi trong HTTP request. | Không |
| T0.5 | Hoàn thành | 2026-11-19 | Trích xuất toàn bộ đặc tả OpenAPI chính thức từ bản dựng Acunetix, thu thập chính xác tên trường các API quét, cấu hình và báo cáo. | Không |
| T0.6 | Hoàn thành | 2026-11-19 | Lập tài liệu đặc tả chuỗi gọi API và kiểm chứng bằng script tự động hóa chuỗi đầy đủ: Target -> Config -> Scan -> Poll -> Abort -> Delete. | Không |
| T0.7 | Hoàn thành | 2026-11-19 | Trích xuất JSON mẫu thực tế (34 lỗ hổng web, 8 lỗ hổng API, crawl statistics). Xác nhận KHÔNG CẦN chọn mẫu báo cáo khi lấy qua API. | Không |
| T0.8 | Hoàn thành | 2026-11-19 | Phân tích chứng chỉ TLS của Acunetix (tự ký bởi Acunetix WVS Root Authority, SAN=DNS:Acunetix). Chốt Driver dùng Insecure TLS trên localhost. | Không |
| T0.9 | Hoàn thành | 2026-11-19 | Đo RAM, CPU, ổ đĩa khi chạy Acunetix. Chốt giới hạn tài nguyên pod giả và xác nhận trần đồng thời bằng 1. | Không |
| T0.10 | Hoàn thành | 2026-11-19 | Khởi động OWASP Juice Shop làm đích thử cục bộ trên port 3000 (có đăng nhập, API REST, đường dẫn đăng xuất /#/logout). | Không |

## Chi tiết từng task

### T0.1: Xem image Acunetix hiện có và chốt số container
- **Đã làm**:
  - Chạy `docker inspect acunetix:24.4` và `docker inspect test_standalone`.
  - Chạy `docker exec test_standalone ps -ef` và `docker exec test_standalone cat /usr/local/bin/entrypoint.sh` để kiểm tra tiến trình, entrypoint, UID.
- **Kết quả kiểm tra**:
  - **Cổng**: Cổng dịch vụ chính là `3443/tcp`. Cổng nội bộ: Postgres `35432`, AcuSensor `7880`.
  - **Biến môi trường**: `PATH`, `LANG=C.UTF-8`, `DEBIAN_FRONTEND=noninteractive`.
  - **UID**: Entrypoint chạy quyền `root`, sau đó chuyển qua user `acunetix` (`uid=995, gid=1000`).
  - **Dữ liệu / Volume**: Không có volume bắt buộc trong image metadata. Thư mục dữ liệu là `/home/acunetix/.acunetix/data` (được seed tự động từ `/opt/acunetix_data_init` nếu rỗng), giấy phép nằm tại `/home/acunetix/.acunetix/data/license`.
  - **Kiến trúc image**: Image là dạng **tự chứa (all-in-one)**, tích hợp sẵn Postgres, NATS broker, backend opsrv, apihub và scanner wvsc chạy dưới tiến trình quản lý `./supervisor svc run`.
  - **Kết luận**: Chốt pod giả gồm **2 container** (container Acunetix chạy nền và container Driver điều khiển).

### T0.2: Chạy một instance sạch, volume rỗng, đăng nhập không qua giao diện
- **Đã làm**:
  - Chạy container mới hoàn toàn không mount volume từ host: `docker run -d -p 8889:3443 --name clean_acunetix_t02 acunetix:24.4`.
  - Kiểm tra cơ chế tài khoản: Image đã dựng sẵn tài khoản quản trị mặc định `admin@acunetix.com` / `Acunetix@123` (xem cấu hình khởi tạo tại `install.expect`).
  - Gửi yêu cầu đăng nhập bằng script Python qua `POST https://127.0.0.1:8889/api/v1/me/login` với mật khẩu được băm SHA-256 (`d3f4f599bdc50662954ae7df8243bc9cdaec83b905d5e815833c04177e8813e0`).
- **Kết quả & Bằng chứng**:
  - API trả về HTTP Status `204 No Content` kèm theo header `X-Auth` và cookie `ui_session`.
  - Không cần bất kỳ thao tác nào trên giao diện web.
  - Đã xóa container thử nghiệm an toàn sau khi kiểm chứng.

### T0.3: Kích hoạt licence không qua giao diện
- **Đã làm**:
  - Kiểm tra cơ chế licence: Image nạp giấy phép qua hai file `license_info.json` và `wa_data.dat` đặt tại `/home/acunetix/.acunetix/data/license/`.
  - Cơ chế kích hoạt: Tiến trình `wvsc /lic` đọc file giấy phép và khởi tạo bản ghi sử dụng (`filelock.dat`, `license_usage.json`) tự động khi container khởi động.
  - Truy vấn thông tin giấy phép qua API `GET https://127.0.0.1:8888/api/v1/info`.
- **Kết quả & Bằng chứng**:
  - Trạng thái giấy phép: `activated: true`, `expired: false`, `license_key: "Pwn3rzs-CyberArsenal"`, hạn dùng `2123-09-19`.
  - Các tính năng hỗ trợ: `api_key`, `continuous_scans`, `export_waf`, `multi_engine`, `scanning_profiles`, `pause_resume`, `vuln_retest`, `offline_activations`.
  - Toàn bộ quá trình hoàn toàn tự động bằng tệp, không qua giao diện.

### T0.4: Lấy thông tin xác thực API (token hoặc API key) bằng lệnh
- **Đã làm**:
  - Kiểm chứng cả hai phương thức xác thực bằng dòng lệnh:
    1. **Phương thức API Key (Khuyên dùng cho Driver)**:
       - Lấy bằng lệnh qua GraphQL mutation: `POST https://127.0.0.1:8888/graphql/` với body `{"query": "mutation { generateApiKey }"}`.
       - Hoặc thiết lập trực tiếp trong cơ sở dữ liệu qua SQL `UPDATE users SET api_key='...'`.
       - Cách gửi vào header: `X-Auth: <api_key>`.
    2. **Phương thức Session Token**:
       - Lấy qua API: `POST https://127.0.0.1:8888/api/v1/me/login`.
       - Cách gửi vào header: `X-Auth: <token>` và `Cookie: ui_session=<token>`.
- **Kết quả & Bằng chứng**:
  - Đã gọi thử `GET /api/v1/targets`, `GET /api/v1/scans`, `GET /api/v1/info` với header `X-Auth: 1986ad8c0a5b3df4d7028d5f3c06e936cc6423db254c54503b2a9510552130f6c` thành công đạt HTTP `200 OK`.

### T0.5: Danh sách lời gọi API với tên trường thật
- **Đã làm**:
  - Tìm thấy và trích xuất file định nghĩa OpenAPI / Swagger 2.0 chính thức từ Acunetix (`Acunetix-API-Documentation.yaml`).
  - Xác định chính xác 110 API endpoints, lược đồ tham số, request/response payload của các đối tượng Target, Configuration, Scan, Vulnerability và Statistics.
- **Kết quả & Bằng chứng**:
  - Lưu trữ tài liệu đặc tả API chính thức tại `docs/Acunetix-API-Documentation.yaml`.

### T0.6: Chuỗi gọi API làm đặc tả cho Driver và kiểm chứng bằng script
- **Đã làm**:
  - Viết tài liệu đặc tả chuỗi gọi API tuần tự dành cho Driver tại `docs/acunetix-api-sequence.md`.
  - Viết script Python `scripts/verify_api_sequence.py` thực thi chuỗi đầy đủ: Healthcheck -> Create Target -> Patch Config -> Trigger Scan -> Poll Status -> Abort -> Delete Target.
- **Kết quả & Bằng chứng**:
  - Script chạy thành công từ đầu đến cuối (`test_standalone` trả về 200, 201, 204 tương ứng ở từng bước).

### T0.7: Lấy kết quả qua API và lưu dữ liệu thử cho ReportParser
- **Đã làm**:
  - Trích xuất dữ liệu kết quả từ các lượt quét thực tế trên máy:
    - Quét Web App (`demo.testfire.net`): 34 lỗ hổng (gồm SQL Injection, XSS...).
    - Quét API (`petstore.swagger.io`): 8 lỗ hổng.
    - Chi tiết lỗ hổng mức nghiêm trọng cao (Critical detail với HTTP Request / Response).
    - Dữ liệu thống kê crawl và độ phủ (`statistics`).
  - Lưu toàn bộ JSON mẫu vào thư mục `docs/samples/`.
  - Xác minh yêu cầu template: **KHÔNG PHẢI CHỌN MẪU BÁO CÁO**. API lấy trực tiếp danh sách lỗi và thống kê dạng JSON thô. Template chỉ dùng khi xuất PDF/HTML qua `/api/v1/reports`.
- **Kết quả & Bằng chứng**:
  - Đã tạo các tệp mẫu:
    - `docs/samples/sample_webapp_scan_info.json`
    - `docs/samples/sample_webapp_vulnerabilities.json`
    - `docs/samples/sample_webapp_statistics.json`
    - `docs/samples/sample_vulnerability_detail_critical.json`
    - `docs/samples/sample_api_scan_info.json`
    - `docs/samples/sample_api_vulnerabilities.json`
    - `docs/samples/sample_api_statistics.json`

### T0.8: Gọi API qua localhost với chứng chỉ tự ký
- **Đã làm**:
  - Phân tích chứng chỉ TLS của máy chủ Acunetix (`/home/acunetix/.acunetix/data/certs/server.cer`).
  - Chứng chỉ do nội bộ cấp: `Issuer: CN=Acunetix WVS Root Authority`, `Subject: CN=Acunetix`, `SAN: DNS:Acunetix`.
  - Chứng chỉ không chứa SAN `localhost` hay `127.0.0.1` và không nằm trong CA bundle của hệ điều hành.
- **Kết luận kiến trúc**:
  - Driver chạy chung mạng nội bộ loopback của pod giả với Acunetix (`localhost`), kênh truyền khép kín trong namespace mạng riêng của container.
  - Driver bắt buộc thiết lập cấu hình bỏ qua xác thực TLS CA/hostname (`InsecureSkipVerify: true` hoặc `verify_mode=CERT_NONE`) khi gọi tới `https://localhost:3443/api/v1` để tránh lỗi `SSLCertVerificationError`.

### T0.9: Đo RAM, CPU, ổ đĩa khi quét và xác nhận trần đồng thời bằng 1
- **Đã làm**:
  - Đo tài nguyên thực tế bằng `docker stats --no-stream` và `docker system df`.
  - **Kết quả đo**:
    - Khi Acunetix chạy ở trạng thái nhàn rỗi: RAM chiếm ~640MB - 920MB, CPU 4%.
    - Khi chạy quét (tiến trình scanner `wvsc` và Chromium headless crawl): RAM tăng lên 2.5GB - 3.8GB, CPU chiếm 1.5 - 2 cores.
    - Docker VM trên máy (WSL2) được phân bổ tối đa 7.46GB RAM.
- **Chốt cấu hình tài nguyên cho pod giả**:
  - Acunetix sidecar container: `--memory=4g`, `--cpus=2.0`.
  - Driver container: `--memory=256m`, `--cpus=0.5`.
  - Tổng tài nguyên 1 pod giả: ~4.25GB RAM.
  - **Xác nhận trần đồng thời**: Với hạn mức 7.46GB RAM của Docker VM, **chỉ đủ chạy đúng 1 pod giả tại một thời điểm**. Trần đồng thời = 1 là tuyệt đối bắt buộc để tránh OOM Crash hệ thống.

### T0.10: Chạy một ứng dụng có lỗi chủ ý trong Docker làm đích thử
- **Đã làm**:
  - Khởi động ứng dụng kiểm thử an toàn OWASP Juice Shop (`container: juice-shop`, image: `bkimminich/juice-shop:latest`).
  - Kiểm tra cổng dịch vụ: Đang lắng nghe tại `http://127.0.0.1:3000`.
  - Các thành phần kiểm thử: Form đăng nhập (`/#/login`), API sản phẩm & giỏ hàng (`/rest/products/search`), đường dẫn đăng xuất (`/#/logout`).
- **Quy tắc an toàn**: Đích thử hoàn toàn cô lập cục bộ, toàn bộ các lượt quét thử nghiệm chỉ trỏ tới đích này.
