"""
gui/app.py — Giao diện desktop PyQt6 cho MPP Converter.

Cho phép người dùng không quen CLI thao tác hoàn toàn bằng chuột:
  - Chọn file .mpp (Browse hoặc kéo-thả)
  - Xem trước dữ liệu (Task List, Gantt Chart)
  - Xuất ra Excel/PDF/Cả hai

Threading:
  - MppLoaderWorker  — đọc file .mpp trên QThread riêng
  - ExportWorker     — xuất file trên QThread riêng
  Cả hai báo kết quả về main thread qua pyqtSignal, không update widget trực tiếp.
"""

import os
import sys
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Đảm bảo JAVA_HOME trước khi import bất kỳ thứ gì liên quan đến JVM
# ---------------------------------------------------------------------------
if sys.platform == "darwin" and "JAVA_HOME" not in os.environ:
    _brew_jdk = "/opt/homebrew/opt/openjdk"
    if os.path.exists(_brew_jdk):
        os.environ["JAVA_HOME"] = _brew_jdk

# Thêm thư mục gốc project vào sys.path để import core/exporters hoạt động
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import matplotlib
matplotlib.use("QtAgg")  # Backend Qt-compatible
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QSize, QTimer
)
from PyQt6.QtGui import (
    QColor, QFont, QIcon, QDragEnterEvent, QDropEvent,
    QPalette, QBrush
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QLineEdit, QFileDialog,
    QGroupBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QRadioButton, QButtonGroup, QProgressBar, QMessageBox,
    QHeaderView, QSizePolicy, QFrame, QScrollArea, QAbstractItemView,
    QTextEdit, QSplitter
)

from core.data_model import ProjectData
from core.mpp_reader import read_mpp, MppReadError
from core.gantt_renderer import build_gantt_figure
from exporters.excel_exporter import ExcelExporter
from exporters.pdf_exporter import PdfExporter


# ===========================================================================
# Style constants
# ===========================================================================
APP_STYLE = """
QMainWindow, QWidget {
    background-color: #F5F7FA;
    font-family: 'Segoe UI', 'San Francisco', Arial, sans-serif;
    font-size: 13px;
    color: #222222;
}
QGroupBox {
    border: 1.5px solid #D0D7E2;
    border-radius: 8px;
    margin-top: 14px;
    padding: 10px 12px;
    background-color: #FFFFFF;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    top: -1px;
    padding: 0 6px;
    color: #2E5C8A;
    font-weight: bold;
    font-size: 13px;
}
QPushButton {
    background-color: #2E5C8A;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: 600;
    min-height: 28px;
}
QPushButton:hover {
    background-color: #3A72A8;
}
QPushButton:pressed {
    background-color: #1E3F62;
}
QPushButton:disabled {
    background-color: #B0BEC5;
    color: #ECEFF1;
}
QPushButton#btnSecondary {
    background-color: #E8EDF4;
    color: #2E5C8A;
    border: 1.5px solid #C5D0DF;
}
QPushButton#btnSecondary:hover {
    background-color: #D6E4F0;
}
QLineEdit {
    border: 1.5px solid #C5D0DF;
    border-radius: 6px;
    padding: 5px 10px;
    background-color: #FFFFFF;
    color: #333333;
}
QLineEdit:focus {
    border-color: #2E5C8A;
}
QLineEdit[readOnly="true"] {
    background-color: #F0F3F7;
    color: #555555;
}
QTableWidget {
    border: 1px solid #D0D7E2;
    border-radius: 6px;
    background-color: #FFFFFF;
    gridline-color: #EEEEEE;
    selection-background-color: #D6E4F0;
}
QTableWidget QHeaderView::section {
    background-color: #2E5C8A;
    color: white;
    font-weight: bold;
    padding: 6px;
    border: none;
    border-right: 1px solid #3A72A8;
}
QTabWidget::pane {
    border: 1px solid #D0D7E2;
    border-radius: 6px;
    background-color: #FFFFFF;
}
QTabBar::tab {
    background: #E8EDF4;
    color: #2E5C8A;
    border: 1px solid #C5D0DF;
    border-bottom: none;
    border-radius: 6px 6px 0 0;
    padding: 7px 20px;
    margin-right: 3px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: #FFFFFF;
    color: #1A3A5C;
    border-color: #2E5C8A;
}
QProgressBar {
    border: 1px solid #C5D0DF;
    border-radius: 6px;
    background-color: #E8EDF4;
    height: 16px;
    text-align: center;
    color: #333333;
    font-size: 11px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #2E5C8A, stop:1 #5D9ED4);
    border-radius: 5px;
}
QRadioButton {
    spacing: 6px;
    font-size: 13px;
}
QRadioButton::indicator {
    width: 16px;
    height: 16px;
}
QLabel#labelStatus {
    color: #555555;
    font-size: 12px;
    font-style: italic;
}
"""


