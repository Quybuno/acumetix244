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
| T0.11 | Hoàn thành | 2026-11-19 | Xóa và tạo lại instance liên tiếp: xác nhận dữ liệu sạch 100% (0 target, 0 scan) và license tự kích hoạt thành công đúng chuẩn pod giả dùng 1 lần. | Không |
| T1.1 | Hoàn thành | 2026-11-19 | Thiết lập quy ước tên `scan-<mã>-<vai trò>`, nhãn `scan-id`, `role`, cấu trúc thư mục tạm riêng theo lượt. Kiểm chứng lọc Docker chính xác. | Không |
| T1.2 | Hoàn thành | 2026-11-19 | Container giữ mạng (`alpine:3.20 sleep infinity` + `--add-host host.docker.internal:host-gateway`). Driver gọi localhost:3443 và webhook host thành công. | Không |
| T1.3 | Hoàn thành | 2026-11-19 | Khởi động tuần tự Net -> Acunetix -> Probe readiness (nc + curl) với timeout -> Driver. Driver chỉ chạy khi Acunetix trả lời được. | Không |
| T1.4 | Hoàn thành | 2026-11-19 | Tệp bí mật & tệp nhập gắn chỉ đọc (:ro) cho driver, không truyền qua biến môi trường (kiểm tra inspect không lộ), cô lập hoàn toàn với container khác, xóa sạch khi dọn. | Không |
| T1.5 | Hoàn thành | 2026-11-19 | Cấu hình giới hạn tài nguyên pod giả (--memory, --cpus theo số đo T0.9), không dùng cờ privileged. Máy host chạy mượt mà không bị nghẽn. | Không |
| T1.6 | Hoàn thành | 2026-11-19 | Thiết lập cơ chế hạn tối đa của pod giả (Job Timeout). Quá hạn tự động kill toàn bộ pod và đánh dấu lỗi SCAN_TIMEOUT. | Không |
| T1.7 | Hoàn thành | 2026-11-19 | Lưu log container driver (và acunetix) ra tệp tmp/scans/<mã>/logs/driver.log trước khi dọn. Đọc được nguyên nhân lỗi dù container đã bị xóa. | Không |
| T1.8 | Hoàn thành | 2026-11-19 | Dọn sạch toàn bộ container, volume, thư mục bí mật và tệp tạm theo nhãn scan-id=<mã>. Không làm ảnh hưởng container khác trên host. | Không |
| T1.9 | Hoàn thành | 2026-11-19 | Hàm get_pod_status(scan_id) trả về cấu trúc JSON chuẩn: trạng thái pod, mã thoát của driver, danh sách container thiếu. Sẵn sàng cho BE tích hợp. | Không |
| T1.10 | Hoàn thành | 2026-11-19 | Xây dựng hai script CLI launch.py và cleanup.py chạy tay với driver giả. Thấy trọn vẹn vòng đời dựng, chạy, driver thoát và dọn sạch 100%. | Không |
| T2.1 | Hoàn thành | 2026-11-19 | Dựng khung dự án driver (driver/): đọc cấu hình/secrets, ghi log có cấu trúc gắn scan_id, che phủ 100% bí mật (SecretMaskingFilter & mask_data). | Không |
| T2.2 | Hoàn thành | 2026-11-19 | Chờ API Acunetix sẵn sàng bằng thăm dò lặp lại có hạn chờ (Insecure TLS). Quá hạn thoát mã lỗi 10 (ACUNETIX_NOT_READY), không treo. | Không |
| T2.3 | Hoàn thành | 2026-11-19 | Khởi tạo xác thực API (hỗ trợ cả API key trực tiếp và tạo key động qua Login SHA-256 + GraphQL generateApiKey). Gọi API kiểm tra GET /api/v1/targets thành công. | Không |
| T2.4 | Hoàn thành | 2026-11-19 | Tạo target (POST /api/v1/targets) và cấu hình ScanOptions (PATCH configuration: profile, speed, crawl scope, excluded paths, headers, login). Xác nhận khớp 100% qua API. | Không |

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

### T0.11: Xóa instance rồi tạo lại từ đầu
- **Đã làm**:
  - Viết kịch bản kiểm chứng tự động `scripts/verify_ephemeral.py`:
    1. Tạo container 1 sạch (`ephemeral_test`).
    2. Kiểm tra trạng thái sạch: `Targets=0`, `Scans=0`, `LicenseActivated=True`.
    3. Thêm target để làm bẩn trạng thái container 1.
    4. Xóa hoàn toàn container 1 (`docker rm -f ephemeral_test`).
    5. Tạo container 2 mới toanh (`ephemeral_test2`) cùng cổng.
    6. Kiểm tra lại trạng thái container 2: Dữ liệu bẩn của container 1 mất sạch hoàn toàn (`Targets=0`, `Scans=0`), license tự động kích hoạt lại thành công (`LicenseActivated=True`).
    7. Dọn dẹp container 2.
- **Kết quả & Bằng chứng**:
  - Script chạy thành công (`verify_ephemeral.py` PASS toàn bộ assertions). Đảm bảo tính chất ephemeral (dùng một lần rồi vứt bỏ) hoàn hảo cho thiết kế pod giả mỗi lượt quét.

### T1.1: Quy ước tên và nhãn container, thư mục tạm theo lượt
- **Đã làm**:
  - Xây dựng module điều phối `scripts/pod_manager.py` chuẩn hóa quy ước:
    - Tên container: `scan-<mã>-<vai trò>` (với các vai trò: `net`, `acunetix`, `driver`).
    - Nhãn Docker: `scan-id=<mã>`, `role=<vai trò>`, `managed-by=deepreview-docker-launcher`.
    - Thư mục làm việc cách ly theo từng lượt quét: `tmp/scans/<mã>/` gồm các thư mục con `secrets/`, `inputs/`, `logs/`.
  - Hàm `list_pod_containers(scan_id)` lọc toàn bộ các container của một lượt quét bằng filter `label=scan-id=<mã>`.
- **Kết quả & Bằng chứng**:
  - Đã chạy thử nghiệm tạo 2 container gắn nhãn và xác minh hàm `list_pod_containers` nhận diện chính xác 100% qua lệnh `docker ps -a --filter label=scan-id=...`.

### T1.2: Container giữ mạng và liên lạc nội bộ / webhook
- **Đã làm**:
  - Xây dựng và kiểm chứng kiến trúc mạng chia sẻ (shared network namespace):
    1. Khởi động container giữ mạng `scan-<mã>-net` bằng `alpine:3.20 sleep infinity` với cờ `--add-host host.docker.internal:host-gateway`.
    2. Container Acunetix chạy với `--network container:scan-<mã>-net`.
    3. Container Driver chạy với `--network container:scan-<mã>-net`.
  - Tạo mock HTTP webhook server chạy trên máy host (cổng 9999).
- **Kết quả & Bằng chứng**:
  - Từ container Driver gọi `https://localhost:3443/api/v1/info` tới Acunetix thành công qua giao diện loopback nội bộ.
  - Từ container Driver gọi `http://host.docker.internal:9999/webhook` gửi payload webhook về máy host thành công (HTTP 200).

### T1.3: Khởi động pod theo thứ tự và kiểm tra ready trước khi chạy driver
- **Đã làm**:
  - Xây dựng hàm `launch_ordered_pod` trong `scripts/pod_manager.py` tuân thủ nghiêm ngặt thứ tự:
    1. Khởi động container giữ mạng `scan-<mã>-net`.
    2. Khởi động container Acunetix gắn cờ `--network container:...` và cấp quyền thư mục license.
    3. Thăm dò readiness (`wait_acunetix_ready`): sử dụng thăm dò nhanh socket TCP port 3443 qua netcat (`nc -z -w 1 127.0.0.1 3443`), sau đó kiểm tra HTTP status code qua `curl -k https://localhost:3443/api/v1/info`. Hạn chờ tối đa (timeout) mặc định 60-90s; nếu quá hạn sẽ hủy pod và báo lỗi `TimeoutError`.
    4. Chỉ khi Acunetix phản hồi HTTP thành công, container Driver (`scan-<mã>-driver`) mới được khởi chạy.
