# Tiến độ triển khai Acunetix vào Deep Review trên Docker

## Nhật ký công việc

| Mã task | Trạng thái | Ngày | Tóm tắt kết quả / Bằng chứng | Việc còn treo |
|---------|------------|------|------------------------------|---------------|
| T0.1 | Hoàn thành | 2026-11-19 | Đã kiểm tra image acunetix:24.4 (inspect, ps). Image tự chứa (all-in-one). Chốt pod giả gồm 2 container (Acunetix + Driver). | Không |
| T0.2 | Hoàn thành | 2026-11-19 | Chạy container sạch không mount volume, xác thực đăng nhập tự động qua API POST /api/v1/me/login thành công (HTTP 204), không cần giao diện. | Lưu ý cấp quyền thư mục license cho acunetix user |
| T0.3 | Hoàn thành | 2026-11-19 | Kích hoạt license tự động qua file (license_info.json, wa_data.dat) không qua UI. API /api/v1/info xác nhận activated=true, hạn đến năm 2123. | Không |

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