# ===========================================================================
# Worker threads
# ===========================================================================
class MppLoaderWorker(QThread):
    """Worker thread cho việc đọc file .mpp qua MPXJ (tránh block UI)."""
    progress = pyqtSignal(int)          # 0-100
    finished = pyqtSignal(object)       # ProjectData
    error = pyqtSignal(str)             # thông báo lỗi

    def __init__(self, file_path: str):
        super().__init__()
        self._file_path = file_path

    def run(self):
        try:
            self.progress.emit(10)
            data = read_mpp(self._file_path)
            self.progress.emit(100)
            self.finished.emit(data)
        except MppReadError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"Lỗi không xác định: {e}")


class ExportWorker(QThread):
    """Worker thread cho việc xuất file Excel/PDF (tránh block UI)."""
    progress = pyqtSignal(int)          # 0-100
    finished = pyqtSignal(str)          # đường dẫn thư mục output
    error = pyqtSignal(str)             # thông báo lỗi

    def __init__(self, project_data: ProjectData, output_dir: str, fmt: str):
        """
        Args:
            project_data: dữ liệu đã đọc từ .mpp
            output_dir:   thư mục lưu file
            fmt:          'excel' | 'pdf' | 'both'
        """
        super().__init__()
        self._data = project_data
        self._output_dir = output_dir
        self._fmt = fmt

    def run(self):
        try:
            self.progress.emit(5)
            out_dir = Path(self._output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            base = self._data.name.replace(" ", "_") or "project"

            if self._fmt in ("excel", "both"):
                excel_path = out_dir / f"{base}.xlsx"
                ExcelExporter(self._data).export(str(excel_path))
                self.progress.emit(45 if self._fmt == "both" else 90)

            if self._fmt in ("pdf", "both"):
                pdf_path = out_dir / f"{base}.pdf"
                PdfExporter(self._data).export(str(pdf_path))
                self.progress.emit(90)

            self.progress.emit(100)
            self.finished.emit(self._output_dir)
        except Exception as e:
            self.error.emit(str(e))


# ===========================================================================
# Widgets
# ===========================================================================
class _HSep(QFrame):
    """Đường kẻ ngang phân cách."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setStyleSheet("color: #D0D7E2;")


class FilePickerWidget(QGroupBox):
    """Vùng ① — Chọn file .mpp."""
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("① Chọn file .mpp", parent)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout()
        layout.setSpacing(8)

        self.txt_path = QLineEdit()
        self.txt_path.setReadOnly(True)
        self.txt_path.setPlaceholderText("Chưa chọn file — kéo-thả hoặc bấm Browse…")
        self.txt_path.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.btn_browse = QPushButton("📂  Browse…")
        self.btn_browse.setObjectName("btnSecondary")
        self.btn_browse.setFixedWidth(130)
        self.btn_browse.clicked.connect(self._browse)

        layout.addWidget(self.txt_path)
        layout.addWidget(self.btn_browse)
        self.setLayout(layout)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn file Microsoft Project",
            "",
            "Microsoft Project Files (*.mpp);;All Files (*)"
        )
        if path:
            self._emit_if_valid(path)

    def set_path(self, path: str):
        self.txt_path.setText(path)

    def _emit_if_valid(self, path: str):
        if not path.lower().endswith(".mpp"):
            QMessageBox.warning(
                self, "Sai định dạng",
                f"Chỉ hỗ trợ file .mpp\n\nFile bạn chọn: {Path(path).name}"
            )
            return
        self.txt_path.setText(path)
        self.file_selected.emit(path)


class ProjectInfoWidget(QGroupBox):
    """Vùng ② — Thông tin project (ẩn cho đến khi load xong)."""
    def __init__(self, parent=None):
        super().__init__("② Thông tin Project", parent)
        self._build_ui()
        self.hide()

    def _build_ui(self):
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        grid.setColumnStretch(5, 1)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)

        def _lbl(text: str, bold=False) -> QLabel:
            l = QLabel(text)
            if bold:
                l.setStyleSheet("font-weight: bold; color: #2E5C8A;")
            return l

        self._lbl_name = QLabel("—")
        self._lbl_start = QLabel("—")
        self._lbl_finish = QLabel("—")
        self._lbl_author = QLabel("—")
        self._lbl_last_saved = QLabel("—")
        self._lbl_calendar = QLabel("—")
        self._lbl_count = QLabel("—")
        self._lbl_count.setObjectName("_lbl_count")

        # Row 0
        grid.addWidget(_lbl("Tên project:", True), 0, 0)
        grid.addWidget(self._lbl_name, 0, 1)
        grid.addWidget(_lbl("Tác giả:", True), 0, 2)
        grid.addWidget(self._lbl_author, 0, 3)
        grid.addWidget(_lbl("Calendar:", True), 0, 4)
        grid.addWidget(self._lbl_calendar, 0, 5)

        # Row 1
        grid.addWidget(_lbl("Bắt đầu:", True), 1, 0)
        grid.addWidget(self._lbl_start, 1, 1)
        grid.addWidget(_lbl("Kết thúc:", True), 1, 2)
        grid.addWidget(self._lbl_finish, 1, 3)
        grid.addWidget(_lbl("Lần lưu cuối:", True), 1, 4)
        grid.addWidget(self._lbl_last_saved, 1, 5)

        # Row 2
        grid.addWidget(_lbl("Tasks / Milestones / Resources:", True), 2, 0)
        grid.addWidget(self._lbl_count, 2, 1, 1, 5)

        self.setLayout(grid)

    def update_data(self, data: ProjectData):
        self._lbl_name.setText(data.name or "—")
        self._lbl_author.setText(data.author or "—")
        self._lbl_calendar.setText(data.calendar_name or "—")
        
        self._lbl_start.setText(
            data.start_date.strftime("%Y-%m-%d") if data.start_date else "—"
        )
        self._lbl_finish.setText(
            data.finish_date.strftime("%Y-%m-%d") if data.finish_date else "—"
        )
        self._lbl_last_saved.setText(
            data.last_saved.strftime("%Y-%m-%d %H:%M") if data.last_saved else "—"
        )
        
        self._lbl_count.setText(
            f"{data.task_count} tasks   •   {data.milestone_count} milestones   •   {len(data.resources)} resources   •   Tiền tệ: {data.currency_symbol or '—'}   •   Giờ làm việc/ngày: {data.minutes_per_day // 60}h"
        )
        self.show()


class TaskListTab(QWidget):
    """Tab Task List — QTableWidget với tất cả fields có trong file .mpp."""
    HEADERS = [
        "WBS", "Tên công việc", "Bắt đầu", "Kết thúc",
        "Duration (ngày)", "% Hoàn thành",
        "Critical", "Free Slack", "Total Slack",
        "Priority", "Cost", "Actual Cost",
        "Constraint", "Predecessors", "Resources", "Notes",
    ]
    # Cột được căn giữa (không phải tên)
    _CENTER_COLS = {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13}

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setShowGrid(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.verticalHeader().hide()
        self.table.setStyleSheet("alternate-background-color: #F5F8FC;")

        layout.addWidget(self.table)

    def load_data(self, data: ProjectData):
        tasks = data.tasks
        self.table.setRowCount(len(tasks))

        MILESTONE_BG = QColor("#FFF3CD")
        SUMMARY_BG = QColor("#EEF2F7")
        CRITICAL_COLOR = QColor("#FFE8E8")

        sym = data.currency_symbol or ""

        for row, task in enumerate(tasks):
            indent = "  " * task.outline_level

            values = [
                task.wbs or str(task.outline_level),     # WBS
                indent + task.name,                       # Tên công việc
                task.start.strftime("%Y-%m-%d") if task.start else "",
                task.finish.strftime("%Y-%m-%d") if task.finish else "",
                f"{task.duration_days:.2f}" if task.duration_hours else "0.00",
                f"{int(task.percent_complete)}%",
                "✔" if task.is_critical else "",         # Critical
                f"{task.free_slack_days:.2f}d",           # Free Slack
                f"{task.total_slack_days:.2f}d",          # Total Slack
                str(task.priority),                       # Priority
                f"{sym}{task.cost:,.0f}" if task.cost else "",       # Cost
                f"{sym}{task.actual_cost:,.0f}" if task.actual_cost else "",  # Actual
                task.constraint_type.replace("_", " ").title() if task.constraint_type else "",
                ", ".join(str(p) for p in task.predecessors) if task.predecessors else "",
                "; ".join(task.resource_names) if task.resource_names else "",
                task.notes[:120] + ("…" if len(task.notes) > 120 else "") if task.notes else "",
            ]

            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setToolTip(val)  # tooltip để xem full text

                # Màu nền
                if task.is_milestone:
                    item.setBackground(QBrush(MILESTONE_BG))
                elif task.is_summary:
                    item.setBackground(QBrush(SUMMARY_BG))
                    if col in (0, 1):
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                elif task.is_critical and col == 6:
                    item.setBackground(QBrush(CRITICAL_COLOR))

                # Critical ✔ — tô đỏ cho dễ thấy
                if col == 6 and task.is_critical:
                    item.setForeground(QBrush(QColor("#C0392B")))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

                if col in self._CENTER_COLS:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                    )

                self.table.setItem(row, col, item)

        # Resize cột thật sau khi có data
        for c in range(len(self.HEADERS)):
            if c != 1:  # cột 1 đã Stretch
                self.table.resizeColumnToContents(c)


# ---------------------------------------------------------------------------
# Tab Resources
# ---------------------------------------------------------------------------
class ResourcesTab(QWidget):
    """Tab hiển thị toàn bộ resources và assignments của họ."""
    HEADERS = ["ID", "Tên", "Loại", "Initials", "Max Units %",
               "Calendar", "Standard Rate", "Email", "Ghi chú"]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setStyleSheet("alternate-background-color: #F5F8FC;")
        layout.addWidget(self.table)

    def load_data(self, data: ProjectData):
        resources = data.resources
        self.table.setRowCount(len(resources))
        TYPE_COLORS = {"Work": QColor("#E8F5E9"), "Material": QColor("#FFF8E1"), "Cost": QColor("#FCE4EC")}

        for row, r in enumerate(resources):
            bg = QBrush(TYPE_COLORS.get(r.type, QColor("#FFFFFF")))
            values = [
                str(r.id), r.name, r.type, r.initials,
                f"{r.max_units:.0f}%", r.calendar_name,
                r.std_rate, r.email, r.notes[:80] if r.notes else "",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setBackground(bg)
                item.setToolTip(val)
                self.table.setItem(row, col, item)

        for c in range(len(self.HEADERS)):
            if c != 1:
                self.table.resizeColumnToContents(c)


# ---------------------------------------------------------------------------
# Tab Assignments
# ---------------------------------------------------------------------------
class AssignmentsTab(QWidget):
    """Tab hiển thị toàn bộ assignments (Task ↔ Resource)."""
    HEADERS = ["Task ID", "Tên Task", "Resource ID", "Tên Resource",
               "Units %", "Work (h)", "Actual Work (h)", "Cost", "Actual Cost"]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(True)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setStyleSheet("alternate-background-color: #F5F8FC;")
        layout.addWidget(self.table)

    def load_data(self, data: ProjectData):
        # Build lookup maps
        task_map = {t.id: t.name for t in data.tasks}
        res_map = {r.id: r.name for r in data.resources}
        sym = data.currency_symbol or ""

        assignments = data.assignments
        self.table.setRowCount(len(assignments))

        for row, a in enumerate(assignments):
            task_name = task_map.get(a.task_id, "")
            res_name = res_map.get(a.resource_id, "")
            values = [
                str(a.task_id), task_name,
                str(a.resource_id), res_name,
                f"{a.units:.0f}%",
                f"{a.work_hours:.1f}h",
                f"{a.actual_work_hours:.1f}h",
                f"{sym}{a.cost:,.0f}" if a.cost else "",
                f"{sym}{a.actual_cost:,.0f}" if a.actual_cost else "",
            ]
            CENTER_COLS = {0, 2, 4, 5, 6, 7, 8}
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setToolTip(val)
                if col in CENTER_COLS:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, col, item)

        for c in range(len(self.HEADERS)):
            if c != 1:
                self.table.resizeColumnToContents(c)


# ---------------------------------------------------------------------------
# Tab Project Info (full properties)
# ---------------------------------------------------------------------------
class ProjectInfoTab(QWidget):
    """Tab hiển thị toàn bộ thông tin project: properties + custom properties."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # --- Standard properties ---
        grp_std = QGroupBox("ℹ️  Project Properties")
        grp_layout = QVBoxLayout(grp_std)
        self._std_table = QTableWidget(0, 2)
        self._std_table.setHorizontalHeaderLabels(["Property", "Value"])
        self._std_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._std_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._std_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._std_table.verticalHeader().hide()
        self._std_table.setAlternatingRowColors(True)
        self._std_table.setStyleSheet("alternate-background-color: #F5F8FC;")
        grp_layout.addWidget(self._std_table)
        layout.addWidget(grp_std)

        # --- Custom properties ---
        grp_custom = QGroupBox("📌  Custom Properties")
        grp_custom_layout = QVBoxLayout(grp_custom)
        self._custom_table = QTableWidget(0, 2)
        self._custom_table.setHorizontalHeaderLabels(["Property", "Value"])
        self._custom_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._custom_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._custom_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._custom_table.verticalHeader().hide()
        self._custom_table.setAlternatingRowColors(True)
        self._custom_table.setStyleSheet("alternate-background-color: #F5F8FC;")
        grp_custom_layout.addWidget(self._custom_table)
        layout.addWidget(grp_custom)

    def load_data(self, data: ProjectData):
        fields = [
            ("Tên project",          data.name),
            ("Tác giả (Author)",      data.author or "—"),
            ("Ngày bắt đầu",          data.start_date.strftime("%Y-%m-%d %H:%M") if data.start_date else "—"),
            ("Ngày kết thúc",          data.finish_date.strftime("%Y-%m-%d %H:%M") if data.finish_date else "—"),
            ("Lần lưu cuối",           data.last_saved.strftime("%Y-%m-%d %H:%M") if data.last_saved else "—"),
            ("Lịch sửa (Revision)",   str(data.revision)),
            ("Tiền tệ",               data.currency_symbol or "—"),
            ("Giờ làm việc/ngày",    f"{data.minutes_per_day // 60}h"),
            ("Calendar mặc định",     data.calendar_name or "—"),
            ("Tổng tasks",             str(data.task_count)),
            ("Milestones",             str(data.milestone_count)),
            ("Resources",              str(len(data.resources))),
            ("Assignments",            str(len(data.assignments))),
        ]

        self._std_table.setRowCount(len(fields))
        for row, (lbl, val) in enumerate(fields):
            ki = QTableWidgetItem(lbl)
            vi = QTableWidgetItem(val)
            ki.setFlags(ki.flags() & ~Qt.ItemFlag.ItemIsEditable)
            vi.setFlags(vi.flags() & ~Qt.ItemFlag.ItemIsEditable)
            font = ki.font()
            font.setBold(True)
            ki.setFont(font)
            self._std_table.setItem(row, 0, ki)
            self._std_table.setItem(row, 1, vi)

        # Custom properties table
        cp = data.custom_properties
        self._custom_table.setRowCount(len(cp))
        for row, (key, val) in enumerate(sorted(cp.items())):
            ki = QTableWidgetItem(key)
            vi = QTableWidgetItem(val)
            ki.setFlags(ki.flags() & ~Qt.ItemFlag.ItemIsEditable)
            vi.setFlags(vi.flags() & ~Qt.ItemFlag.ItemIsEditable)
            ki.setToolTip(val)
            vi.setToolTip(val)
            self._custom_table.setItem(row, 0, ki)
            self._custom_table.setItem(row, 1, vi)


class GanttTab(QWidget):
    """
    Tab Gantt Chart.

    Canvas matplotlib được bọc trong QScrollArea — khi project có nhiều task,
    người dùng có thể cuộn để xem toàn bộ biểu đồ mà labels không bị chồng đè.
    Có nút toggle để chuyển giữa chế độ 'Summary only' và 'All tasks'.
    """
    # DPI cố định để tính pixel size của canvas
    _DPI = 100
    # Inch trên mỗi hàng task
    _ROW_HEIGHT_INCH = 0.30
    # Chiều rộng figure (inch) — phải khớp với gantt_renderer
    _FIG_WIDTH_INCH = 14.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_data: ProjectData | None = None
        self._summary_only: bool | None = None  # None = auto
        self._canvas = None
        self._toolbar = None

        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- Thanh công cụ trên cùng ---
        toolbar_row = QHBoxLayout()
        toolbar_row.setContentsMargins(8, 6, 8, 4)

        self._lbl_filter = QLabel("")
        self._lbl_filter.setStyleSheet("color: #555; font-size: 12px; font-style: italic;")

        self._btn_toggle = QPushButton("Xem tất cả tasks")
        self._btn_toggle.setObjectName("btnSecondary")
        self._btn_toggle.setFixedWidth(160)
        self._btn_toggle.hide()
        self._btn_toggle.clicked.connect(self._toggle_view)

        toolbar_row.addWidget(self._lbl_filter)
        toolbar_row.addStretch()
        toolbar_row.addWidget(self._btn_toggle)
        outer.addLayout(toolbar_row)

        # --- Placeholder (trước khi có data) ---
        self._placeholder = QLabel("Chưa có dữ liệu — hãy load file .mpp trước.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #999; font-size: 14px; padding: 40px;")
        outer.addWidget(self._placeholder)

        # --- QScrollArea chứa canvas matplotlib ---
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet("QScrollArea { border: none; }")
        self._scroll.hide()
        outer.addWidget(self._scroll, stretch=1)

        # Container bên trong scroll
        self._canvas_container = QWidget()
        self._canvas_layout = QVBoxLayout(self._canvas_container)
        self._canvas_layout.setContentsMargins(0, 0, 0, 0)
        self._canvas_layout.setSpacing(0)
        self._scroll.setWidget(self._canvas_container)

    def _toggle_view(self):
        """Chuyển đổi giữa chế độ summary-only và all-tasks."""
        if self._project_data is None:
            return
        # Đảo trạng thái
        if self._summary_only is None or self._summary_only:
            self._summary_only = False
        else:
            self._summary_only = True
        self._render(self._project_data)

    def _render(self, data: ProjectData):
        """Xoá canvas cũ và vẽ lại với cài đặt summary_only hiện tại."""
        # Xoá canvas cũ
        if self._canvas is not None:
            self._canvas_layout.removeWidget(self._toolbar)
            self._canvas_layout.removeWidget(self._canvas)
            self._toolbar.deleteLater()
            self._canvas.deleteLater()
            self._canvas = None
            self._toolbar = None

        fig = build_gantt_figure(data, summary_only=self._summary_only)
        n_tasks = len([t for t in data.tasks if t.start and t.finish])

        # Tính pixel height phù hợp để canvas không bị squeeze
        fig_h_inch, _ = fig.get_size_inches()[1], fig.get_size_inches()[0]
        canvas_h_px = max(int(fig_h_inch * self._DPI), 300)
        canvas_w_px = max(int(self._FIG_WIDTH_INCH * self._DPI), 800)

        self._canvas = FigureCanvasQTAgg(fig)
        self._canvas.setMinimumSize(canvas_w_px, canvas_h_px)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._toolbar = NavigationToolbar2QT(self._canvas, self._canvas_container)

        self._canvas_layout.addWidget(self._toolbar)
        self._canvas_layout.addWidget(self._canvas)

        self._canvas.draw()

        # Cập nhật label và nút toggle
        n_shown = len(fig.axes[0].get_yticks()) if fig.axes else 0
        if self._summary_only:
            self._lbl_filter.setText(
                f"Đang hiển thị summary/milestone ({n_shown}/{n_tasks} tasks). "
            )
            self._btn_toggle.setText("Xem tất cả tasks")
        else:
            self._lbl_filter.setText(f"Đang hiển thị tất cả {n_tasks} tasks.")
            self._btn_toggle.setText("Chỉ xem summary")

        # Cuộn lên đầu sau khi render
        self._scroll.verticalScrollBar().setValue(0)

    def load_data(self, data: ProjectData):
        """Gọi từ main thread sau khi MppLoaderWorker trả về."""
        self._project_data = data

        # Mặc định: hiển thị toàn bộ tasks (người dùng có thể thu gọn bằng nút toggle)
        self._summary_only = False

        self._placeholder.hide()
        self._scroll.show()
        self._btn_toggle.show()

        self._render(data)


class ExportWidget(QGroupBox):
    """Vùng ④ — Radio button + chọn thư mục + Progress + Convert."""
    convert_requested = pyqtSignal(str, str)   # (output_dir, fmt)

    def __init__(self, parent=None):
        super().__init__("④ Xuất file", parent)
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)

        # --- Format radio buttons ---
        fmt_layout = QHBoxLayout()
        fmt_layout.setSpacing(20)
        self._fmt_group = QButtonGroup(self)

        self._rb_excel = QRadioButton("Excel (.xlsx)")
        self._rb_pdf = QRadioButton("PDF (.pdf)")
        self._rb_both = QRadioButton("Cả hai")
        self._rb_both.setChecked(True)

        for i, rb in enumerate([self._rb_excel, self._rb_pdf, self._rb_both]):
            self._fmt_group.addButton(rb, i)
            fmt_layout.addWidget(rb)
        fmt_layout.addStretch()
        main_layout.addLayout(fmt_layout)

        # --- Output directory ---
        dir_layout = QHBoxLayout()
        dir_layout.setSpacing(8)

        lbl_dir = QLabel("Thư mục lưu:")
        lbl_dir.setFixedWidth(100)

        self.txt_dir = QLineEdit()
        self.txt_dir.setReadOnly(True)
        self.txt_dir.setPlaceholderText("Chưa chọn thư mục output…")

        self.btn_dir = QPushButton("📁  Chọn thư mục")
        self.btn_dir.setObjectName("btnSecondary")
        self.btn_dir.setFixedWidth(150)
        self.btn_dir.clicked.connect(self._pick_dir)

        dir_layout.addWidget(lbl_dir)
        dir_layout.addWidget(self.txt_dir)
        dir_layout.addWidget(self.btn_dir)
        main_layout.addLayout(dir_layout)

        # --- Progress bar ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        # --- Status label + Convert button ---
        bottom_layout = QHBoxLayout()

        self.lbl_status = QLabel("Chưa convert")
        self.lbl_status.setObjectName("labelStatus")

        self.btn_convert = QPushButton("▶  Convert")
        self.btn_convert.setFixedWidth(130)
        self.btn_convert.setEnabled(False)
        self.btn_convert.setMinimumHeight(36)
        self.btn_convert.clicked.connect(self._on_convert)

        bottom_layout.addWidget(self.lbl_status)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_convert)
        main_layout.addLayout(bottom_layout)

        self.setLayout(main_layout)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu output")
        if d:
            self.txt_dir.setText(d)

    def _on_convert(self):
        out_dir = self.txt_dir.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "Chưa chọn thư mục", "Hãy chọn thư mục lưu file trước khi convert.")
            return
        fmt_map = {0: "excel", 1: "pdf", 2: "both"}
        fmt = fmt_map.get(self._fmt_group.checkedId(), "both")
        self.convert_requested.emit(out_dir, fmt)

    def set_convert_enabled(self, enabled: bool):
        self.btn_convert.setEnabled(enabled)

    def set_progress(self, value: int):
        self.progress_bar.show()
        self.progress_bar.setValue(value)

    def set_status(self, text: str):
        self.lbl_status.setText(text)

    def reset_progress(self):
        self.progress_bar.setValue(0)
        self.progress_bar.hide()


