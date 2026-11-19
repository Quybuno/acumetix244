# Task xây dựng hệ thống quét Acunetix trên Docker


## 1. Mục tiêu và phạm vi

Xây hệ thống quét Acunetix cho Deep Review chạy hoàn toàn trên máy của anh. Chưa có OpenShift nên mỗi lượt quét chạy trong một “pod giả” gồm các container Docker. Luồng và các thành phần giữ như [Kế hoạch triển khai Acunetix vào Deep Review](https://claude.ai/artifact/SxBZ4jE23eTALhz5ghX5wp); chỉ lớp khởi chạy pod được thay bằng Docker, để sau này chuyển sang OpenShift mà không phải viết lại phần còn lại.

**Đã có sẵn:** image Acunetix, licence, Docker trên máy (RAM 16GB, còn khoảng 32GB ổ trống) và [mockup trang Scans có chọn engine](https://claude.ai/artifact/18PwybqnKizeNR5dhgP3Cw).

**Trong phạm vi**

- FE: chọn engine, form ScanOptions trong ngăn kéo, bảng lịch sử, hiển thị kết quả.
- BE: API lượt quét, ScanOptions, bộ khởi chạy Docker, máy trạng thái, nhận webhook, ReportParser, Reconciler.
- Driver: chương trình điều khiển Acunetix trong pod giả rồi gửi kết quả về BE.
- Pod giả: script hoặc mã khởi động nhóm container, giới hạn tài nguyên, dọn dẹp.
- Kiểm thử toàn trình trên Docker, kể cả giả lập lỗi.

**Ngoài phạm vi (chờ có OpenShift)**

- Job, Secret, NetworkPolicy, SCC, ResourceQuota và registry nội bộ thật.
- Kiểm chứng trần đồng thời theo năng lực cụm.
- Lên lịch quét (do Deep Review lo), chỉ làm quét chạy ngay.

**Kết quả mong muốn:** từ màn Scans, chọn Acunetix, điền form, bấm bắt đầu quét; BE dựng pod giả, driver quét xong gửi webhook, báo cáo hiện trong Deep Review mà không ai mở giao diện Acunetix.

## 2. Kiến trúc: Docker thay pod

Luồng giống kế hoạch OpenShift; chỉ khác nơi chạy: thay vì một pod, BE dựng một nhóm container Docker cho mỗi lượt quét.

&#91;embedded content: kiến trúc trên Docker · FE, BE, pod giả, driver\]

FE gửi form tới BE; BE dựng pod giả; trong pod giả chỉ driver nói chuyện với Acunetix qua localhost rồi gửi kết quả về BE bằng webhook trước khi thoát.

| OpenShift | Docker trên máy anh |
| --- | --- |
| Pod | Nhóm container cùng nhãn mã lượt quét, chung mạng |
| Sidecar (Acunetix) | Container chạy nền, khởi động theo thứ tự có kiểm tra sẵn sàng |
| Container chính (driver) | Container chạy tới khi thoát; mã thoát là kết quả |
| Secret của lượt quét | Tệp tạm gắn chỉ đọc vào driver, xóa khi dọn |
| Dọn Job và TTL | Xóa mọi container theo nhãn, giữ log ra tệp trước |
| Hạn tối đa của Job | Reconciler hoặc script dừng container khi quá hạn |
| Giới hạn tài nguyên | Giới hạn memory và cpu cho từng container |
| Trần đồng thời | BE đếm số nhóm container đang chạy |
| Reconciler tìm Job mất | Lọc container theo nhãn, so với trạng thái trong DB |

## 3. Quyết định đã chốt và giả định đang dùng

Các quyết định dưới đây kế thừa kế hoạch OpenShift, chỉ đổi phần hạ tầng sang Docker.

| Quyết định | Nội dung |
| --- | --- |
| Một lượt quét, một pod giả | Nhóm container Docker cùng nhãn mã lượt quét, chung mạng, sống và chết cùng nhau |
| Bộ khởi chạy tách thành giao diện | BE chỉ gọi launch, status, kill, cleanup; làm bản Docker trước, bản OpenShift sau |
| Driver là container chính duy nhất | Acunetix chạy nền; driver thoát thì pod giả kết thúc |
| Chung mạng nội bộ | Một container giữ mạng, các container khác chạy với `--network container:<tên>`; driver gọi API Acunetix ở localhost |
| Số container | Chốt ở nhiệm vụ T0.1 theo image anh có: image tự chứa thì hai container (Acunetix và driver), image tách thì bốn |
| Secret | Tách phần thường (lưu DB) và phần bí mật (tệp tạm theo lượt gắn chỉ đọc vào driver, xóa khi dọn, không vào DB hay log) |
| Không tự thử lại | Pod giả chết giữa chừng thì lượt quét thất bại; BE không giữ kết nối, chờ webhook |
| Webhook có token | Token ngẫu nhiên mỗi lượt, DB chỉ lưu bản băm |
| Trần đồng thời bằng 1 | RAM 16GB chỉ đủ cho một pod giả mỗi lần; vượt trần thì từ chối, không xếp hàng |
| Kết quả lấy bằng API | Driver lấy JSON trước khi thoát, BE dùng ReportParser đổi sang UnifiedReport |
| Chỉ quét chạy ngay | Lên lịch do Deep Review lo |
| Trạng thái và mã lỗi | SCANNING, PARSING, COMPLETED, FAILED; mã JOB\_LOST, CALLBACK\_LOST, PARSE\_FAILED, SCAN\_TIMEOUT, LOGIN\_FAILED, MANUAL\_INTERVENTION, LOW\_COVERAGE |

**Giả định chưa kiểm chứng** (các nhiệm vụ giai đoạn 0 sẽ trả lời):

- Licence chạy được trong container mới mỗi lượt quét và không vượt số instance được phép.
- Khởi tạo instance (kích hoạt licence, tài khoản admin, lấy API key) làm được không qua giao diện.
- Tên trường API và cấu trúc JSON kết quả (chỉ có tài liệu cộng đồng, phải bắt thật qua tab Network).
- Báo cáo có bắt buộc chọn mẫu (template) hay không khi lấy qua API.
- Máy chủ chính dùng chứng chỉ tự ký, driver cần xử lý đúng khi gọi qua localhost.
- Giới hạn kích thước của webhook với kết quả lớn.

## 4. Giai đoạn 0: dựng Acunetix trên máy và khám phá

Làm trước hết, vì kết quả quyết định các giai đoạn sau. Mục tiêu: chạy được toàn bộ chuỗi quét bằng dòng lệnh, không mở giao diện.

| Task | Việc làm và kết quả |
| --- | --- |
| T0.1 | Xem image anh có (`docker images`, `docker inspect`): cổng, biến môi trường, UID, volume. Kết quả: biết image tự chứa hay tách máy chủ chính, worker, Postgres, từ đó chốt số container của pod giả |
| T0.2 | Chạy một instance sạch, volume rỗng, tài khoản quản trị đặt bằng biến môi trường. Kết quả: đăng nhập được mà không bấm giao diện |
| T0.3 | Kích hoạt licence không qua giao diện (biến môi trường, tệp, lệnh hoặc API). Kết quả: instance mới có licence; nếu bắt buộc qua giao diện thì ghi lại và hỏi hãng |
| T0.4 | Lấy thông tin xác thực API (token đăng nhập hoặc API key) bằng lệnh. Kết quả: ghi cách gửi vào header |
| T0.5 | Mở giao diện trên instance đang chạy, quét thử một lượt đầy đủ (đăng nhập, header, loại trừ, tệp API, hồ sơ quét) và xem tab Network của trình duyệt. Kết quả: danh sách lời gọi API với tên trường thật |
| T0.6 | Làm lại chuỗi đó bằng curl hoặc script: tạo target, đặt cấu hình, nạp tệp, bắt đầu quét, hỏi tiến độ. Kết quả: tài liệu “chuỗi gọi API” dùng làm đặc tả cho driver |
| T0.7 | Lấy kết quả qua API: danh sách lỗi (phân trang), số đường dẫn thu thập, trạng thái đăng nhập. Kết quả: lưu một đến hai JSON mẫu làm dữ liệu thử cho ReportParser; ghi rõ có phải chọn mẫu báo cáo hay không |
| T0.8 | Gọi API qua localhost với chứng chỉ tự ký. Kết quả: biết driver cần xử lý chứng chỉ thế nào |
| T0.9 | Đo RAM, CPU, ổ cứng khi quét (`docker stats`, `docker system df`). Kết quả: mức giới hạn memory và cpu cho pod giả, xác nhận trần đồng thời bằng 1 |
| T0.10 | Chạy một ứng dụng có lỗi chủ ý trong Docker làm đích thử: có đăng nhập, API có định nghĩa, đường dẫn đăng xuất. Kết quả: đích an toàn, chỉ quét đích này |
| T0.11 | Xóa instance rồi tạo lại từ đầu. Kết quả: dữ liệu mất sạch, licence và khởi tạo vẫn chạy lại được, đúng như một pod giả dùng một lần |

**Cổng sang giai đoạn 1:** T0.2, T0.3, T0.4 và T0.6 chạy được. Nếu licence bắt buộc kích hoạt qua giao diện (T0.3), dùng phương án dự phòng: một instance Acunetix dùng chung lâu dài trên máy, BE (hoặc adapter) gọi API trực tiếp, bỏ pod giả mỗi lượt.

## 5. Giai đoạn 1: pod giả bằng Docker

Mục tiêu: một lệnh dựng được nhóm container đúng như một pod, một lệnh dọn sạch. Làm bằng script trước, chưa cần BE; dùng một “driver giả” (container chờ vài giây rồi thoát với mã tùy ý) để thử vòng đời.

| Task | Việc làm và kết quả |
| --- | --- |
| T1.1 | Quy ước tên và nhãn: container đặt `scan-<mã>-<vai trò>`, nhãn `scan-id`, `role`; mỗi lượt có một thư mục tạm riêng. Kết quả: lọc được toàn bộ container của một lượt bằng một nhãn |
| T1.2 | Container giữ mạng (nhẹ, chạy chờ); các container khác chạy với `--network container:<tên>`. Kết quả: từ container driver gọi `localhost:<cổng>` tới Acunetix thành công; driver gọi được địa chỉ host (ví dụ `host.docker.internal`) để tới webhook |
| T1.3 | Khởi động theo thứ tự (cơ sở dữ liệu, máy chủ chính, worker nếu tách, cuối cùng driver), mỗi bước chờ kiểm tra sẵn sàng và có hạn chờ. Kết quả: driver chỉ chạy khi Acunetix trả lời được |
| T1.4 | Tệp bí mật theo lượt: tệp tạm chỉ chủ sở hữu đọc, gắn chỉ đọc vào driver, không truyền bằng biến môi trường vì docker inspect sẽ lộ, tệp nhập (.lsr, API, .js) gắn chỉ đọc. Kết quả: driver đọc được, không container nào khác đọc được, xóa được khi dọn |
| T1.5 | Giới hạn tài nguyên (`--memory`, `--cpus` theo số đo T0.9), không chạy ở chế độ đặc quyền. Kết quả: máy anh vẫn dùng được khi pod giả đang quét |
| T1.6 | Hạn tối đa của pod giả (tương đương hạn của Job): quá hạn thì bị dừng. Kết quả: hạn này dài hơn trần chờ của driver, để driver tự báo lỗi trước |
| T1.7 | Lưu log của driver ra tệp trước khi dọn. Kết quả: đọc được nguyên nhân khi lỗi dù container đã bị xóa |
| T1.8 | Dọn: xóa mọi container theo nhãn, volume tạm, thư mục bí mật. Kết quả: không còn container, mạng hay tệp nào của lượt đó |
| T1.9 | Hàm đọc trạng thái nhóm container: đang chạy, driver đã thoát với mã nào, thiếu container nào. Kết quả: đầu ra dạng JSON để BE dùng sau này |
| T1.10 | Hai script `launch` và `cleanup`, chạy tay với driver giả. Kết quả: thấy đúng vòng đời dựng, chạy, driver thoát, dọn |

**Cổng sang giai đoạn 2:** chạy tay vài lần liên tiếp không để sót lại container, mạng hay tệp tạm nào.

**Lưu ý bảo mật:** khi BE điều khiển Docker (giai đoạn 3) cần quyền truy cập Docker socket, gần như quyền root trên máy. Chỉ dùng cho máy phát triển của anh, không mang cấu hình này lên môi trường chung.

## 6. Giai đoạn 2: driver

Driver là chương trình nhỏ anh tự viết, chạy một lần trong pod giả, làm thay việc mà người dùng làm tay trên giao diện Acunetix rồi gửi kết quả về BE. Viết bằng ngôn ngữ anh quen nhất, miễn đóng được thành image và gọi được HTTP. Dựa vào tài liệu chuỗi gọi API ở T0.6.

**Đầu vào của driver:** phần cấu hình thường, tệp bí mật (tài khoản admin, licence, mật khẩu đích, giá trị header, token webhook), các tệp nhập gắn chỉ đọc, mã lượt quét và địa chỉ webhook.

| Task | Việc làm và kết quả |
| --- | --- |
| T2.1 | Dựng khung dự án driver: đọc cấu hình, ghi log có cấu trúc gắn mã lượt quét, không bao giờ ghi mật khẩu hay token. Kết quả: chạy được, in ra cấu hình đã che bí mật |
| T2.2 | Chờ API sẵn sàng bằng cách hỏi lặp lại, có hạn chờ. Kết quả: quá hạn thì thoát với mã lỗi, không treo |
| T2.3 | Khởi tạo instance và lấy thông tin xác thực API (kích hoạt licence, tài khoản admin, API key) theo cách chốt ở T0.2 đến T0.4. Kết quả: có thể gọi API có xác thực |
| T2.4 | Tạo target và đặt cấu hình theo ScanOptions: hồ sơ quét theo preset, đăng nhập, header, đường dẫn loại trừ, giới hạn thu thập, nâng cao. Kết quả: target hiện đúng cấu hình khi xem trên giao diện Acunetix |
| T2.5 | Nạp tệp nhập và định nghĩa API. Kết quả: các endpoint từ tệp xuất hiện trong site structure |
| T2.6 | Tạo lượt quét chạy ngay, hỏi trạng thái định kỳ tới khi xong. Kết quả: quá trần thời gian thì thoát với mã SCAN\_TIMEOUT |
| T2.7 | Kiểm tra sau quét: đăng nhập có thành công không (LOGIN\_FAILED), có dừng chờ người không (MANUAL\_INTERVENTION), số đường dẫn thu thập có thấp bất thường không (LOW\_COVERAGE). Kết quả: trạng thái Completed của Acunetix không được coi là thành công nếu một trong ba điều này xảy ra |
| T2.8 | Lấy hết danh sách lỗi qua API (phân trang) kèm số liệu thu thập. Kết quả: đủ dữ liệu so với số trên giao diện |
| T2.9 | Dọn target. Kết quả: làm xong trước khi gửi webhook vì kết quả mất cùng pod giả |
| T2.10 | Gửi webhook kèm token, thử lại khi lỗi mạng. Kết quả: hết số lần thử thì thoát với mã 50 để Reconciler nhận ra CALLBACK\_LOST |
| T2.11 | Bảng mã thoát và đồng hồ riêng cho từng bước. Kết quả: tổng thời gian driver nhỏ hơn hạn tối đa của pod giả (T1.6) |
| T2.12 | Đóng gói thành image, có Dockerfile và thiết lập chạy không dùng quyền root. Kết quả: build được, chạy trong pod giả ở giai đoạn 1 |

**Thử driver trước khi nối vào BE:** chạy driver riêng trên máy với một Acunetix đang chạy và một máy nhận webhook giả (một server nhỏ in ra nội dung nhận được). Khi chạy ổn mới đóng gói và chạy trong pod giả.

**Cổng sang giai đoạn 3:** driver quét xong đích thử (T0.10) có đăng nhập và API, và máy nhận webhook giả nhận được kết quả đủ.

## 7. Giai đoạn 3: backend

BE giữ toàn bộ trạng thái; pod giả chỉ làm việc rồi gửi kết quả. Bắt đầu bằng hợp đồng API và ScanOptions (T3.1 đến T3.3) vì FE phụ thuộc vào đó. Ngôn ngữ và thư viện theo BE Deep Review hiện có.

| Task | Việc làm và kết quả |
| --- | --- |
| T3.1 | Mô hình dữ liệu: lượt quét (mã, dự án, engine, người tạo, trạng thái, mã lỗi, mục tiêu, thời điểm, băm token), cấu hình thường có phiên bản, kết quả. Kết quả: không có cột nào chứa secret |
| T3.2 | Lược đồ ScanOptions có phiên bản cho từng engine và API trả lược đồ đó cho FE. Kết quả: FE dựng được form mà không biết tên trường của Acunetix |
| T3.3 | API tạo lượt quét: nhận engine, ScanOptions và tệp tải lên; kiểm tra (trường lạ, kích thước, loại tệp, URL hợp lệ và nằm trong danh sách được phép, không có token trong URL); kiểm tra trần đồng thời; ghi DB trạng thái SCANNING; sinh token; gọi bộ khởi chạy; trả mã lượt. Lượt Acunetix thiếu URL bị từ chối |
| T3.4 | Tách ScanOptions thành phần thường (lưu DB) và phần bí mật (chuyển cho bộ khởi chạy rồi bỏ khỏi bộ nhớ). Kết quả: log và DB không có mật khẩu hay token |
| T3.5 | Giao diện bộ khởi chạy Job gồm launch, status, kill, cleanup và bản Docker (dùng thư viện Docker của ngôn ngữ BE hoặc gọi script T1.10); chọn bản bằng cấu hình. Kết quả: đổi sang bản OpenShift sau này không phải sửa luồng |
| T3.6 | API nhận webhook: so băm token, chỉ nhận khi lượt đang SCANNING, giới hạn kích thước nội dung, nhận hai lần không làm hỏng dữ liệu. Kết quả: token sai bị từ chối, không ghi log token |
| T3.7 | ReportParser cho Acunetix: đổi JSON mẫu (T0.7) sang UnifiedReport, ánh xạ mức nghiêm trọng, vị trí, mô tả. Kết quả: lỗi phân tích ra mã PARSE\_FAILED, không làm sập BE |
| T3.8 | Máy trạng thái SCANNING, PARSING, COMPLETED hoặc FAILED kèm mã lỗi, chuyển một chiều. Kết quả: trạng thái cuối do BE đặt sau khi phân tích, không dựa vào trạng thái container |
| T3.9 | API xem lượt quét (danh sách trả thêm engine và mục tiêu: nhánh với Fortify, URL với Acunetix; chi tiết có trạng thái, mã lỗi, cảnh báo độ phủ, kết quả) và API hủy (kill rồi dọn, đóng lượt). Kết quả: FE hiện chung một bảng lịch sử |
| T3.10 | Reconciler chạy mỗi phút: lượt SCANNING mà nhóm container đã mất thì đóng JOB\_LOST; driver thoát mã 50 thì CALLBACK\_LOST; quá hạn thì kill; dọn container và tệp tạm còn sót theo nhãn. Thời hạn chờ webhook phải lớn hơn tổng số lần thử lại của driver, nếu không sẽ đóng nhầm |
| T3.11 | Trần đồng thời bằng 1 theo cấu hình; vượt trần thì từ chối rõ ràng; đếm đúng khi lượt kết thúc hoặc bị dọn |
| T3.12 | Quyền: ai được tạo lượt quét Acunetix, ai được xem kết quả, theo quyền hiện có của Deep Review |
| T3.13 | Log có cấu trúc và đếm lượt theo trạng thái và mã lỗi. Kết quả: nhìn được lúc JOB\_LOST hoặc CALLBACK\_LOST tăng |
| T3.14 | Kiểm thử BE: kiểm tra ScanOptions, ReportParser bằng JSON mẫu, máy trạng thái, và trên bộ khởi chạy Docker với driver giả. Kết quả: chạy được không cần Acunetix thật |

**Hợp đồng cho FE:** sau T3.2 và T3.3, FE bắt đầu được, dùng BE giả để thử form và trạng thái, không cần chờ driver.

**Cổng sang giai đoạn 5:** T3.3 đến T3.10 chạy được với driver giả qua bộ khởi chạy Docker, rồi với driver thật.

## 8. Giai đoạn 4: frontend

FE sửa màn Scans của một dự án theo [mockup trang Scans](https://claude.ai/artifact/18PwybqnKizeNR5dhgP3Cw): thêm ô Engine cạnh ô Branch, chọn Acunetix thì bấm Scan mở ngăn kéo chứa form. FE không biết tên trường của Acunetix, chỉ dựng form theo lược đồ BE trả về. Bắt đầu được sau khi BE chốt T3.2 và T3.3, dùng BE giả để thử.

| Task | Việc làm và kết quả |
| --- | --- |
| T4.1 | Ô Engine cạnh ô Branch: Fortify và Acunetix chọn được, Burp Suite và Nessus hiện mờ “sắp có”, mặc định Fortify |
| T4.2 | Ô Branch bị vô hiệu hóa khi chọn Acunetix, kèm dòng giải thích: Acunetix quét ứng dụng đang chạy qua URL, không đọc mã nguồn trong Git |
| T4.3 | Nút Scan: Fortify tạo lượt quét ngay như cũ; Acunetix mở ngăn kéo, chưa tạo lượt quét cho tới khi bấm “Bắt đầu quét” |
| T4.4 | Ngăn kéo: đầu và chân cố định, thân cuộn; đóng bằng ✕, Hủy, phím Esc hoặc bấm ra ngoài; trả tiêu điểm bàn phím về nút Scan |
| T4.5 | Dựng form theo lược đồ T3.2: mục tiêu (URL bắt buộc), kiểu quét, đăng nhập, API và tệp nhập, header, đường dẫn loại trừ, nâng cao (thu gọn). Chọn chế độ đăng nhập rồi mới hiện các ô tương ứng |
| T4.6 | Ô bí mật (mật khẩu, giá trị header, token) dùng kiểu ẩn, không lưu localStorage hay URL, không hiển thị lại sau khi gửi |
| T4.7 | Tải tệp (chuỗi đăng nhập, định nghĩa API, kịch bản tiền xử lý): hiện giới hạn kích thước và loại tệp BE cho phép, gửi dạng multipart |
| T4.8 | Gửi form: kiểm tra nhẹ ở FE (URL bắt buộc), hiện lỗi BE theo từng ô; xử lý từ chối vì vượt trần đồng thời bằng thông báo dễ hiểu |
| T4.9 | Cảnh báo trên form: dùng tài khoản thử nghiệm, không bật CAPTCHA hay 2FA, chỉ quét môi trường thử nghiệm, token phải còn hạn suốt lượt quét |
| T4.10 | Bảng Scan history: thêm cột Engine, cột Branch đổi thành “Branch / Target”; Status và Progress dùng chung hai engine; tự làm mới định kỳ khi còn lượt đang chạy |
| T4.11 | Hiển thị trạng thái và mã lỗi bằng câu tiếng Việt kèm gợi ý việc cần làm (ví dụ “Đăng nhập thất bại, kiểm tra tài khoản”) |
| T4.12 | LOW\_COVERAGE và LOGIN\_FAILED hiển thị nổi, để kết quả “sạch” không trông như an toàn |
| T4.13 | Xem kết quả: dùng lại màn danh sách lỗi của Fortify trên UnifiedReport, hiển thị số đường dẫn thu thập được |
| T4.14 | Nút hủy lượt quét đang chạy, gọi API hủy T3.9 |

**Chưa làm ở đợt này:** nút “Kiểm tra đăng nhập” trước khi quét thật (cần biết Acunetix báo kết quả đăng nhập qua API như thế nào, T0.6), ô OAuth, lưu URL vào dự án để tự điền.

## 9. Giai đoạn 5: kiểm thử trên Docker

Kiểm thử đi từ nhỏ đến lớn, mỗi bước chỉ thêm một thứ mới để khi hỏng thì biết lỗi ở đâu. Chỉ quét đích thử ở T0.10.

| Test | Làm gì và đạt khi |
| --- | --- |
| T5.1 | Pod giả với driver giả: dựng đúng thứ tự, driver thoát, dọn sạch, không còn container hay tệp tạm |
| T5.2 | Driver thật với máy nhận webhook giả: nhận được kết quả đủ, so đúng số lỗi với giao diện Acunetix |
| T5.3 | BE thật với driver giả: nhận webhook, phân tích, lượt đổi sang COMPLETED và hiển thị trên FE |
| T5.4 | Toàn trình: FE, BE thật, driver thật, đích thử. Bấm bắt đầu quét đến khi thấy báo cáo, không mở giao diện Acunetix |
| T5.5 | Đích thử có đăng nhập và API: kết quả gồm phần sau đăng nhập và endpoint từ tệp API; số đường dẫn thu thập hợp lý |
| T5.6 | Giả lập lỗi: giết container giữa chừng ra JOB\_LOST; chặn đường tới BE ra CALLBACK\_LOST (driver thoát mã 50); token sai bị từ chối; webhook gửi hai lần không hỏng dữ liệu; tắt rồi bật lại BE giữa chừng thì Reconciler đóng đúng |
| T5.7 | Tình huống rủi ro của đích: đăng nhập sai ra LOGIN\_FAILED; có CAPTCHA ra MANUAL\_INTERVENTION hoặc cảnh báo; đích không trả lời hoặc vượt trần thời gian ra SCAN\_TIMEOUT. Không trường hợp nào báo “sạch” |
| T5.8 | Trần đồng thời: bấm quét hai lần liên tiếp thì lần hai bị từ chối rõ ràng; lượt đầu xong thì nhận lại được |
| T5.9 | Dọn dẹp sau nhiều lượt liên tiếp: không còn container, mạng, tệp tạm; ổ cứng không phình dần |
| T5.10 | Bảo mật: tìm mật khẩu và token trong log, DB, tên container và kết quả `docker inspect`; không được thấy ở đâu |
| T5.11 | Hồi quy: chọn Fortify thì luồng cũ vẫn chạy như trước |

**Quan sát để thấy lỗi sớm:** log driver có cấu trúc gắn mã lượt; BE đếm lượt theo trạng thái và mã lỗi, đo thời gian từ lúc tạo đến khi xong và số lần Reconciler phải đóng lượt; JOB\_LOST hay CALLBACK\_LOST tăng là dấu hiệu có vấn đề.

## 10. Thứ tự làm, tiêu chí hoàn thành và chuyển sang OpenShift

### 10.1 Thứ tự làm

1. **Giai đoạn 0 trước hết.** Nếu không khởi tạo và kích hoạt được Acunetix không qua giao diện thì phải đổi hướng (mục 4).
2. **Giai đoạn 1, rồi giai đoạn 2.** Dựng pod giả với driver giả, sau đó thay bằng driver thật chạy riêng trước khi đưa vào pod giả.
3. **Giai đoạn 3 (BE) và giai đoạn 4 (FE).** Chốt hợp đồng API và ScanOptions (T3.1 đến T3.3) trước; sau đó FE và phần còn lại của BE có thể làm song song, FE dùng BE giả.
4. **Giai đoạn 5.** Thử từng nấc theo thứ tự T5.1 đến T5.11.

### 10.2 Tiêu chí hoàn thành

- [ ] Một lượt quét tạo từ FE chạy xong, báo cáo hiện trong Deep Review, không ai mở giao diện Acunetix.
- [ ] Lượt quét có đăng nhập và API cho kết quả gồm cả phần sau đăng nhập và các endpoint từ tệp API.
- [ ] Mỗi mã lỗi (JOB\_LOST, CALLBACK\_LOST, PARSE\_FAILED, SCAN\_TIMEOUT, LOGIN\_FAILED, MANUAL\_INTERVENTION, LOW\_COVERAGE) được gây ra có chủ đích và hiện đúng.
- [ ] Sau mỗi lượt không còn container, mạng hay tệp tạm nào sót lại; lượt mất kết nối được Reconciler đóng.
- [ ] Vượt trần đồng thời bị từ chối rõ ràng.
- [ ] Mật khẩu, key và token không xuất hiện trong log, DB hay `docker inspect`.
- [ ] Chọn Fortify thì luồng cũ không đổi.

### 10.3 Khi có OpenShift

| Giữ nguyên | Phải làm thêm hoặc làm lại |
| --- | --- |
| FE, API BE, ScanOptions, máy trạng thái, webhook, ReportParser | Bản OpenShift của bộ khởi chạy: tạo Secret rồi Job thay cho nhóm container |
| Driver và cách đọc cấu hình | Đẩy image driver và Acunetix lên registry nội bộ, cố định theo digest (cần hỏi điều khoản licence) |
| Reconciler (đổi cách tìm Job theo nhãn) | Mẫu Job: sidecar gốc, tài nguyên, hạn, dọn tự động, nhãn |
| Bộ test T5.1 đến T5.11 | NetworkPolicy, SCC và UID, ResourceQuota, trần đồng thời theo hạn mức; thử lại các nấc liên quan trên cụm thật |

Chỉ được coi là xong trên OpenShift khi các nấc đó đã chạy lại trên cụm thật; chạy trên Docker chỉ chứng minh logic đúng, không chứng minh môi trường thật chạy được.