- **Kết quả & Bằng chứng**:
  - Chạy `python scripts/pod_manager.py test_t13`:
    - Acunetix khởi động và được probe thành công sau ~25s.
    - Container driver được bật lên và cả 3 container (`net`, `acunetix`, `driver`) đều ở trạng thái `running`.
    - Dọn dẹp sạch sẽ sau kiểm thử.

### T1.4: Tệp bí mật theo lượt và gắn chỉ đọc
- **Đã làm**:
  - Xây dựng hàm `prepare_scan_files(scan_id, secrets, inputs)` tạo file `credentials.json` trong `tmp/scans/<mã>/secrets/` (phân quyền chỉ chủ sở hữu đọc `0600`) và các tệp nhập trong `tmp/scans/<mã>/inputs/`.
  - Cập nhật hàm `launch_ordered_pod`:
    - Gắn volume chỉ đọc vào driver container: `-v <secrets>:/secrets:ro` và `-v <inputs>:/inputs:ro`.
    - Tuyệt đối không truyền bí mật hay token qua biến môi trường (`-e`).
    - Các container `net` và `acunetix` tuyệt đối không được mount thư mục secrets/inputs.
- **Kết quả & Bằng chứng**:
  - Chạy `python scripts/pod_manager.py test_t14`:
    - `docker inspect` cả 3 container: biến môi trường `Env` hoàn toàn sạch, không chứa secret.
    - `scan-<mã>-driver`: `/secrets` và `/inputs` có thuộc tính `RW: false` (Read-Only). Thử ghi file vào `/secrets/hacked.txt` bị hệ điều hành chặn với lỗi `Read-only file system`.
    - `scan-<mã>-net` và `scan-<mã>-acunetix`: không có mount nào tới `/secrets` hoặc `/inputs`.
    - Gọi `cleanup_pod`: toàn bộ thư mục tạm và tệp bí mật trên host bị xóa sạch không còn dấu vết.

### T1.5: Giới hạn tài nguyên và chế độ non-privileged
- **Đã làm**:
  - Áp dụng thông số tài nguyên đã chốt ở T0.9 vào `launch_ordered_pod`:
    - `scan-<mã>-net`: `--memory=64m`, `--cpus=0.1`.
    - `scan-<mã>-acunetix`: `--memory=4g`, `--cpus=2.0`.
    - `scan-<mã>-driver`: `--memory=256m`, `--cpus=0.5`.
    - Tuyệt đối không dùng chế độ đặc quyền `--privileged` cho bất kỳ container nào.
- **Kết quả & Bằng chứng**:
  - Chạy `python scripts/pod_manager.py test_t15`:
    - `docker inspect` kiểm chứng `HostConfig.Memory`: Net = 64MB (67108864 B), Acunetix = 4GB (4294967296 B), Driver = 256MB (268435456 B).
    - `HostConfig.NanoCpus`: Net = 0.1 CPU (100000000), Acunetix = 2.0 CPUs (2000000000), Driver = 0.5 CPUs (500000000).
    - `HostConfig.Privileged`: `False` trên toàn bộ 3 container.
    - Toàn bộ máy phát triển phản hồi bình thường, không bị chiếm dụng CPU/RAM quá mức.

### T1.6: Hạn tối đa của pod giả (Job Timeout) và dừng tự động
- **Đã làm**:
  - Xây dựng hàm `kill_pod(scan_id)`: dừng khẩn cấp toàn bộ các container đang chạy của một lượt quét bằng `docker kill`.
  - Xây dựng hàm `wait_pod_completion(scan_id, timeout_sec, poll_interval)`:
    - Giám sát trạng thái thoát của container driver.
    - Nếu thời gian chạy vượt quá trần hạn định của pod giả (`timeout_sec`), tự động kích hoạt `kill_pod(scan_id)`.
    - Trả về đối tượng trạng thái chuẩn: `status: "TIMEOUT"`, `timed_out: True`, `error: "SCAN_TIMEOUT"`.
- **Kết quả & Bằng chứng**:
  - Chạy `python scripts/pod_manager.py test_t16`:
    - Giả lập container driver bị treo (sleep 60s) với hạn Job Timeout thử nghiệm = 6 giây.
    - Hàm giám sát phát hiện quá hạn sau 6.76s, lập tức gửi tín hiệu kill tới toàn bộ nhóm container (`scan-t16timeout-driver`, `scan-t16timeout-acunetix`, `scan-t16timeout-net`).
    - Kiểm tra `docker inspect`: cả 3 container lập tức chuyển sang trạng thái `exited`.
    - Kết quả trả về đúng chuẩn `error: SCAN_TIMEOUT`. Dọn dẹp sạch sẽ sau test.

### T1.7: Lưu log của driver ra tệp trước khi dọn dẹp
- **Đã làm**:
  - Xây dựng hàm `save_pod_logs(scan_id)`: tự động xuất luồng output/error của container `driver` (và `acunetix`) ra tệp `tmp/scans/<mã>/logs/driver.log` và `acunetix.log`.
  - Nâng cấp hàm `cleanup_pod(scan_id, preserve_logs)`:
    - Khi kết thúc lượt quét hoặc xảy ra sự cố, hàm sẽ trích xuất và bảo toàn log ra đĩa trước khi xóa container.
    - Xóa các container Docker (`docker rm -f`).
    - Dọn sạch các thư mục bí mật `secrets/` và `inputs/`, nhưng vẫn giữ lại thư mục `logs/` phục vụ tra cứu.
- **Kết quả & Bằng chứng**:
  - Chạy `python scripts/pod_manager.py test_t17`:
    - Giả lập driver gặp lỗi chí mạng `FATAL ERROR: Target connection refused on mock port` và thoát mã lỗi `42`.
    - Gọi cleanup pod: xác nhận toàn bộ container thuộc pod đã biến mất khỏi Docker (`docker ps -a` trả về 0 container).
    - Mở tệp log `tmp/scans/t17logsave/logs/driver.log` trên host: log được lưu nguyên vẹn, đọc rõ ràng nguyên nhân lỗi và mã thoát `42` dù container đã bị hủy hoàn toàn.

### T1.8: Dọn sạch tài nguyên theo nhãn scan-id
- **Đã làm**:
  - Xây dựng hàm `purge_scan_resources(scan_id)`:
    - Tìm và xóa toàn bộ container có nhãn `scan-id=<mã>` (`docker rm -f`).
    - Tìm và xóa volume có nhãn `scan-id=<mã>` (nếu có).
    - Xóa toàn bộ thư mục tạm `tmp/scans/<mã>/` gồm `secrets/`, `inputs/`, `logs/`.
    - Tuyệt đối chỉ xóa tài nguyên khớp nhãn của lượt quét, không chạy các lệnh phá hủy diện rộng như `docker system prune` hay xóa volume chung.
- **Kết quả & Bằng chứng**:
  - Chạy `python scripts/pod_manager.py test_t18`:
    - Ghi nhận 18 container baseline đang chạy độc lập trên máy host.
    - Dựng nhóm container pod giả `t18cleanup` (gồm 3 container + thư mục tạm + secret).
    - Kích hoạt `purge_scan_resources`:
      - `docker ps -a --filter label=scan-id=t18cleanup` trả về đúng 0 container.
      - Thư mục `tmp/scans/t18cleanup` biến mất hoàn toàn khỏi đĩa host.
      - Kiểm tra lại 18 container baseline của host: 100% nguyên vẹn, không có bất kỳ ảnh hưởng nào.

