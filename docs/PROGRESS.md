# Tiến độ triển khai Acunetix vào Deep Review trên Docker

## Nhật ký công việc

| Mã task | Trạng thái | Ngày | Tóm tắt kết quả / Bằng chứng | Việc còn treo |
|---------|------------|------|------------------------------|---------------|
| T0.1 | Hoàn thành | 2026-11-19 | Đã kiểm tra image acunetix:24.4 (inspect, ps). Image tự chứa (all-in-one). Chốt pod giả gồm 2 container (Acunetix + Driver). | Không |

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
