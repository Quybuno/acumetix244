# Kế hoạch triển khai Acunetix vào Deep Review

Nov 18, 2026 · @Cuong Ruby

## 1. Mục tiêu và phạm vi

Đợt triển khai thử này cho người dùng chọn engine Acunetix trên Deep Review, điền form và nhận kết quả mà không phải mở giao diện Acunetix. Mỗi lượt quét chạy trong một Job OpenShift: driver gọi API Acunetix rồi gửi kết quả về qua webhook, giống cách Fortify đang chạy.

**Đã có sẵn:** image Acunetix, licence, một instance đang chạy bằng giao diện (dùng làm nơi khám phá API) và [mockup form](https://claude.ai/artifact/LJ1zD3zHZnZR3haix7Rncw).

**Trong phạm vi**

- FE: chọn engine, form cấu hình, trạng thái lượt quét, hiển thị kết quả.
- BE: API tạo lượt quét, ScanOptions, máy trạng thái, nhận webhook, ReportParser, Reconciler.
- Hạ tầng: image và registry, namespace, quyền, NetworkPolicy, Secret.
- Driver và mẫu Job.
- Kiểm thử, quan sát, bảo mật.

**Chưa làm ở đợt này**

- Hẹn giờ và quét định kỳ: Deep Review đảm nhiệm, Acunetix chỉ chạy kiểu chạy ngay.
- OAuth, Business Logic Recorder, AcuSensor, TOTP; đích có CAPTCHA hoặc OTP.
- Nhiều vai trò người dùng trong một lượt quét.
- Báo cáo PDF hoặc HTML của Acunetix: lấy dữ liệu lỗi dạng JSON qua API.
- Engine khác (Burp, Nessus): chỉ chừa chỗ cho adapter.

**Đợt thử thành công khi** một đích thử có đăng nhập và API được quét xong và kết quả hiện trên Deep Review, và ba tình huống lỗi (đăng nhập sai, mất webhook, pod chết) cho ra đúng mã lỗi thay vì báo “sạch”.

## 2. Kiến trúc tổng thể

&#91;embedded content: kiến trúc tổng thể · FE, BE, pod, driver\]

FE gửi form tới BE; BE tạo Secret và Job; trong pod chỉ driver nói chuyện với Acunetix qua địa chỉ nội bộ, rồi gửi kết quả về BE bằng webhook trước khi thoát.

## 3. Quyết định đã chốt và giả định đang dùng

Phần lớn thiết kế giữ nguyên như đã thảo luận; chỉ có hai điểm đổi sau khi có image thật: số image của hãng và cách tạo tài khoản admin.

| Quyết định đã chốt | Điều chỉnh sau khi có image thật |
| --- | --- |
| Một lượt quét là một Job, một pod. Các container Acunetix chạy dưới dạng sidecar gốc, driver là container chính duy nhất. Cụm từ Kubernetes 1.29 trở lên | Theo [tài liệu Docker của hãng](https://www.acunetix.com/support/docs/acunetix-on-docker-docker-compose-and-kubernetes/), bản Compose gồm Postgres, một container chính và một worker dùng chung image Acunetix. Vậy là ba container nhưng **hai image**, không phải ba. Cần xác nhận khi chạy thật |
| Chỉ driver gọi API Acunetix, qua địa chỉ nội bộ của pod | Giữ nguyên. Instance đang chạy của anh báo “Not secure” trên trình duyệt, nên chứng chỉ nhiều khả năng tự ký: driver cần cách xử lý riêng (mục 10) |
| Job không tự chạy lại | Giữ nguyên: quét lại tự động tốn licence và che lỗi thật |
| Kết quả lấy từ API danh sách lỗi dạng JSON, không đọc PDF hay HTML. Có ReportParser riêng ánh xạ về UnifiedReport | Giữ nguyên. Lược đồ JSON thật chốt sau giai đoạn 0 |
| Chỉ dùng kiểu quét chạy ngay; hẹn giờ và quét định kỳ do Deep Review đảm nhiệm | Giữ nguyên |
| Namespace riêng, chặn mọi luồng ra mặc định, chỉ mở đúng các đường cần. Allowlist URL của Deep Review là lớp một, NetworkPolicy là lớp hai | Giữ nguyên |
| Trần đồng thời bằng giá trị nhỏ hơn giữa suất licence và sức chứa quota; vượt thì từ chối, chưa xếp hàng đợi | Cần số instance licence cho phép và số đo tài nguyên một pod trước khi đặt trần |
| Token webhook ngẫu nhiên mỗi lượt, cơ sở dữ liệu chỉ lưu bản băm, Secret gắn ownerReference vào Job | Giữ nguyên. Secret phải được tạo trước pod |
| Lấy hết lỗi qua API và gửi đi trước khi pod thoát | Giữ nguyên: kết quả nằm trong cơ sở dữ liệu của pod và mất cùng pod |

**Giả định chưa xác minh, phải được kiểm chứng ở giai đoạn 0**

- Licence kích hoạt được trong pod mới. Hãng dùng khóa licence làm mật khẩu đăng nhập registry, trang tài liệu không mô tả bước kích hoạt nào khác; chưa biết licence cho chạy bao nhiêu instance cùng lúc.
- Tài khoản admin tạo qua hai biến môi trường của image, nhưng cách lấy khóa API mà không qua giao diện chưa biết.
- Image chạy được với UID ngẫu nhiên của OpenShift. Mẫu Compose của hãng đặt quyền thư mục dữ liệu cho một UID cố định, nên có thể phải xin quyền riêng cho pod quét.
- Webhook của lượt quét nhiều lỗi không bị route hoặc máy nhận cắt.

## 4. Giai đoạn 0: spike xác minh trên image và licence thật

Làm giai đoạn này trước mọi thứ khác, vì nó trả lời những câu hỏi quyết định thiết kế: licence có cho chạy mỗi pod một instance không, khởi tạo instance không qua giao diện thế nào, và API trả về gì. Phần khám phá API có thể làm ngay trên instance đang chạy.

| Bước | Làm gì | Đạt khi |
| --- | --- | --- |
| 0.1 | Kiểm tra phiên bản Kubernetes của cụm; chạy Job thử có sidecar chạy vô hạn, container chính thoát sớm | Job kết thúc khi container chính thoát. Không đạt thì phải đổi mô hình |
| 0.2 | Khám phá API trên instance đang chạy: mở DevTools (tab Network), lưu cấu hình Target cho mỗi nhóm ô (Target Information, Crawling, HTTP), rồi chép lại yêu cầu gửi đi | Biết tên trường API thật của từng ô trên form; có bản ánh xạ form sang API |
| 0.3 | Gọi thử toàn bộ luồng bằng `curl` trên một đích thử: xác thực, tạo Target, đặt cấu hình, nạp tệp, tạo lượt quét, hỏi trạng thái, lấy lỗi, xóa Target | Lưu được phản hồi thật của mỗi bước: lược đồ JSON của lỗi, các trạng thái, cách phân trang |
| 0.4 | Chạy thử image trên một máy có Docker với hai biến tài khoản, theo mẫu Compose của hãng (cơ sở dữ liệu, container chính, worker) | Vào được giao diện, biết licence được áp vào instance bằng cách nào, quét được một đích thử |
| 0.5 | Tìm cách lấy khóa API hoặc token mà không qua giao diện (gọi API đăng nhập bằng tài khoản admin) | Driver có đường tự động để có thông tin xác thực. Không đạt thì hỏi hãng |
| 0.6 | Đo: RAM và CPU của từng container, thời gian khởi động, thời gian quét đích nhỏ, kích thước danh sách lỗi dạng JSON | Có số liệu để đặt quota, trần đồng thời và giới hạn webhook |
| 0.7 | Quan sát lưu lượng ra của container khi quét và khi khởi động | Biết image thật sự gọi ra những đích nào, để chỉ mở đúng đích cần |
| 0.8 | Hỏi hãng hoặc đại lý: số instance đồng thời, được sao chép image sang registry nội bộ không, tính năng nào có trong phiên bản được cấp | Có câu trả lời bằng văn bản |
| 0.9 | Thử tạo báo cáo qua API khi bỏ trống mẫu | Biết có bắt buộc chọn mẫu không (chỉ cần nếu sau này cần PDF hoặc HTML) |

**Cổng quyết định sau giai đoạn 0.** Nếu licence không cho chạy nhiều instance, hoặc không có cách khởi tạo instance mà không qua giao diện, thì chuyển sang dùng một instance dùng chung. Lúc đó adapter ở BE giữ nguyên, chỉ đổi nơi Acunetix chạy.

## 5. Giai đoạn 1: image, registry và OpenShift

Phần lớn việc nặng ở đây là xin quyền và đặt giới hạn đúng, nên nên gửi yêu cầu cho admin ngay khi giai đoạn 0 cho kết quả số đo. Các việc dưới đây có thể chạy song song với giai đoạn 3 và 4.

| Việc | Ai làm | Đạt khi | Phụ thuộc |
| --- | --- | --- | --- |
| Namespace riêng cho Acunetix, có ResourceQuota | Admin | Pod không khai yêu cầu tài nguyên bị từ chối; tổng quota bằng tài nguyên một pod nhân số lượt đồng thời, cộng phần dư | Số đo RAM và CPU (bước 0.6) |
| ServiceAccount và Role cho thành phần tạo Job, chỉ trong namespace này: tạo, xem, xoá Job; tạo, xem, vá, xoá Secret; xem pod và đọc log | Admin hoặc nhóm Deep Review | Quyền đã cấp trả lời “được”; tạo pod trực tiếp và đọc Secret namespace khác trả lời “không” | Namespace không chứa bí mật nào khác ngoài của các lượt quét |
| Registry nội bộ chứa hai image (Acunetix và Postgres), tham chiếu theo digest | Admin và nhóm Deep Review | Digest khớp bản gốc; pod thử kéo được cả hai | Hãng cho phép sao chép image (bước 0.8). Nếu chưa được, pod phải kéo từ registry của hãng bằng pull secret dùng khóa licence |
| Pull secret chỉ có quyền đọc, gắn vào ServiceAccount của pod | Admin | Không còn lỗi xác thực khi kéo image | Registry nội bộ |
| NetworkPolicy chặn mặc định mọi luồng ra; mở DNS, webhook về Deep Review và đích quét | Admin | Pod thử gửi được webhook và phân giải được tên miền, nhưng không ra được internet hay máy ngoài danh sách | Mở thêm tới licence và AcuMonitor (`bxss.me`) là quyết định cần duyệt (mục 10); danh sách đích thật từ bước 0.7 |
| UID và SCC: thử UID ngẫu nhiên của OpenShift trước; nếu image không chạy được thì xin SCC riêng cho ServiceAccount của pod quét | Admin | Container cơ sở dữ liệu ghi được thư mục dữ liệu; không mở quyền cho cả namespace | UID mà từng image mong đợi |
| Nới giới hạn kích thước request ở route của OpenShift và ở nơi nhận webhook | Admin và nhóm Deep Review | Webhook có nhiều lỗi không bị cắt | Kích thước thật từ bước 0.6 |
| Nạp trước image lên các node (tuỳ chọn) | Admin | Lượt quét đầu trên node không chậm hẳn | Chỉ làm nếu lần kéo image đầu gây phiền |

**Việc đầu tiên với image:** kéo từ registry của hãng (đăng nhập bằng email Acunetix và khóa licence), chạy thử đúng bản đang dùng, rồi ghi lại digest để cố định. Đừng dùng image chụp từ instance đã kích hoạt, vì nó mang theo licence và dữ liệu quét cũ.

## 6. Giai đoạn 2: driver và mẫu Job

Driver là phần do nhóm tự viết. Nên bắt đầu từ khung driver của Fortify (gửi webhook, thử lại, ghi log, đọc Secret) và chỉ thay phần gọi engine, để thêm engine mới sau này chỉ cần thêm driver.

### Đầu vào của driver

- **Từ Secret của lượt quét:** ScanOptions đã kiểm tra, token webhook, tài khoản admin của instance, licence, thông tin đăng nhập vào đích, giá trị các header tùy chỉnh.
- **Từ tệp được gắn vào pod:** chuỗi đăng nhập (.lsr), tệp định nghĩa API, kịch bản tiền xử lý (.js).
- **Mã lượt quét** và địa chỉ webhook, để gửi kết quả về đúng lượt.

### Driver làm gì, theo thứ tự

1. Chờ API sẵn sàng bằng cách hỏi lặp lại, không dựa vào thứ tự khởi động của sidecar.
2. Lấy thông tin xác thực API của instance (cách làm chốt ở bước 0.5).
3. Tạo Target và đặt cấu hình theo ScanOptions: hồ sơ quét theo preset, đăng nhập, header, đường dẫn loại trừ, giới hạn thu thập.
4. Nạp tệp nhập và định nghĩa API.
5. Tạo lượt quét kiểu chạy ngay.
6. Hỏi trạng thái định kỳ đến khi xong; quá trần thời gian thì báo `SCAN_TIMEOUT`.
7. Kiểm tra sau quét: đăng nhập có thành công không (`LOGIN_FAILED`), có dừng chờ người không (`MANUAL_INTERVENTION`), số đường dẫn thu thập được có thấp bất thường không (`LOW_COVERAGE`). Trạng thái Completed của Acunetix không đủ để kết luận thành công.
8. Lấy hết danh sách lỗi qua API (phân trang) kèm số liệu thu thập.
9. Dọn Target.
10. Gửi webhook kèm token, thử lại khi lỗi mạng; hết số lần thử thì thoát với mã thoát riêng (50) để Reconciler nhận ra.
11. Thoát; các sidecar tự dừng và pod kết thúc.

Bước 8 phải xong trước bước 11, vì kết quả nằm trong cơ sở dữ liệu của pod và mất cùng pod.

### Mẫu Job (mô tả, giá trị cụ thể chốt sau khi đo)

| Thuộc tính | Cách đặt |
| --- | --- |
| Thử lại | Không tự chạy lại khi pod lỗi; pod chết giữa chừng thì Job chuyển sang thất bại |
| Thời hạn | Giới hạn tổng thời gian của Job dài hơn trần chờ của driver, để driver tự báo lỗi trước khi OpenShift dừng pod. Cả hai suy ra từ trần thời gian người dùng chọn |
| Dọn dẹp | Job, pod và Secret tự xóa sau một khoảng giữ đủ dài để đọc log khi có lỗi |
| Container | Ba container Acunetix khai như sidecar gốc, theo thứ tự cơ sở dữ liệu, máy chủ chính, worker; driver là container chính duy nhất |
| Tài nguyên | Khai yêu cầu và giới hạn cho mọi container, vì namespace có hạn mức; mức cụ thể từ số đo bước 0.6 |
| Secret | Mỗi lượt quét một Secret, gắn ownerReference vào Job, chỉ gắn vào driver; phải tạo trước pod |
| Nhãn | Đánh nhãn mã lượt quét lên Job và pod để Reconciler tìm được |
| Mạng | Chịu NetworkPolicy của namespace, không tự mở thêm đường ra |
| ServiceAccount | Pull secret và (nếu cần) SCC riêng cho pod quét |

**Thử driver trước khi gắn vào BE.** Chạy driver riêng trên máy phát triển với một Acunetix chạy sẵn và một máy nhận webhook giả; khi ổn mới đóng gói thành image và chạy trong Job.

## 7. Giai đoạn 3: backend

BE là nơi giữ toàn bộ trạng thái. Pod chỉ làm việc rồi gửi kết quả, nên mọi thứ BE không nhận được phải được Reconciler phát hiện và đóng lại. Bắt đầu bằng hợp đồng API và ScanOptions, vì FE phụ thuộc vào chúng.

### 7.1 API và ScanOptions

| API | Việc |
| --- | --- |
| Tạo lượt quét | Nhận engine, ScanOptions và các tệp tải lên; kiểm tra; kiểm tra trần đồng thời; tạo Secret rồi Job; trả mã lượt quét |
| Mô tả form | Trả lược đồ của ScanOptions cho từng engine để FE dựng form theo lược đồ |
| Xem lượt quét | Trạng thái, mã lỗi, cảnh báo độ phủ, kết quả |
| Nhận webhook | Xác thực token, nhận kết quả từ driver |
| Hủy lượt quét | Xóa Job, đóng lượt quét |

- **ScanOptions có phiên bản.** Trường lấy từ form ở mockup: URL, mô tả, preset, chế độ đăng nhập, tệp nhập, header, đường dẫn loại trừ, và nhóm nâng cao. Tên trường của Acunetix chỉ nằm trong adapter.
- **Kiểm tra ở BE, không tin FE.** Từ chối trường lạ, giới hạn kích thước và loại tệp, không ghi mật khẩu hay token vào log.
- **Preset do cấu hình hệ thống định nghĩa**, không viết cứng trong mã: preset “quét sâu” ánh xạ sang hồ sơ Full Scan kèm đường dẫn loại trừ mặc định và thời lượng dài; “quét nhanh” ánh xạ sang hồ sơ chỉ tìm lỗi mức cao.
- **Adapter theo engine.** Mỗi engine có một adapter tạo Job và một ReportParser; Fortify và Acunetix dùng chung máy trạng thái.

### 7.2 Máy trạng thái và webhook

Một lượt quét đi từ `SCANNING` sang `PARSING`, rồi `COMPLETED` hoặc `FAILED` kèm một mã lỗi. Vượt trần đồng thời thì từ chối ngay khi tạo, chưa xếp hàng đợi.

- Token webhook ngẫu nhiên mỗi lượt; cơ sở dữ liệu chỉ lưu bản băm. So sánh bản băm khi nhận.
- Webhook phải an toàn khi nhận nhiều lần (driver thử lại): lần đầu được nhận, các lần sau trả thành công nhưng không xử lý lại.
- Nhận xong chuyển sang `PARSING`, gọi ReportParser; không phân tích được thì đóng với `PARSE_FAILED`.
- Nới giới hạn kích thước request ở nơi nhận webhook theo số đo thật.

### 7.3 ReportParser cho Acunetix

Ánh xạ danh sách lỗi JSON về UnifiedReport. Dữ liệu mỗi lỗi gồm tên, mức nghiêm trọng (năm mức), CWE, CVE và điểm CVSS nếu có, tham số bị tấn công, cặp yêu cầu và phản hồi HTTP, mô tả và hướng khắc phục. Tên trường thật và cách ánh xạ mức nghiêm trọng chốt sau bước 0.3. Phần số đường dẫn thu thập và cảnh báo độ phủ được lưu cùng kết quả.

### 7.4 Mã lỗi

| Mã | Khi nào | Ai phát hiện |
| --- | --- | --- |
| `JOB_LOST` | Job biến mất hoặc kết thúc thất bại mà không có webhook | Reconciler |
| `CALLBACK_LOST` | Job kết thúc bình thường nhưng webhook không tới, kể cả khi driver thoát với mã 50 | Reconciler |
| `PARSE_FAILED` | Webhook tới nhưng không phân tích được dữ liệu lỗi | Máy nhận webhook |
| `SCAN_TIMEOUT` | Lượt quét vượt trần thời gian | Driver |
| `LOGIN_FAILED` | Đăng nhập vào đích thất bại dù Acunetix báo Completed | Driver |
| `MANUAL_INTERVENTION` | Lượt quét dừng chờ người (CAPTCHA, OTP) | Driver |
| `LOW_COVERAGE` | Số URL thu thập được thấp bất thường, kết quả “sạch” không đáng tin | Driver |

Bốn mã cuối là đề xuất, chưa được duyệt; `LOW_COVERAGE` chưa có ngưỡng thế nào là “thấp”, cần chọn sau khi có số đo thật.

### 7.5 Reconciler

Reconciler chạy mỗi phút và làm ba việc:

1. Tìm lượt đang `SCANNING` mà Job đã mất hoặc đã Failed, đóng với `JOB_LOST`.
2. Tìm lượt có Job đã kết thúc nhưng quá thời hạn chờ mà chưa có webhook, đóng với `CALLBACK_LOST`.
3. Dọn Job và Secret còn sót.

Thời hạn chờ webhook phải lớn hơn tổng số lần thử lại của driver, nếu không Reconciler sẽ đóng nhầm lượt đang gửi.

## 8. Giai đoạn 4: frontend

FE chỉ làm ba việc: cho chọn engine, dựng form theo lược đồ BE trả về, và hiển thị trạng thái cùng kết quả. FE không biết tên trường của Acunetix. Giao diện mẫu nằm ở [mockup form](https://claude.ai/artifact/LJ1zD3zHZnZR3haix7Rncw).

| Việc | Ghi chú |
| --- | --- |
| Chọn engine trên màn tạo lượt quét | Fortify và Acunetix hoạt động; engine khác hiện ở dạng chưa bật |
| Dựng form theo lược đồ | Mỗi engine một lược đồ; thêm ô cho Acunetix chỉ sửa BE |
| Nhóm ô của form | Mục tiêu, kiểu quét (preset), đăng nhập, API và tệp nhập, header, đường dẫn loại trừ, nâng cao (thu gọn) |
| Hiện ô theo chế độ | Chọn chế độ đăng nhập rồi mới hiện các ô tương ứng; mật khẩu và giá trị header là ô bí mật, không hiển thị lại sau khi gửi |
| Tải tệp | Chuỗi đăng nhập, định nghĩa API, kịch bản tiền xử lý; hiện giới hạn kích thước và loại tệp BE cho phép |
| Cảnh báo trên form | Dùng tài khoản thử nghiệm, không bật CAPTCHA hay 2FA; chỉ quét môi trường thử nghiệm; token phải còn hạn suốt lượt quét |
| Trạng thái lượt quét | Hiển thị `SCANNING`, `PARSING`, `COMPLETED`, `FAILED` và mã lỗi bằng câu tiếng Việt dễ hiểu, kèm gợi ý việc cần làm (ví dụ “Đăng nhập thất bại, kiểm tra tài khoản”) |
| Cảnh báo độ phủ | `LOW_COVERAGE` và `LOGIN_FAILED` hiển thị nổi, không để kết quả “sạch” trông như an toàn |
| Xem kết quả | Dùng lại màn hình danh sách lỗi của Fortify trên UnifiedReport; hiển thị số đường dẫn thu thập được |
| Quyền | Ai được tạo lượt quét Acunetix, ai được xem kết quả, theo quyền hiện có của Deep Review |

**Chưa làm ở đợt này:** nút “kiểm tra đăng nhập” trước khi quét thật (cần biết Acunetix báo kết quả đăng nhập qua API như thế nào, bước 0.3), ô OAuth, tải tệp BLR.

**Thứ tự làm.** FE bắt đầu được ngay khi BE chốt lược đồ ScanOptions và hợp đồng API (mục 7.1), không cần chờ driver chạy được; dùng BE giả để thử form và trạng thái trước.

## 9. Giai đoạn 5: kiểm thử, quan sát, bảo mật

Kiểm thử đi từ nhỏ đến lớn, mỗi nấc chỉ thêm một thứ mới để khi hỏng thì biết lỗi ở đâu. Các nấc này nối tiếp giai đoạn 0.

### 9.1 Bậc kiểm thử

| Nấc | Làm gì | Đạt khi |
| --- | --- | --- |
| 1 | Ba container Acunetix trong một pod trên OpenShift, container chính là lệnh chờ | Sidecar lên đúng thứ tự, gọi được API qua địa chỉ nội bộ pod, pod kết thúc khi container chính thoát |
| 2 | Driver thật chạy cả chuỗi tới webhook, đích thử đơn giản, máy nhận webhook giả | Nhận được kết quả đủ |
| 3 | Giả lập lỗi: chặn mạng, giết pod, token sai | Mỗi tình huống ra đúng mã lỗi ở mục 7.4 |
| 4 | BE thật nhận webhook và phân tích thành UnifiedReport | Lỗi hiển thị trên màn hình kết quả |
| 5 | Đích thử có đăng nhập và API: quét qua form trên FE | Kết quả gồm cả phần sau đăng nhập và endpoint từ tệp API; số đường dẫn thu thập hợp lý |
| 6 | Ép tình huống rủi ro: đăng nhập sai, có CAPTCHA, đích không trả lời, vượt trần thời gian, bật và chặn `bxss.me` | Deep Review báo lỗi hoặc cảnh báo đúng, không báo “sạch” |
| 7 | Bật NetworkPolicy chặn mặc định thật | Chỉ mở đúng DNS, webhook, đích quét và các đích được duyệt; lượt quét vẫn chạy |
| 8 | Nhiều lượt quét cùng lúc tới trần đồng thời | Lượt vượt trần bị từ chối rõ ràng; Job và Secret được dọn sau khi xong |

**Đích thử cần có** đăng nhập đơn giản, API có định nghĩa, một đường dẫn đăng xuất, một trang bật CAPTCHA (cho nấc 6), và khả năng tắt phản hồi để mô phỏng đích không trả lời. Chỉ quét môi trường thử nghiệm.

### 9.2 Quan sát

- Driver ghi log có cấu trúc ra đầu ra chuẩn, gắn mã lượt quét; giữ TTL của pod đủ dài để đọc khi lỗi.
- BE đếm số lượt quét theo trạng thái và mã lỗi, đo thời gian từ lúc tạo đến khi xong, và số lần Reconciler phải đóng lượt.
- Cảnh báo khi `JOB_LOST` hoặc `CALLBACK_LOST` tăng, vì đó là dấu hiệu hạ tầng hoặc mạng có vấn đề.
- Theo dõi số lượt đang chạy so với trần đồng thời.

### 9.3 Bảo mật

- **Secret của lượt quét** chỉ driver đọc, không ghi ra log, mất cùng Job.
- **Token webhook** ngẫu nhiên mỗi lượt, DB chỉ lưu bản băm.
- **Mật khẩu đích quét** không lưu lâu: chỉ nằm trong Secret và trong instance của pod, mất cùng pod.
- **Chứng chỉ tự ký của Acunetix:** driver gọi API qua địa chỉ nội bộ pod. Tắt kiểm tra chứng chỉ trái quy định R-08, nên cần xin ngoại lệ (lưu lượng không rời pod); cách sạch hơn là cho driver tin riêng đúng chứng chỉ đó nếu lấy được.
- **Lớp chặn URL:** allowlist URL của Deep Review là lớp một, NetworkPolicy là lớp hai.
- **Ra Internet:** mở `bxss.me` cho AcuMonitor nghiệp là dữ liệu kiểm tra đi qua dịch vụ của hãng, nên cần bộ phận bảo mật duyệt; nếu không mở thì kết quả phải ghi rõ nhóm lỗi bị bỏ qua.

## 10. Rủi ro và câu hỏi mở

Phần lớn rủi ro nằm ở những điều chưa kiểm chứng được cho tới khi chạy thật. Các dòng đầu quyết định hướng đi, nên làm trước trong giai đoạn 0.

### 10.1 Rủi ro

| Rủi ro | Cách giảm | Chủ |
| --- | --- | --- |
| Licence tính theo instance hoặc theo số pod chạy đồng thời, mỗi pod một instance có thể vượt giới hạn | Hỏi hãng và người cấp licence trước; đặt trần đồng thời theo số instance được phép; nếu không đủ thì chuyển sang một instance dùng chung (phương án dự phòng ở mục 4) | Cường, người giữ licence |
| Khởi tạo instance không qua giao diện: kích hoạt licence và lấy API key khi chưa có người bấm | Thử ở giai đoạn 0; tra tài liệu API và hỏi hãng; ghi lại chuỗi lệnh chạy được | Cường |
| Điều khoản cho phép sao chép image vào registry nội bộ | Đọc điều khoản licence; hỏi hãng; nếu không được thì kéo từ registry hãng qua tài khoản được cấp | Người giữ licence, quản trị registry |
| UID/SCC của OpenShift không khớp UID 9900 của image | Thử ở giai đoạn 1; xin SCC phù hợp hoặc chỉnh quyền thư mục dữ liệu | Quản trị OpenShift |
| Kích thước kết quả vượt giới hạn webhook | Đo ở giai đoạn 0 với đích lớn; nếu vượt thì driver nén hoặc tách lô, hoặc gửi bản tóm tắt kèm đường dẫn lấy phần còn lại | Cường |
| Lưu lượng AcuMonitor ra `bxss.me` bị chặn mặc định | Xin bộ phận bảo mật duyệt; nếu không mở thì ghi rõ trong kết quả nhóm lỗi bị bỏ qua | Bảo mật |
| Tắt kiểm tra chứng chỉ trên địa chỉ nội bộ pod trái R-08; API key lộ trong danh sách tiến trình | Xin ngoại lệ có ghi lý do; driver truyền key qua tệp hoặc biến môi trường, không qua tham số dòng lệnh | Cường, bảo mật |
| Token webhook hết hạn trước khi lượt quét xong | Hạn token = hạn tối đa của Job cộng một biên an toàn | Cường |
| Đích quét có WAF hoặc chỉ cho IP nguồn xác định, quét bị chặn giữa chừng | Đăng ký IP nguồn của cụm với chủ đích; lượt bị chặn ra mã `LOW_COVERAGE` thay vì báo sạch | Người đăng ký lượt quét |
| Pod kết thúc “Completed” nhưng kết quả sai hoặc thiếu | Trạng thái cuối chỉ do BE đặt sau khi nhận và phân tích webhook, không dựa vào trạng thái Job | Cường |
| Hết quota hoặc không đủ tài nguyên khi nhiều lượt quét chạy cùng lúc | Trần đồng thời nhỏ hơn hoặc bằng năng lực quota; từ chối ngay, không xếp hàng | Cường, quản trị OpenShift |

### 10.2 Câu hỏi cần hỏi

- **Hãng hoặc người giữ licence:** số instance được chạy đồng thời; kích hoạt khi khởi động tự động có được không; có được sao chép image sang registry nội bộ không.
- **Quản trị OpenShift:** phiên bản Kubernetes có hỗ trợ sidecar gốc (từ 1.29) không; SCC nào cho phép UID của image; quota cấp cho namespace.
- **Bảo mật:** có duyệt ngoại lệ R-08 và đường ra `bxss.me` không; danh sách đích được phép quét.
- **Chủ Deep Review:** hạn tối đa một lượt quét; ai được tạo lượt quét; giữ kết quả bao lâu.

## 11. Thứ tự thực hiện, mốc và tiêu chí hoàn thành

&#91;embedded content: lộ trình · P0 đến P5, cổng G0 đến G3\]

Làm P0 trước; chỉ khi G0 qua mới triển khai P1 đến P4, rồi P5 khép lại. Nếu G0 không qua thì đổi sang một instance dùng chung (mục 4).

### 11.1 Tiêu chí hoàn thành

- Một lượt quét tạo từ FE chạy xong và kết quả hiện trong Deep Review, không ai phải thao tác trong giao diện Acunetix.
- Lượt quét có đăng nhập và API cho kết quả gồm cả phần sau đăng nhập và các endpoint từ tệp API.
- Mỗi lỗi ở mục 7.4 có thể gây ra có chủ đích và hiện đúng mã.
- Pod, Job và Secret được dọn sau khi xong; lượt mất kết nối được Reconciler đóng.
- Vượt trần đồng thời bị từ chối rõ ràng.
- Mật khẩu, key và token không xuất hiện trong log.
- Các câu hỏi ở mục 10.2 đã có trả lời bằng văn bản; ngoại lệ R-08 và đường ra `bxss.me` đã có quyết định.