### T1.9: Hàm đọc trạng thái nhóm container trả về JSON
- **Đã làm**:
  - Xây dựng hàm `get_pod_status(scan_id)` trong `scripts/pod_manager.py` đọc chi tiết trạng thái qua `list_pod_containers` và `docker inspect`:
    - Trả về đối tượng JSON hoàn chỉnh gồm:
      - `status`: `NOT_FOUND` | `RUNNING` | `COMPLETED` | `FAILED` | `DEGRADED`.
      - `driver_exit_code`: `int` khi driver kết thúc, hoặc `None` khi đang chạy / không tồn tại.
      - `missing_containers`: danh sách các vai trò bắt buộc bị thiếu trong số `['net', 'acunetix', 'driver']`.
      - `containers`: mảng chi tiết từng container (`name`, `role`, `id`, `state`, `status`, `exit_code`).
      - `error`: mã lỗi chi tiết nếu có (`DRIVER_EXIT_<code>`, `POD_NOT_FOUND`, `MISSING_ROLES_...`).
- **Kết quả & Bằng chứng**:
  - Chạy `python scripts/pod_manager.py test_t19`:
    - Khi pod không tồn tại: trả về `status: "NOT_FOUND"`, `driver_exit_code: null`, `missing_containers: ["net", "acunetix", "driver"]`.
    - Khi pod đang chạy: trả về `status: "RUNNING"`, `driver_exit_code: null`, `missing_containers: []`.
    - Khi driver chạy xong thoát mã 0: trả về `status: "COMPLETED"`, `driver_exit_code: 0`.
    - Khi xóa cưỡng bức container `net`: hàm lập tức phát hiện và trả về `missing_containers: ["net"]`.
    - Dữ liệu chuẩn xác 100% để phục vụ BE ở Giai đoạn 3 (giao diện bộ khởi chạy Job và Reconciler).

### T1.10: Hai script launch và cleanup chạy tay với driver giả
- **Đã làm**:
  - Xây dựng CLI `scripts/launch.py`:
    - Nhận tham số: `scan_id`, `--duration` (giây chạy của driver), `--exit-code` (mã thoát tùy ý), `--secrets-file`, `--timeout-ready`, `--wait`.
    - Tự động chuẩn bị secrets/inputs, khởi động nhóm container pod giả theo thứ tự và in kết quả JSON ra terminal.
  - Xây dựng CLI `scripts/cleanup.py`:
    - Nhận tham số: `scan_id`, `--preserve-logs`.
    - Xóa toàn bộ container và volume của pod theo nhãn `scan-id`.
    - Hỗ trợ lưu trữ log ra host để phân tích khi cần (`--preserve-logs`) hoặc dọn sạch triệt để toàn bộ thư mục tạm.
- **Kết quả & Bằng chứng**:
  - Chạy `python scripts/launch.py manual01 --duration 3 --wait`:
    - Khởi động thành công 3 container: `scan-manual01-net`, `scan-manual01-acunetix`, `scan-manual01-driver`.
    - Driver đọc được secret mount, chạy 3s và thoát mã 0.
    - Script in kết quả trạng thái cuối: `status: "COMPLETED"`, `driver_exit_code: 0`.
  - Chạy `python scripts/cleanup.py manual01 --preserve-logs`:
    - Dọn sạch 3 container khỏi Docker (0 remaining).
    - Bảo toàn log tại `tmp/scans/manual01/logs/driver.log` với nội dung ghi nhận đầy đủ.
  - Chạy `python scripts/cleanup.py manual01`:
    - Dọn sạch 100% thư mục tạm `tmp/scans/manual01` trên host.
  - Vòng đời: Dựng -> Chạy -> Driver thoát -> Dọn sạch hoạt động chuẩn xác và trực quan qua dòng lệnh.

## Kiểm tra Cổng sang Giai đoạn 2

**Tiêu chí TASKS.md**: "Chạy tay vài lần liên tiếp không để sót lại container, mạng hay tệp tạm nào."

- **Kịch bản kiểm chứng**: Thực thi `python scripts/verify_gate_phase1.py` chạy tự động 3 chu kỳ pod liên tiếp với các kịch bản thực tế:
  1. **Lượt 1 (`gate-run-1`)**: Chạy thành công bình thường (driver thoát mã `0`).
  2. **Lượt 2 (`gate-run-2`)**: Giả lập lỗi thực thi (driver thoát mã `1`).
  3. **Lượt 3 (`gate-run-3`)**: Lặp lại lượt chạy thành công (driver thoát mã `0`).
- **Kết quả kiểm tra từng dòng tiêu chuẩn**:
  - [x] **Container**: Không còn container nào mang nhãn `scan-id` hoặc `managed-by=deepreview-docker-launcher` sau mỗi lượt (`Leak check: 0 containers`).
  - [x] **Mạng**: Shared network namespace giải phóng sạch sẽ khi container `net` bị hủy, không tạo docker network rác.
  - [x] **Tệp tạm**: Thư mục `tmp/scans/<mã>` bị xóa sạch 100%, không sót thư mục `secrets`, `inputs`, `logs` nào (`Leak check: 0 temporary scan dirs`).
  - [x] **Tính ổn định**: 18 container khác trên host không bị ảnh hưởng, máy host phản hồi mượt mà.
- **Kết luận Cổng 2**: **ĐẠT (PASSED 100%)** - Toàn bộ Giai đoạn 1 đã hoàn thành xuất sắc. Sẵn sàng sang Giai đoạn 2 (Viết Driver).

### T2.1: Dựng khung dự án driver, đọc cấu hình và ghi log có cấu trúc che bí mật
- **Đã làm**:
  - Khởi tạo package `driver/` với cấu trúc module chuyên biệt:
    - `driver/logger.py`: Cung cấp `StructuredFormatter` định dạng chuẩn ISO-8601 kèm `[scan_id=<mã>]`, `SecretMaskingFilter` chặn đứng rò rỉ chuỗi bí mật, và hàm `mask_data` đệ quy che các trường nhạy cảm (`api_key`, `token`, `password`, `secret`, `authorization`, header value).
    - `driver/config.py`: Định nghĩa `DriverConfig` và hàm `load_config` nạp cấu hình từ `credentials.json`, options, và tham số CLI; trích xuất tự động danh sách chuỗi bí mật cần che chắn.
    - `driver/main.py`: Điểm vào chính của Driver tiếp nhận tham số dòng lệnh, khởi tạo logger và in ra cấu hình đã được che mờ toàn bộ bí mật.
- **Kết quả & Bằng chứng**:
  - Chạy kịch bản kiểm thử tự động `scripts/test_t21_driver.py`:
    - Tạo cấu hình chứa đầy đủ các trường nhạy cảm: `api_key`, `admin_password`, `webhook_token`, `target_credentials` và `custom_headers`.
    - Driver khởi động thành công, in ra log chuẩn cấu trúc `[ISO-TIMESTAMP] [INFO ] [scan_id=test-t21-scan]`.
    - Cấu hình in ra hiển thị `[REDACTED]` tại toàn bộ các trường nhạy cảm.
    - Quét toàn bộ stdout, stderr và tệp `driver.log`: 100% không chứa bất kỳ chuỗi mật khẩu/token/key thô nào (0 rò rỉ).
    - Driver kết thúc với mã thoát 0.

### T2.2: Chờ API Acunetix sẵn sàng bằng thăm dò lặp lại có hạn chờ
- **Đã làm**:
  - Xây dựng lớp `AcunetixClient` trong `driver/client.py`:
    - Cấu hình SSL context Insecure TLS (`verify_mode=CERT_NONE`) tương thích với chứng chỉ tự ký nội bộ của Acunetix theo T0.8.
    - Phương thức `probe_health()`: gửi yêu cầu `GET /api/v1/info` thăm dò phản hồi từ backend Acunetix.
    - Phương thức `wait_for_ready(timeout_seconds, poll_interval)`: lặp lại việc kiểm tra sau mỗi khoảng thời gian định kỳ. Nếu quá hạn `timeout_seconds`, ghi log cảnh báo và trả về `False`, đảm bảo tiến trình driver không bao giờ bị treo vô tận.
  - Tích hợp vào `driver/main.py`: nếu API Acunetix không sẵn sàng khi hết thời gian chờ, driver chủ động ghi log lỗi chí mạng và kết thúc ngay với mã thoát riêng `10` (`EXIT_CODE_ACUNETIX_NOT_READY`).
