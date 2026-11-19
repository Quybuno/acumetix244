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