# ===========================================================================
# Main Window
# ===========================================================================
class MainWindow(QMainWindow):
    """Cửa sổ chính của MPP Converter GUI."""

    def __init__(self):
        super().__init__()
        self._project_data: ProjectData | None = None
        self._loader_worker: MppLoaderWorker | None = None
        self._export_worker: ExportWorker | None = None

        self.setWindowTitle("UnboxMPP")
        self.setMinimumSize(960, 680)
        self.resize(1100, 750)
        self.setAcceptDrops(True)

        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # ① File Picker
        self.file_picker = FilePickerWidget()
        root.addWidget(self.file_picker)

        # ② Project Info
        self.project_info = ProjectInfoWidget()
        root.addWidget(self.project_info)

        # ④ Tab Preview (5 tabs)
        self._tab_widget = QTabWidget()
        self._tab_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._task_tab          = TaskListTab()
        self._gantt_tab         = GanttTab()
        self._resources_tab     = ResourcesTab()
        self._assignments_tab   = AssignmentsTab()
        self._project_info_tab  = ProjectInfoTab()

        self._tab_widget.addTab(self._task_tab,         "📋  Task List")
        self._tab_widget.addTab(self._gantt_tab,        "📊  Gantt Chart")
        self._tab_widget.addTab(self._resources_tab,    "👥  Resources")
        self._tab_widget.addTab(self._assignments_tab,  "🔗  Assignments")
        self._tab_widget.addTab(self._project_info_tab, "📁  Project Info")

        root.addWidget(self._tab_widget, stretch=1)

        # ④ Export
        self.export_widget = ExportWidget()
        root.addWidget(self.export_widget)

        # Loading indicator (hiện khi đang đọc file)
        self._lbl_loading = QLabel("⏳  Đang đọc file .mpp…")
        self._lbl_loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_loading.setStyleSheet("color: #2E5C8A; font-size: 13px; font-style: italic; padding: 4px;")
        self._lbl_loading.hide()
        root.addWidget(self._lbl_loading)

    def _connect_signals(self):
        self.file_picker.file_selected.connect(self._load_file)
        self.export_widget.convert_requested.connect(self._start_export)

    # ------------------------------------------------------------------
    # Drag-and-drop
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].toLocalFile().lower().endswith(".mpp"):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith(".mpp"):
                self.file_picker.set_path(path)
                self._load_file(path)
            else:
                QMessageBox.warning(
                    self, "Sai định dạng",
                    f"Chỉ hỗ trợ file .mpp\n\nFile bạn thả: {Path(path).name}"
                )

    # ------------------------------------------------------------------
    # Load file (background thread)
    # ------------------------------------------------------------------
    def _load_file(self, path: str):
        if self._loader_worker and self._loader_worker.isRunning():
            return  # Tránh load đồng thời

        self._lbl_loading.show()
        self.export_widget.set_convert_enabled(False)
        self.export_widget.set_status("Đang đọc file…")
        self.export_widget.set_progress(0)
        self.export_widget.progress_bar.show()

        self._loader_worker = MppLoaderWorker(path)
        self._loader_worker.progress.connect(self.export_widget.set_progress)
        self._loader_worker.finished.connect(self._on_load_finished)
        self._loader_worker.error.connect(self._on_load_error)
        self._loader_worker.start()

    def _on_load_finished(self, data: ProjectData):
        self._project_data = data
        self._lbl_loading.hide()
        self.export_widget.reset_progress()
        self.export_widget.set_status(
            f"✅  Đã load: {data.task_count} tasks, {data.milestone_count} milestones, {len(data.resources)} resources"
        )
        self.export_widget.set_convert_enabled(True)

        # Populate UI
        self.project_info.update_data(data)
        self._task_tab.load_data(data)
        self._resources_tab.load_data(data)
        self._assignments_tab.load_data(data)
        self._project_info_tab.load_data(data)

        # Load Gantt chart trên main thread (matplotlib, nhanh)
        self._gantt_tab.load_data(data)

    def _on_load_error(self, msg: str):
        self._lbl_loading.hide()
        self.export_widget.reset_progress()
        self.export_widget.set_status("❌  Load thất bại")
        QMessageBox.critical(
            self,
            "Lỗi đọc file .mpp",
            msg
        )

    # ------------------------------------------------------------------
    # Export (background thread)
    # ------------------------------------------------------------------
    def _start_export(self, output_dir: str, fmt: str):
        if self._project_data is None:
            return
        if self._export_worker and self._export_worker.isRunning():
            return

        self.export_widget.set_status("Đang xuất file…")
        self.export_widget.set_progress(0)
        self.export_widget.set_convert_enabled(False)

        self._export_worker = ExportWorker(self._project_data, output_dir, fmt)
        self._export_worker.progress.connect(self.export_widget.set_progress)
        self._export_worker.finished.connect(self._on_export_finished)
        self._export_worker.error.connect(self._on_export_error)
        self._export_worker.start()

    def _on_export_finished(self, out_dir: str):
        self.export_widget.set_status("✅  Xuất file thành công!")
        self.export_widget.set_convert_enabled(True)

        box = QMessageBox(self)
        box.setWindowTitle("Xuất file thành công")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(
            f"Đã xuất file thành công!\n\nThư mục chứa file:\n{out_dir}"
        )
        box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
        btn_open = box.addButton("📂  Mở thư mục", QMessageBox.ButtonRole.ActionRole)
        box.exec()

        if box.clickedButton() == btn_open:
            self._open_folder(out_dir)

    def _on_export_error(self, msg: str):
        self.export_widget.set_status("❌  Xuất file thất bại")
        self.export_widget.set_convert_enabled(True)
        QMessageBox.critical(self, "Lỗi xuất file", msg)

    @staticmethod
    def _open_folder(path: str):
        """Mở thư mục trong file explorer (cross-platform)."""
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])


# ===========================================================================
# Entry point
# ===========================================================================
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