- **Kết quả & Bằng chứng**:
  - Chạy kịch bản kiểm thử `scripts/test_t22_readiness.py`:
    - **Trường hợp thành công**: Kiểm tra trực tiếp với instance Acunetix đang chạy tại `https://127.0.0.1:8888`. Driver phát hiện API sẵn sàng sau 0.55s, ghi nhận `Acunetix API is READY` và thoát mã `0`.
    - **Trường hợp quá hạn**: Kiểm tra với endpoint không tồn tại `https://127.0.0.1:59999` với hạn chờ 4 giây. Driver thực hiện thăm dò lặp lại, phát hiện quá hạn sau đúng 4.52s, ghi log `Readiness check timed out` và kết thúc với mã lỗi `10` mà không hề bị treo hay block tiến trình.

### T2.3: Khởi tạo instance và lấy thông tin xác thực API
- **Đã làm**:
  - Mở rộng lớp `AcunetixClient` trong `driver/client.py`:
    - Phương thức `login_and_generate_api_key(email, password)`: đăng nhập qua `POST /api/v1/me/login` với mật khẩu băm SHA-256 (`hashlib.sha256`), trích xuất session token và gửi tới endpoint GraphQL `POST /graphql/` với mutation `mutation { generateApiKey }` kèm cookie `ui_session` để nhận API key vĩnh viễn (định dạng 65 ký tự hex).
    - Phương thức `authenticate(api_key, email, password)`: hỗ trợ kiểm tra API key được cung cấp sẵn trước, nếu không có hoặc không hợp lệ sẽ tự động đăng nhập tài khoản quản trị để tạo API key động.
    - Phương thức `check_auth()`: xác thực token bằng lệnh gọi `GET /api/v1/targets?l=1` yêu cầu quyền hạn đầy đủ.
  - Cập nhật `driver/main.py`: tích hợp bước xác thực vào luồng chính, tự động đăng ký API key vào bộ lọc che dấu vết (`SecretMaskingFilter`) của logger, và xử lý mã thoát lỗi `11` (`EXIT_CODE_AUTH_FAILED`) nếu xác thực thất bại.
- **Kết quả & Bằng chứng**:
  - Chạy kịch bản kiểm thử `scripts/test_t23_auth.py`:
    - **Test 1 (Đăng nhập động + GraphQL)**: Đăng nhập với tài khoản `admin@acunetix.com` / `Acunetix@123`, nhận session token, gọi GraphQL sinh API key và xác thực `GET /api/v1/targets` thành công (HTTP 200, thoát mã 0).
    - **Test 2 (Dùng API key có sẵn)**: Xác thực trực tiếp qua header `X-Auth: <api_key>` thành công (HTTP 200, thoát mã 0).
    - **Test 3 (Bắt lỗi đăng nhập sai)**: Thử đăng nhập với mật khẩu sai, bắt đúng lỗi `401 Unauthorized` từ API Acunetix và thoát với mã lỗi `11` mà không rò rỉ mật khẩu vào log.

### T2.4: Tạo target và đặt cấu hình theo ScanOptions
- **Đã làm**:
  - Mở rộng lớp `AcunetixClient` trong `driver/client.py`:
    - Phương thức `create_target(address, description)`: gửi yêu cầu `POST /api/v1/targets` tạo target quét mới, trả về `target_id`.
    - Phương thức `configure_target(target_id, scan_options, secrets)`: gửi `PATCH /api/v1/targets/{target_id}/configuration` đặt các tham số quét theo ScanOptions:
      - `scan_speed`: tốc độ quét (`fast`).
      - `limit_crawler_scope`: giới hạn phạm vi crawl trong subdomain đích (`true`).
      - `default_scanning_profile_id`: ánh xạ preset hồ sơ quét (Full Scan -> `11111111-1111-1111-1111-111111111111`).
      - `excluded_paths`: mảng đường dẫn loại trừ (`/#/logout`, `/rest/user/logout`, `/assets/`).
      - `custom_headers`: mảng header tùy chỉnh dạng chuỗi `Header: Value`.
      - `login`: chế độ form đăng nhập tự động (`kind: "automatic"` kèm tài khoản và mật khẩu).
    - Phương thức `delete_target(target_id)`: xóa target qua `DELETE /api/v1/targets/{target_id}`.
  - Cập nhật `driver/main.py`: tích hợp bước tạo và cấu hình target vào luồng chính, bắt lỗi và thoát mã `12` (`EXIT_CODE_CONFIG_FAILED`) nếu cấu hình thất bại, đồng thời hỗ trợ cờ `--clean-target` cho kịch bản chạy thử nghiệm.
- **Kết quả & Bằng chứng**:
  - Chạy kịch bản kiểm thử `scripts/test_t24_target_config.py`:
    - Driver tạo target thành công với `target_id = 87a57ff8-b68e-410e-94f9-f4dfb6f7e97c`.
    - Gọi trực tiếp `GET /api/v1/targets/{target_id}/configuration` đối soát:
      - `scan_speed`: `fast`.
      - `limit_crawler_scope`: `true`.
      - `default_scanning_profile_id`: `11111111-1111-1111-1111-111111111111`.
      - `excluded_paths`: gồm đủ 3 đường dẫn loại trừ.
      - `custom_headers`: gồm `X-Security-Scan: DeepReview-Agent` và `X-Custom-Env: LocalTest`.
      - `login`: dạng `automatic` với username `admin@juice-sh.op` và mật khẩu được mã hóa an toàn.
    - Xóa dọn dẹp target thành công (`HTTP 204`), mật khẩu mục tiêu không bị lộ trong stdout/log.

### T2.5: Nạp tệp nhập và định nghĩa API vào target
- **Đã làm**:
  - Nghiên cứu cơ chế upload 2 bước (2-step upload) của Acunetix:
    - Bước 1: Khởi tạo tải tệp qua `POST /api/v1/targets/{target_id}/configuration/imports` (hoặc `.../login_sequence`) với payload `{"name": filename, "size": filesize}` nhận `upload_url` (`/uploads/<uuid>`).
    - Bước 2: Tải luồng nhị phân trực tiếp qua `POST {upload_url}` kèm các header bắt buộc: `Content-Type: application/octet-stream`, `Content-Range: bytes 0-{size-1}/{size}`, `Content-Disposition: attachment; filename="{filename}"` và `X-Auth`. Nhận mã trạng thái `204 No Content`.
  - Mở rộng lớp `AcunetixClient` trong `driver/client.py`:
    - `upload_file_stream(init_endpoint, file_path, filename)`: hàm chuẩn hóa thực thi luồng tải 2 bước.
    - `import_api_definition(target_id, file_path)`: nạp định nghĩa API (OpenAPI 3.0, Swagger, Postman, XML, HAR) vào cấu hình import của target.
    - `import_login_sequence(target_id, file_path)`: nạp chuỗi đăng nhập (`.lsr`) chuẩn định dạng JSON actions/restrictions và tự động kích hoạt `PATCH /api/v1/targets/{target_id}/configuration` với `{"login": {"kind": "sequence"}}`.
    - `import_inputs_from_directory(target_id, inputs_dir)`: tự động quét thư mục tệp nhập, phân loại và tải toàn bộ các tệp `.lsr` và định nghĩa API lên target, sau đó đối soát lại qua `GET /api/v1/targets/{target_id}/configuration/imports`.
  - Cập nhật `driver/main.py`: tích hợp bước nạp tệp nhập vào luồng thực thi chính sau khi cấu hình target, xử lý ngoại lệ và mã thoát lỗi riêng `13` (`EXIT_CODE_IMPORT_FAILED`).
