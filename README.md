# UnboxMPP

Công cụ CLI và GUI chạy trên local (được viết bằng Python) để chuyển đổi file Microsoft Project (`.mpp`) sang định dạng Excel (`.xlsx`) hoặc báo cáo PDF (`.pdf`). Công cụ hoạt động độc lập mà không cần cài đặt phần mềm Microsoft Project hay sử dụng license trả phí.
<img width="2188" height="1552" alt="image" src="https://github.com/user-attachments/assets/a6653a9a-9c5f-4511-bf78-5afa0cd90e6c" />



## 🌟 Tính năng nổi bật

- **Giao diện trực quan (GUI)**: Hỗ trợ kéo-thả file, xem trước dữ liệu, hiển thị biểu đồ Gantt tương tác trước khi xuất file.
- **Tự động cấu hình**: Tự động kiểm tra và cấu hình môi trường Java JRE/JDK trên macOS và Windows.
- **Trích xuất dữ liệu chi tiết**: Đọc toàn bộ thông tin dự án `.mpp` thông qua MPXJ, bao gồm: Tasks, Resources, Assignments, Predecessors.
- **Xuất Excel (.xlsx)**:
  - Danh sách Task có cấu trúc phân cấp (thụt lề theo WBS).
  - Tự động định dạng: Milestone, Summary Tasks.
  - Tô màu thông minh và conditional formatting (Ví dụ: Các công việc thuộc đường găng - Critical Path).
- **Xuất báo cáo PDF (.pdf)**:
  - Trang báo cáo tổng quan dự án.
  - Bảng danh sách Task tự động ngắt trang, lặp lại tiêu đề.
  - Tích hợp biểu đồ Gantt trực quan.

---

## 🛠 Yêu cầu hệ thống & Cài đặt

### 1. Cài đặt Java JRE/JDK (Bắt buộc)
Lõi đọc file `.mpp` (MPXJ) chạy trên máy ảo Java (JVM), do đó máy của bạn cần có Java.

- **macOS**: Cài đặt OpenJDK thông qua Homebrew:
  ```bash
  brew install openjdk
  ```
  *(Lưu ý: Tool đã được cấu hình tự động tìm đường dẫn của Homebrew OpenJDK tại `/opt/homebrew/opt/openjdk` làm `JAVA_HOME` nếu bạn chưa cài đặt biến môi trường này).*
