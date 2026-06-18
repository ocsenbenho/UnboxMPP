# PROMPT CHO ANTIGRAVITY — MPP to Excel/PDF Converter Tool

> Copy toàn bộ nội dung dưới đây vào Antigravity (agent task) để build tool.

---

## CONTEXT

Tôi là Project Manager trong ngân hàng (HDBank), quản lý các dự án triển khai dùng MS Project (.mpp). Tôi cần một tool Python chạy local (không cần internet, không cần license trả phí) để:
1. Đọc file .mpp
2. Xuất ra Excel (.xlsx) hoặc PDF, tùy người dùng chọn
3. Chạy trên Windows/Macbook của công ty, không cần cài Microsoft Project

## MỤC TIÊU

Build một CLI tool Python tên `mpp-convert` có khả năng:

```bash
mpp-convert input.mpp --format excel --output report.xlsx
mpp-convert input.mpp --format pdf --output report.pdf
mpp-convert input.mpp --format both --output-dir ./out/
```

## YÊU CẦU KỸ THUẬT (BẮT BUỘC)

### 1. Đọc file .mpp
- Dùng thư viện **MPXJ** (open source, https://www.mpxj.org/) qua Python wrapper (`pip install mpxj`). MPXJ chạy trên JVM nên cần kiểm tra Java đã cài chưa, và in hướng dẫn cài nếu thiếu.
- KHÔNG dùng Aspose.Tasks hoặc bất kỳ thư viện có phí/cần license.
- Trích xuất tối thiểu các trường sau cho mỗi Task: id, name, outline_level (độ sâu WBS), start, finish, duration, percent_complete, predecessors (danh sách ID), is_milestone, is_summary.
- Trích xuất Resource: id, name, type.
- Trích xuất Assignment: task_id, resource_id, units (% phân bổ).
- Trích xuất Project info: name, start_date, finish_date.

### 2. Data Model (lớp trung gian)
Tạo dataclass Python độc lập (KHÔNG phụ thuộc trực tiếp object của MPXJ ở các lớp xuất file), gồm: `Task`, `Resource`, `Assignment`, `ProjectData`. Lý do: để sau này dễ thêm exporter mới (CSV, JSON, Google Sheets) mà không phải sửa lại logic đọc file.

### 3. Module xuất Excel (`excel_exporter.py`)
Dùng `openpyxl`. Yêu cầu:
- Sheet 1 "Task List": bảng task với cột Name (indent theo outline_level), Start, Finish, Duration, % Complete, Predecessors. Format header có màu nền, freeze row đầu, auto-width cột.
- Sheet 2 "Gantt Chart": vẽ Gantt đơn giản bằng conditional formatting hoặc tô màu cell theo timeline (mỗi cột = 1 ngày/tuần, tô màu thanh ngang theo task start-finish). Task summary in đậm.
- Sheet 3 "Resources" (optional, chỉ tạo nếu có resource data): bảng resource + assignment.
- Milestone hiển thị icon hoặc highlight riêng (ví dụ nền vàng).

### 4. Module xuất PDF (`pdf_exporter.py`)
Dùng `reportlab`. Yêu cầu:
- Trang 1: thông tin tổng quan project (tên, ngày bắt đầu/kết thúc, tổng số task).
- Các trang tiếp: bảng task list dạng report (tự động ngắt trang, có header lặp lại mỗi trang).
- Gantt chart visual: vẽ bằng `reportlab.graphics` hoặc xuất matplotlib rồi chèn ảnh vào PDF — chọn cách nào đơn giản, ổn định hơn.
- Khổ A4, có header (tên project) và footer (số trang) trên mỗi trang.

### 5. CLI (`main.py`)
Dùng `argparse` hoặc `click`. Tham số:
- `input` (positional, bắt buộc): đường dẫn file .mpp
- `--format {excel,pdf,both}` (bắt buộc)
- `--output` : đường dẫn file output (khi format=excel hoặc pdf)
- `--output-dir`: thư mục output (khi format=both)
- `--verbose`: in log chi tiết quá trình đọc/convert

### 6. Validation & Error Handling
- Kiểm tra file input tồn tại, đúng đuôi .mpp.
- Bắt lỗi nếu Java/MPXJ không khả dụng → in hướng dẫn cài đặt rõ ràng (link, command).
- Bắt lỗi file .mpp bị corrupt hoặc password-protected → thông báo rõ, không crash im lặng.
- Log ra số lượng task/resource đọc được trước khi xuất file, để người dùng verify nhanh.

### 7. Testing
- Viết unit test cho data model (mock dữ liệu, không cần file .mpp thật) để verify logic format Gantt, format Excel.
- Viết integration test với 1 file .mpp mẫu nhỏ (tạo bằng ProjectLibre nếu cần, hoặc tìm sample online) để verify full pipeline đọc → xuất Excel/PDF không lỗi.

## CẤU TRÚC THƯ MỤC BẮT BUỘC

```
mpp_converter/
├── main.py
├── config.py
├── core/
│   ├── __init__.py
│   ├── mpp_reader.py
│   ├── data_model.py
│   └── validator.py
├── exporters/
│   ├── __init__.py
│   ├── base_exporter.py
│   ├── excel_exporter.py
│   └── pdf_exporter.py
├── tests/
│   ├── test_mpp_reader.py
│   ├── test_excel_exporter.py
│   └── sample_files/
├── requirements.txt
└── README.md
```

## ACCEPTANCE CRITERIA (Definition of Done)

- [ ] `pip install -r requirements.txt` chạy thành công trên môi trường sạch (Python 3.10+, Windows)
- [ ] `python main.py sample.mpp --format excel --output test.xlsx` tạo ra file Excel mở được, có đủ 2-3 sheet như spec
- [ ] `python main.py sample.mpp --format pdf --output test.pdf` tạo ra file PDF mở được, có Gantt visual
- [ ] Tool báo lỗi rõ ràng (không traceback khó hiểu) khi: file không tồn tại, sai định dạng, Java chưa cài
- [ ] README.md có hướng dẫn cài đặt (bao gồm cài Java cho MPXJ) và 3 ví dụ lệnh sử dụng
- [ ] Toàn bộ code có docstring, comment tiếng Anh (theo convention code chuẩn), KHÔNG hardcode đường dẫn

## RÀNG BUỘC QUAN TRỌNG

- KHÔNG dùng thư viện có phí (Aspose, hoặc tương tự)
- KHÔNG cần kết nối internet khi chạy convert (chỉ cần internet lúc `pip install`)
- Code phải chạy được trên Windows (môi trường công ty banking, không có quyền admin để cài phần mềm ngoài Python + Java JRE)
- Giữ tool ở dạng CLI thuần, KHÔNG cần GUI ở phiên bản đầu (có thể để file `gui/app.py` rỗng làm placeholder cho phase 2)

## THỨ TỰ TRIỂN KHAI ĐỀ XUẤT (để Antigravity làm theo từng bước, dễ review)

1. Setup project structure + requirements.txt + kiểm tra MPXJ đọc được 1 file .mpp mẫu, in ra raw task list (chưa cần format đẹp)
2. Implement `data_model.py` + `mpp_reader.py` hoàn chỉnh, có unit test
3. Implement `excel_exporter.py` (Sheet 1 Task List trước, sau đó Gantt, sau đó Resources)
4. Implement `pdf_exporter.py` (bảng task trước, sau đó Gantt visual)
5. Implement `main.py` CLI nối toàn bộ pipeline
6. Viết `validator.py` + xử lý lỗi cho toàn bộ pipeline
7. Viết README.md + test integration cuối cùng

Sau mỗi bước, dừng lại để tôi review trước khi sang bước tiếp theo.