- **Kết quả & Bằng chứng**:
  - Chạy kịch bản kiểm thử `scripts/test_t25_imports.py`:
    - Driver quét thư mục `inputs/`, phát hiện và nạp thành công 2 tệp: `login_flow.lsr` (756 bytes) và `openapi_juice.json` (554 bytes).
    - Gọi trực tiếp `GET /api/v1/targets/{target_id}/configuration/imports` trên Acunetix: tệp `openapi_juice.json` được ghi nhận với `status: True`.
    - Gọi trực tiếp `GET /api/v1/targets/{target_id}/configuration`: trường `login.kind` đã tự động chuyển sang `sequence`.
    - Dọn dẹp target thành công, không có bất kỳ mật khẩu hay token nào rò rỉ trong log. Driver kết thúc với mã thoát 0.

### T2.6: Tạo lượt quét chạy ngay và hỏi trạng thái định kỳ
- **Đã làm**:
  - Mở rộng lớp `AcunetixClient` trong `driver/client.py`:
    - `start_scan(target_id, profile_id)`: kích hoạt lượt quét chạy ngay qua `POST /api/v1/scans` với lịch `schedule: {disable: false, start_date: null}`, trả về `scan_id`.
    - `get_scan(scan_id)`: lấy thông tin chi tiết phiên quét qua `GET /api/v1/scans/{scan_id}` (trạng thái `scheduled`, `queued`, `starting`, `processing`, `completed`, `aborted`, `failed`, tỉ lệ tiến độ %, và cờ `manual_intervention`).
    - `abort_scan(scan_id)`: gửi lệnh dừng khẩn cấp qua `POST /api/v1/scans/{scan_id}/abort`.
    - `delete_scan(scan_id)`: xóa bản ghi scan qua `DELETE /api/v1/scans/{scan_id}`.
    - `poll_scan(scan_id, timeout_seconds, poll_interval)`: vòng lặp thăm dò trạng thái định kỳ, ghi log thay đổi tiến độ theo thời gian thực. Tự động phát hiện khi quá trần thời gian (`elapsed > timeout_seconds`) để gọi `abort_scan` và trả về trạng thái `"timeout"`.
  - Cập nhật `driver/main.py`:
    - Thêm tham số `--scan-timeout` (mặc định 1800s), `--poll-interval` (mặc định 3.0s), `--no-scan` (cho chế độ dry-run/setup only).
    - Tích hợp Bước 8 vào luồng chính: khởi tạo scan, thăm dò tiến độ. Nếu quá trần thời gian, driver chủ động hủy scan và kết thúc với mã lỗi `14` (`EXIT_CODE_SCAN_TIMEOUT`). Nếu gặp lỗi kết thúc thất bại, thoát mã `15` (`EXIT_CODE_SCAN_FAILED`).
- **Kết quả & Bằng chứng**:
  - Chạy kịch bản kiểm thử `scripts/test_t26_scan_lifecycle.py`:
    - **Test Case 1 (Quét thành công)**: Khởi tạo lượt quét với hồ sơ `crawl_only`, driver ghi nhận tiến trình chuyển từ `scheduled` -> `queued` -> `processing` -> `completed` (100%) sau 12.1 giây, thoát mã `0`.
    - **Test Case 2 (Quá trần thời gian & Abort)**: Đặt trần timeout cực ngắn 5s cho lượt quét `Full Scan`. Driver phát hiện quá hạn sau 5.1s, lập tức gửi lệnh abort tới Acunetix (`HTTP 204`), dọn dẹp target và kết thúc chính xác với mã lỗi `14` (`SCAN_TIMEOUT`).
    - Toàn bộ bí mật/mật khẩu không bị rò rỉ trong stdout/stderr/log.

### T2.7: Kiểm tra sau quét: LOGIN_FAILED, MANUAL_INTERVENTION, LOW_COVERAGE
- **Đã làm**:
  - Mở rộng lớp `AcunetixClient` trong `driver/client.py`:
    - `get_scan_statistics(scan_id, scan_session_id)`: gọi `GET /api/v1/scans/{scan_id}/results/{scan_session_id}/statistics` lấy dữ liệu chi tiết thống kê crawl (`locations`, `request_count`) và danh sách sự kiện/thông báo (`messages`).
    - `check_post_scan_health(scan_id, scan_info, statistics, scan_options, target_config)`: thực hiện kiểm định nghiệp vụ sau quét, đảm bảo trạng thái `Completed` của Acunetix không được coi là thành công nếu vi phạm 1 trong 3 điều kiện:
      1. `MANUAL_INTERVENTION`: phát hiện khi `manual_intervention=True` trên phiên quét hoặc trong thông báo sự kiện yêu cầu can thiệp thủ công (CAPTCHA, MFA).
      2. `LOGIN_FAILED`: phát hiện khi cấu hình có đăng nhập (`automatic` hoặc chuỗi `sequence`) nhưng Acunetix ghi nhận lỗi xác thực (`autologin_failed`, `lsr_failed`, thông báo `login failed`, `unable to authenticate`).
      3. `LOW_COVERAGE`: phát hiện khi số đường dẫn thu thập (`locations`) thấp hơn ngưỡng trần cấu hình (`min_locations`, mặc định 3) hoặc kết nối crawler preflight bị từ chối (`Could not connect to target host`).
  - Cập nhật `driver/main.py`:
    - Tích hợp Bước 9 kiểm định sau quét vào luồng chính.
    - Nếu vi phạm sức khỏe nghiệp vụ, ghi nhận cảnh báo bác bỏ trạng thái Completed của Acunetix và đánh dấu phiên quét chuyển sang `FAILED` kèm mã lỗi tương ứng (`LOGIN_FAILED`, `MANUAL_INTERVENTION`, `LOW_COVERAGE`).
- **Kết quả & Bằng chứng**:
  - Chạy kịch bản kiểm thử `scripts/test_t27_post_scan_health.py`:
    - **Test Case 1 (Thực tế CLI với LOW_COVERAGE)**: Quét crawler trên endpoint lỗi kết nối, Acunetix báo `completed` nhưng `locations` = 2 (< 5). Driver phát hiện lỗi kết nối preflight, bác bỏ trạng thái completed và đánh dấu `FAILED` với `error_code='LOW_COVERAGE'`.
    - **Test Case 2 (LOGIN_FAILED)**: Kiểm định trường hợp có thông báo lỗi đăng nhập (`autologin_failed`), hàm kiểm tra trả về `is_healthy=False`, `error_code='LOGIN_FAILED'`.
    - **Test Case 3 (MANUAL_INTERVENTION)**: Kiểm định cờ `manual_intervention=True`, hàm kiểm tra trả về `is_healthy=False`, `error_code='MANUAL_INTERVENTION'`.
    - **Test Case 4 (HEALTHY SCAN)**: Lượt quét có số locations hợp lệ, không có lỗi đăng nhập hay can thiệp người dùng, hàm kiểm tra trả về `is_healthy=True`.
    - Không phát hiện bất kỳ rò rỉ bí mật nào trong stdout/log.

### T2.8: Lấy danh sách lỗ hổng qua API phân trang kèm số liệu thu thập
- **Đã làm**:
  - Mở rộng lớp `AcunetixClient` trong `driver/client.py`:
    - `get_scan_vulnerabilities(scan_id, scan_session_id, page_size)`: duyệt qua toàn bộ các trang lỗ hổng bằng cơ chế con trỏ `?c=<cursor>&l=<limit>` dựa trên mảng `pagination.cursors` của Acunetix. Thu thập 100% bản ghi lỗ hổng mà không làm đứt đoạn hay bỏ sót dữ liệu.
  - Cập nhật `driver/main.py`:
    - Tích hợp Bước 10: Thu thập toàn bộ danh sách lỗ hổng và thống kê crawl, tổng hợp thành đối tượng kết quả chuẩn (`scan_result_payload`) gồm trạng thái tổng thể (`status`, `error_code`, `is_healthy`), số liệu phân rã theo mức nghiêm trọng (`severity_counts`), số đường dẫn crawl được (`locations`), và toàn bộ chi tiết danh sách lỗ hổng.