- **Windows**: Tải bản JRE 8+ tại [Adoptium](https://adoptium.net/) (chọn bản dành cho Windows x64) và cài đặt.
- **Kiểm tra Java**:
  ```bash
  java -version
  ```

### 2. Thiết lập môi trường Python & Cài đặt Dependencies
Dự án yêu cầu **Python 3.9+**. Khuyến khích sử dụng Virtual Environment (môi trường ảo).

```bash
# Clone repository
git clone https://github.com/ocsenbenho/UnboxMPP.git
cd UnboxMPP

# Tạo venv
python3 -m venv .venv

# Kích hoạt venv
# Trên macOS/Linux:
source .venv/bin/activate
# Trên Windows:
.venv\Scripts\activate

# Cài đặt thư viện cần thiết
pip install -r requirements.txt
```

---

## 📖 Hướng dẫn sử dụng

Công cụ cung cấp 2 chế độ: **Giao diện đồ họa (GUI)** và **Giao diện dòng lệnh (CLI)**.

> [!IMPORTANT]
> **Lưu ý quan trọng**: Trước khi khởi chạy ứng dụng bằng bất kỳ lệnh nào (dù là GUI hay CLI), hãy chắc chắn rằng bạn đã kích hoạt môi trường ảo (Virtual Environment) trong Terminal:
> - **macOS/Linux**: `source .venv/bin/activate`
> - **Windows**: `.venv\Scripts\activate`

### Cách 1: Sử dụng Giao diện đồ họa (GUI) - Khuyên dùng

Nếu bạn muốn có một trải nghiệm trực quan, dễ dàng xem trước và kiểm tra thông tin dự án trước khi xuất file. Bạn có thể mở giao diện bằng hình thức gọi lệnh trong Terminal/Command Prompt như sau:

**Khởi chạy ứng dụng:**
```bash
python gui/app.py
```

**Thao tác sử dụng:**
1. Ở phần **① Chọn file .mpp**, ấn nút `Browse...` hoặc kéo-thả trực tiếp file `.mpp` từ máy tính vào giao diện.
2. Công cụ sẽ tự động đọc file và hiển thị chi tiết ở phần trung tâm bao gồm các tab: 
   - *Task List* (Danh sách công việc)
   - *Resources & Assignments* (Nguồn lực & Phân công)
   - *Project Info* (Thông tin chi tiết dự án)
   - *Gantt Chart* (Biểu đồ tiến độ Gantt - có thể cuộn, thu phóng)
3. Chuyển xuống phần **③ Tùy chọn xuất file**, chọn định dạng mong muốn: `Excel`, `PDF`, hoặc `Cả hai`.
4. Chọn thư mục lưu kết quả.
5. Ấn **Xuất File** và chờ thanh trạng thái hoàn tất!

### Cách 2: Sử dụng Dòng lệnh (CLI)

Phù hợp khi bạn cần thao tác nhanh qua Terminal hoặc tích hợp công cụ vào các kịch bản tự động hóa (Scripts).

**Khởi chạy CLI qua `main.py`:**
```bash
# Xuất ra file Excel
python main.py project.mpp --format excel --output report.xlsx

# Xuất ra file PDF
python main.py project.mpp --format pdf --output report.pdf

# Xuất cả 2 định dạng, tự động đặt tên file và lưu vào thư mục chỉ định
python main.py project.mpp --format both --output-dir ./out/

# (Tuỳ chọn) Bật chế độ verbose in log chi tiết để debug
python main.py project.mpp --format excel --output report.xlsx --verbose
```

---

## 📁 Cấu trúc thư mục

```text
mpp_converter/
├── main.py                  # CLI entry point (chạy bằng dòng lệnh)
├── gui/
│   └── app.py               # GUI desktop app xây dựng bằng PyQt6
├── core/
│   ├── data_model.py        # Dataclass chứa cấu trúc dữ liệu: Task, Resource, Assignment,...
│   ├── mpp_reader.py        # Module xử lý đọc file .mpp qua thư viện MPXJ (JPype)
│   ├── gantt_renderer.py    # Logic render Gantt Chart dùng matplotlib
│   └── validator.py         # Kiểm tra, validate dữ liệu đầu vào/đầu ra
├── exporters/
│   ├── base_exporter.py     # Base abstract class chung cho exporter
│   ├── excel_exporter.py    # Thao tác xuất file Excel (openpyxl)
│   └── pdf_exporter.py      # Thao tác xuất file PDF (reportlab + matplotlib vẽ biểu đồ)
├── tests/
│   ├── test_data_model.py   # Unit tests cho data models
│   ├── test_integration.py  # Integration tests kiểm tra luồng đầu-cuối
│   └── sample_files/        # Các file .mpp mẫu phục vụ kiểm thử
└── requirements.txt         # File chứa danh sách dependencies
```

---

## 🧪 Chạy Kiểm Thử (Tests)

Công cụ sử dụng thư viện `pytest` để kiểm thử tự động. Để chạy toàn bộ unit tests và integration tests, thực thi:

```bash
PYTHONPATH=. pytest
```

---

## 🤝 Đóng góp (Contributing)

Chúng tôi hoan nghênh mọi đóng góp để hoàn thiện công cụ!
- Nếu bạn gặp lỗi, vui lòng mở một **Issue** kèm theo mô tả và file log.
- Nếu bạn có tính năng mới, hãy tạo **Pull Request**.

## 📄 License

Dự án được phân phối dưới giấy phép MIT License. Tham khảo file `LICENSE` để biết thêm chi tiết.