- **Kết quả & Bằng chứng**:
  - Chạy kịch bản kiểm thử `scripts/test_t28_vulnerabilities_pagination.py`:
    - **Test Live API**: Driver thực thi quét, hoàn tất polling, tự động gọi API phân trang thu thập kết quả và thống kê (`locations=2`). Đối soát trực tiếp với Acunetix REST API khớp 100%.
    - **Test Thuật toán phân trang đa trang**: Giả lập dữ liệu lớn trải dài qua 3 trang con trỏ (`page_0`, `cur_page1`, `cur_page2`), thuật toán duyệt chuẩn xác qua từng con trỏ, thu thập đủ 5/5 lỗ hổng theo đúng thứ tự.
    - Toàn bộ bản ghi lỗ hổng đều chứa đầy đủ các trường cốt lõi: `vuln_id`, `vt_name`, `severity`, `affects_url`, `status`.
    - Không phát hiện bất kỳ mật khẩu hay token nào rò rỉ trong log/output.

### T2.9: Dọn target trước khi gửi webhook
- **Đã làm**:
  - Tích hợp Bước 11 trong `driver/main.py`: tự động kích hoạt xóa target (`DELETE /api/v1/targets/{target_id}`) ngay sau khi thu thập xong dữ liệu lỗ hổng & thống kê (`scan_result_payload`) và **trước khi** gửi webhook về Backend.
  - Cơ chế tự động dọn dẹp theo mặc định (`--clean-target=True`), đồng thời hỗ trợ cờ `--keep-target` dành cho mục đích debug phát triển khi cần thiết.
  - Đảm bảo việc xóa target không làm ảnh hưởng đến payload kết quả đã được đóng gói an toàn trong bộ nhớ driver.
- **Kết quả & Bằng chứng**:
  - Chạy kịch bản kiểm thử `scripts/test_t29_target_cleanup.py`:
    - Driver tổng hợp payload kết quả trước: ghi nhận log `Scan payload compiled`.
    - Sau đó thực hiện xóa target: ghi nhận log `Cleaning up target <id> before webhook callback` -> `Target <id> and all associated scan data deleted successfully`.
    - Truy vấn trực tiếp Acunetix REST API:
      - `GET /api/v1/targets/{target_id}` trả về `HTTP 404 Not Found`.
      - `GET /api/v1/scans/{scan_id}` trả về `HTTP 404 Not Found` (toàn bộ bản ghi phiên quét, dữ liệu phát hiện và tệp nạp liên đới bị xóa sạch tự động theo cascade).
    - Không phát hiện rò rỉ bất kỳ mật khẩu hay token nào trong log/output.

### T2.10: Gửi webhook kèm token, thử lại khi lỗi mạng, thoát mã 50 khi thất bại
- **Đã làm**:
  - Xây dựng module `driver/webhook.py` với lớp `WebhookSender`:
    - Gửi kết quả quét dạng JSON POST tới `webhook_url` kèm token xác thực qua các header `X-Webhook-Token` và `Authorization: Bearer <token>`.
    - Cơ chế thử lại (retry) khi gặp lỗi mạng hoặc HTTP non-2xx: số lần thử tối đa (`max_retries`, mặc định 3) với độ trễ lũy tiến (`retry_delay * attempt`).
    - Ghi nhận chi tiết kết quả thử lại và log kích thước payload.
  - Cập nhật `driver/main.py`:
    - Định nghĩa mã thoát chuẩn `EXIT_CODE_WEBHOOK_FAILED = 50`.
    - Thêm tham số `--webhook-retries` và `--webhook-retry-delay`.
    - Tích hợp Bước 12: gửi `scan_result_payload` về Webhook server. Nếu hết số lần thử lại mà vẫn không thể kết nối, driver chủ động ghi log lỗi chí mạng và kết thúc tiến trình với mã thoát `50` để Reconciler tại Backend nhận diện sự cố `CALLBACK_LOST`.
- **Kết quả & Bằng chứng**:
  - Chạy kịch bản kiểm thử `scripts/test_t210_webhook.py`:
    - **Test Case 1 (Gửi thành công)**: Khởi động Mock Webhook Server, driver gửi payload hoàn chỉnh kèm token `X-Webhook-Token`, server nhận và xác thực khớp 100%, driver ghi nhận `HTTP 200` và thoát mã `0`.
    - **Test Case 2 (Lỗi mạng & Thoát mã 50)**: Trỏ webhook tới cổng không hoạt động, driver thực hiện đúng 3 lần thử lại (`attempt 1/3` -> `attempt 2/3` -> `attempt 3/3`), sau đó thoát chính xác với mã lỗi `50` (`CALLBACK_LOST`).
    - Quét toàn bộ stdout/stderr/log: Mật khẩu admin và chuỗi `webhook_token` được che chắn an toàn, không có bất kỳ rò rỉ nào.

### T2.11: Bảng mã thoát chuẩn hóa và đồng hồ riêng cho từng bước
- **Đã làm**:
  - Xây dựng module `driver/timer.py` với lớp `StepTimer`:
    - Đo lường chính xác thời gian thực thi của từng bước độc lập trong toàn bộ pipeline driver bằng `time.monotonic()`.
    - Xuất bảng tóm tắt thời gian thực thi có cấu trúc rõ ràng (`DRIVER EXECUTION TIMING SUMMARY`) khi driver kết thúc (dù thành công hay thất bại).
    - So sánh tổng thời gian driver với hạn mức trần của pod giả (`Job Timeout`, T1.6, mặc định 1860s) và tính toán khoảng đệm an toàn (`Margin to Job Kill`), đảm bảo driver luôn chủ động kết thúc hoặc báo lỗi trước khi bị hệ thống diệt cưỡng bức.
    - Đính kèm toàn bộ số liệu thời gian từng bước (`timings`) vào payload gửi về Webhook để lưu trữ và phục vụ phân tích hiệu năng tại Backend.
  - Chuẩn hóa bảng mã thoát trong `driver/main.py`:
    - `0`: Thực thi thành công (`EXIT_CODE_SUCCESS`).
    - `10`: Acunetix API chưa sẵn sàng quá hạn (`EXIT_CODE_ACUNETIX_NOT_READY`).
    - `11`: Xác thực hoặc đăng nhập thất bại (`EXIT_CODE_AUTH_FAILED`).
    - `12`: Tạo target hoặc cấu hình ScanOptions thất bại (`EXIT_CODE_CONFIG_FAILED`).
    - `13`: Nạp tệp nhập (OpenAPI/LSR) thất bại (`EXIT_CODE_IMPORT_FAILED`).
    - `14`: Quá trần thời gian quét hoặc phiên quét lỗi (`EXIT_CODE_SCAN_TIMEOUT` / `EXIT_CODE_SCAN_FAILED`).
    - `50`: Gửi webhook thất bại sau toàn bộ số lần thử lại (`EXIT_CODE_WEBHOOK_FAILED`).
- **Kết quả & Bằng chứng**:
  - Chạy kịch bản kiểm thử `scripts/test_t211_timings_and_exit_codes.py`:
    - **Test Case 1 (Bảng đồng hồ & So khớp Job Timeout)**: Driver chạy hoàn chỉnh toàn trình trong 11.00s, xuất bảng timing gồm đủ 10 bước độc lập. Đối soát trần Job Timeout (1860s) thấy khoảng đệm an toàn đạt 1849.00s. Webhook payload nhận được chứa đầy đủ trường `timings.steps`.
    - **Test Case 2 (Kiểm chứng các mã thoát)**: Kiểm thử kích hoạt chủ đích các mã thoát:
      - Khi Acunetix không sẵn sàng: Thoát chính xác mã `10`.
      - Khi quét quá hạn (timeout): Thoát chính xác mã `14`.
      - Khi webhook thất bại hết số lần thử: Thoát chính xác mã `50`.
    - Quét log: Không có rò rỉ mật khẩu/token.

### T2.12: Đóng gói driver thành Docker image non-root
- **Đã làm**:
  - Tạo `driver/Dockerfile`:
    - Sử dụng base image tối giản `python:3.12-alpine`.
    - Tạo group `driver` (GID 1000) và user `driver` (UID 1000), thư mục làm việc `/app`.
    - Phân quyền sở hữu toàn bộ mã nguồn driver cho UID 1000 (`chown -R driver:driver /app`).
    - Thiết lập chỉ thị `USER driver:driver` (non-root) để tuân thủ OpenShift Restricted SCC và Docker security best practices.
    - Cấu hình `ENTRYPOINT ["python", "-m", "driver.main"]`.
  - Viết kịch bản kiểm thử toàn diện `scripts/test_t212_driver_image.py`:
    - Kiểm tra build image: Docker image `deepreview-acunetix-driver:local` build thành công với dung lượng tối ưu ~74.6MB (không thư viện bên ngoài).
    - Kiểm tra định danh người dùng: Chạy `id` bên trong container xác nhận chính xác `uid=1000(driver) gid=1000(driver)`.
    - Kiểm tra thực thi CLI: Chạy `--help` hiển thị đầy đủ tùy chọn của driver với mã thoát `0`.
    - Kiểm tra chạy thực tế với volume mounts và mock arguments: Container thực thi chính xác và thoát đúng mã chuẩn khi không có cấu hình.
- **Kết quả & Bằng chứng**:
  - Kịch bản `scripts/test_t212_driver_image.py` chạy PASS 100% tất cả 4/4 bài kiểm tra.
  - Image sẵn sàng để tích hợp vào kiến trúc Pod giả (Giai đoạn 1) và khởi chạy thông qua Launcher ở Giai đoạn 3.

---

## CỔNG SANG GIAI ĐOẠN 3 (HOÀN THÀNH 100%)
- **Yêu cầu từ `docs/TASKS.md`**:
  > *"Thử driver trước khi nối vào BE: chạy driver riêng trên máy với một Acunetix đang chạy và một máy nhận webhook giả (một server nhỏ in ra nội dung nhận được). Khi chạy ổn mới đóng gói và chạy trong pod giả.*
  > *Cổng sang giai đoạn 3: driver quét xong đích thử (T0.10) có đăng nhập và API, và máy nhận webhook giả nhận được kết quả đủ."*
- **Kịch bản kiểm chứng**: `scripts/verify_gate_phase2.py`
  - Đích thử thực tế: OWASP Juice Shop (`http://host.docker.internal:3000` / `http://127.0.0.1:3000`).
  - Tệp chuỗi đăng nhập: `fixtures/juice_shop_login.lsr` (định dạng LSR JSON gồm các action navigate, change email/password, click loginButton).
  - Tệp đặc tả API: `fixtures/juice_shop_openapi.json` (OpenAPI 3.0 với các REST endpoints của Juice Shop).
  - Máy chủ webhook giả định: HTTP Server in ra nội dung payload nhận được lên console, kiểm tra token xác thực `X-Webhook-Token`.
- **Kết quả kiểm tra chi tiết**:
  1. **[PASS] CHECK 1 - Chạy driver độc lập trên máy host**:
     - Driver kết nối thành công với Acunetix (`https://127.0.0.1:8888`), tạo target, nạp LSR và OpenAPI.
     - Quét đích OWASP Juice Shop thành công trong 106.88s, kiểm tra post-scan health đạt chuẩn (`locations=123`, `is_healthy=True`).
     - Target và dữ liệu scan được tự động xóa dọn dẹp sạch sẽ khỏi Acunetix (`DELETE /targets/{id}`).
     - Mock Webhook Server nhận payload đầy đủ 100% (`status=COMPLETED`, `token=[VERIFIED]`, `timings`, `statistics`). Mã thoát `0`.
  2. **[PASS] CHECK 2 - Chạy driver đóng gói trong Docker Container (Non-root UID 1000)**:
     - Khởi chạy container `deepreview-acunetix-driver:local` với user non-root UID 1000, volume mounts bí mật/cấu hình/inputs `:ro`.
     - Container quét đích thử OWASP Juice Shop thành công trong 107.46s.
     - Mock Webhook Server nhận payload đầy đủ với kết quả `COMPLETED`. Mã thoát `0`.
  3. **[PASS] CHECK 3 - Kiểm tra an toàn bí mật (Zero Secret Leakage)**:
     - Quét toàn bộ stdout/stderr của cả hai lượt chạy, xác nhận mật khẩu admin, mật khẩu target và webhook token được che chắn an toàn 100%, không rò rỉ bất kỳ chuỗi nhạy cảm nào.
- **Kết luận**:
  - Toàn bộ 12 task của Giai đoạn 2 (`T2.1` -> `T2.12`) và toàn bộ tiêu chí của **Cổng sang giai đoạn 3** đã được kiểm chứng chạy thật thành công xuất sắc.

---

## Giai đoạn 3: Backend

### T3.1: Mô hình dữ liệu cho lượt quét, cấu hình có phiên bản và kết quả (Zero secrets in DB)
- **Đã làm**:
  - Thiết kế cấu trúc gói `backend/` gồm `db/` và `models/`.
  - Tạo `backend/db/schema.py`:
    - Bảng `scans`: `scan_id` (PK), `project_id`, `engine` (`acunetix`/`fortify`), `created_by`, `status` (`SCANNING`, `PARSING`, `COMPLETED`, `FAILED`), `error_code`, `target` (URL cho Acunetix, nhánh git cho Fortify), `token_hash` (chuỗi SHA-256 64 ký tự hex), `created_at`, `updated_at`, `completed_at`.
    - Bảng `scan_options_configs`: `id`, `scan_id` (FK), `version` (phiên bản cấu hình, ví dụ `1.0`), `config_json` (chỉ lưu các trường cấu hình không nhạy cảm), `created_at`.
    - Bảng `scan_results`: `id`, `scan_id` (FK), `status`, `vulnerabilities_count`, `severity_counts_json`, `vulnerabilities_json`, `statistics_json`, `timings_json`, `coverage_warnings_json`, `created_at`.
    - Định nghĩa danh sách các từ khóa cấm xuất hiện trong tên cột: `FORBIDDEN_COLUMN_SUBSTRINGS` (`password`, `secret`, `raw_token`, `api_key`, `credential`, v.v.).
  - Tạo `backend/db/database.py`:
    - Quản lý kết nối SQLite, kích hoạt ngoại khóa (`PRAGMA foreign_keys = ON;`), khởi tạo schema.
    - Phương thức kiểm tra toàn diện `verify_zero_secret_columns()` duyệt kiểm tra toàn bộ danh mục bảng và cột thực tế trong SQLite.
  - Tạo `backend/models/scan.py`:
    - Các dataclass `ScanJob`, `ScanOptionsConfig`, `ScanResult`.
    - Hàm băm an toàn `hash_webhook_token()` và so sánh thời gian hằng số `verify_webhook_token()` sử dụng `hmac.compare_digest`.
    - Lớp `ScanRepository` thực hiện các thao tác thêm, lấy, chuyển trạng thái và lưu kết quả an toàn.
  - Viết kịch bản kiểm thử tự động `scripts/test_t31_datamodels.py`.
- **Kết quả & Bằng chứng**:
  - Chạy `python scripts/test_t31_datamodels.py` PASS 100% tất cả 6 test suites:
    1. Kiểm tra cấu trúc bảng và xác nhận 100% **không có bất kỳ cột nào chứa secret** (`scans`, `scan_options_configs`, `scan_results`).
    2. Băm token SHA-256: token thô được băm 64-char hex và xác thực chính xác; token thô tuyệt đối không được ghi vào DB.
    3. Tạo lượt quét và máy trạng thái: chuyển giao trạng thái tuần tự `SCANNING` -> `PARSING` -> `COMPLETED`.
    4. Cấu hình có phiên bản `1.0`: lưu và đọc cấu hình không nhạy cảm thành công; model tự động bắt lỗi và từ chối khi cố tình lưu `admin_password` vào cấu hình.
    5. Lưu trữ kết quả: ghi nhận đầy đủ danh sách lỗ hổng, số lượng theo mức nghiêm trọng, thống kê crawl và bảng timings.
    6. Trích xuất thô (dump) toàn bộ cơ sở dữ liệu: đối soát không có bất kỳ mật khẩu hay token nào xuất hiện trong các bản ghi SQLite.

### T3.2: Lược đồ ScanOptions có phiên bản cho từng engine và API trả lược đồ cho FE
- **Đã làm**:
  - Tạo `backend/schemas/scan_options.py`:
    - Định nghĩa lược đồ biểu mẫu ScanOptions có phiên bản (`version: "1.0"`).
    - Biểu mẫu Acunetix: Phân tách thành 7 nhóm trường theo logic nghiệp vụ và mockup:
      1. `target`: URL mục tiêu (bắt buộc, loại `url`), mô tả.
      2. `preset`: Kiểu quét định sẵn (`fast_scan`, `deep_scan`, `crawl_only`, `owasp_top10`).
      3. `authentication`: Chế độ đăng nhập (`none`, `automatic`, `sequence`), tên đăng nhập, mật khẩu (`is_secret: True`, ẩn khi nhập), tệp kịch bản `.lsr` (`depends_on`).
      4. `imports`: Tệp đặc tả API (`.json`, `.yaml`, `.yml`, `.xml`, `.har`).
      5. `headers`: Danh sách Header bổ sung (`key_value_list`, `is_secret: True`).
      6. `scope`: Đường dẫn loại trừ (`excluded_paths`).
      7. `advanced`: Tốc độ quét (`scan_speed`), giới hạn thu thập (`crawl_limit`), thời hạn tối đa (`scan_timeout_minutes`).
    - Biểu mẫu Fortify: Lược đồ SAST tương thích với mục tiêu là nhánh Git (`git_branch`).
    - **Ràng buộc an toàn & trừu tượng hóa**: 100% không để lộ các tên trường nội bộ của Acunetix (như `default_scanning_profile_id`, `limit_crawler_scope`, `sensor_secret`, `ssh_credentials`) ra phía Frontend.
  - Tạo `backend/api/schema_handler.py`:
    - Endpoint `GET /api/v1/schemas/engines`: Trả về danh sách engine được hỗ trợ (`acunetix`, `fortify`).
    - Endpoint `GET /api/v1/schemas/scan-options?engine=<engine>`: Trả về chi tiết lược đồ ScanOptions để FE dựng form động.
    - Xử lý kiểm tra lỗi: Engine không hợp lệ hoặc thiếu tham số trả về HTTP 400 Bad Request rõ ràng.
  - Viết kịch bản kiểm thử tự động `scripts/test_t32_scan_options_schema.py`.
- **Kết quả & Bằng chứng**:
  - Chạy `python scripts/test_t32_scan_options_schema.py` PASS 100% tất cả 4 test suites:
    1. Lược đồ Acunetix: Đủ 7 nhóm trường, ràng buộc kiểu dữ liệu, các preset định sẵn, điều kiện hiển thị (`depends_on`), cờ bảo mật (`is_secret: True`).
    2. Đối soát tên trường: Kiểm tra danh sách từ khóa nội bộ của Acunetix, xác nhận 0% rò rỉ tên trường Acunetix ra schema.
    3. Lược đồ Fortify: Tương thích hoàn toàn với nhánh Git.
    4. HTTP API Server:
       - `GET /api/v1/schemas/engines` -> `HTTP 200`
       - `GET /api/v1/schemas/scan-options?engine=acunetix` -> `HTTP 200`
       - `GET /api/v1/schemas/scan-options?engine=fortify` -> `HTTP 200`
       - `GET /api/v1/schemas/scan-options?engine=invalid` -> `HTTP 400`
       - `GET /api/v1/schemas/scan-options` (thiếu engine) -> `HTTP 400`

### T3.3: API tạo lượt quét (Validation, trần đồng thời, sinh token, gọi bộ khởi chạy)
- **Đã làm**:
  - Tạo `backend/validation/scan_validator.py`:
    - Kiểm tra siêu dữ liệu cơ bản: `engine`, `project_id`, `created_by`.
    - Kiểm tra trường lạ: Từ chối ngay các trường lạ không nằm trong lược đồ của engine.
    - Kiểm tra mục tiêu cho Acunetix: `target_url` là bắt buộc (từ chối lượt Acunetix thiếu URL); kiểm tra định dạng cú pháp; chặn thông tin đăng nhập trong URL (`user:pass@host`); chặn query param chứa token nhạy cảm (`token`, `api_key`, `secret`, `auth`); kiểm tra URL nằm trong danh sách Allowlist được cấp phép.
    - Kiểm tra tệp tải lên: Giới hạn kích thước và chỉ chấp nhận đuôi tệp cho phép (`.lsr`, `.json`, `.yaml`, `.yml`, `.xml`, `.har`).
  - Tạo `backend/services/launcher.py`: Định nghĩa giao diện `LauncherInterface` và lớp `MockLauncher` phục vụ kiểm thử đơn vị độc lập.
  - Tạo `backend/services/scan_service.py`:
    - Kiểm tra trần đồng thời (`MAX_CONCURRENT_SCANS`, mặc định 1): Đếm các lượt đang ở trạng thái `SCANNING` hoặc `PARSING`. Vượt trần từ chối ngay với HTTP 429 (`CONCURRENCY_LIMIT_EXCEEDED`).
    - Sinh webhook token ngẫu nhiên an toàn (`secrets.token_urlsafe(32)`), băm SHA-256 (`token_hash`) và chỉ lưu bản băm vào DB bảng `scans` với trạng thái ban đầu `SCANNING`.
    - Tách biệt `ScanOptions` thành phần thường (lưu DB với version 1.0) và phần bí mật (chuyển cho launcher rồi xóa sạch khỏi bộ nhớ BE).
    - Gọi launcher khởi tạo pod/job.
  - Tạo `backend/api/scan_handler.py`: Endpoint `POST /api/v1/scans` trả về HTTP 201 Created kèm `scan_id` khi thành công, hoặc HTTP 400/429 khi có lỗi.
  - Viết kịch bản kiểm thử tự động `scripts/test_t33_create_scan_api.py`.
- **Kết quả & Bằng chứng**:
  - Chạy `python scripts/test_t33_create_scan_api.py` PASS 100% tất cả 7 test suites:
    1. Tạo lượt quét hợp lệ: Trả về HTTP 201 Created, trạng thái `SCANNING`, token băm trong DB, zero secret trong phản hồi API và cấu hình DB.
    2. Lượt Acunetix thiếu `target_url`: Bị từ chối với HTTP 400 Bad Request.
    3. URL chứa thông tin đăng nhập (`user:pass@host`) hoặc query param token: Bị từ chối với HTTP 400 Bad Request.
    4. URL ngoài danh sách Allowlist: Bị từ chối với HTTP 400 Bad Request.
    5. Cấu hình có trường lạ: Bị từ chối với HTTP 400 Bad Request.
    6. Tệp tải lên sai định dạng (`.exe`): Bị từ chối với HTTP 400 Bad Request.
    7. Trần đồng thời = 1: Lượt 1 đang chạy, lượt 2 gửi đến bị từ chối ngay lập tức với HTTP 429 `CONCURRENCY_LIMIT_EXCEEDED`; sau khi lượt 1 chuyển `COMPLETED`, lượt 2 được chấp nhận thành công.





