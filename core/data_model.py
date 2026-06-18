"""
Data model layer — chuẩn hoá dữ liệu đọc từ MPP thành dataclass Python sạch,
độc lập với cấu trúc object phức tạp của MPXJ/Java.

Mọi exporter (Excel, PDF, ...) chỉ làm việc với các class ở đây,
không bao giờ import trực tiếp MPXJ.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Resource:
    """Một resource (người/thiết bị/chi phí) trong project."""
    id: int
    name: str
    type: str           # "Work" | "Material" | "Cost"
    initials: str = ""
    email: str = ""
    max_units: float = 100.0    # % availability tối đa
    std_rate: str = ""          # Standard rate (vd: "50.00/h")
    calendar_name: str = ""
    notes: str = ""


@dataclass
class Assignment:
    """Liên kết giữa 1 task và 1 resource, kèm % phân bổ."""
    task_id: int
    resource_id: int
    units: float        # % allocation, ví dụ 100.0 = full time
    work_hours: float = 0.0
    actual_work_hours: float = 0.0
    cost: float = 0.0
    actual_cost: float = 0.0


@dataclass
class Task:
    """Một dòng task trong MS Project (có thể là task thường, summary, hoặc milestone)."""
    id: int
    name: str
    start: Optional[datetime]
    finish: Optional[datetime]
    duration_hours: float
    percent_complete: float
    outline_level: int          # độ sâu trong WBS — dùng để indent khi hiển thị và vẽ Gantt
    predecessors: list[int] = field(default_factory=list)
    is_milestone: bool = False
    is_summary: bool = False

    # --- Fields mở rộng ---
    wbs: str = ""               # Số WBS, vd "1.2.3"
    priority: int = 500         # 0–1000 (500 = Medium)
    cost: float = 0.0           # Tổng chi phí ước tính
    actual_cost: float = 0.0
    constraint_type: str = ""   # "AS_SOON_AS_POSSIBLE", "MUST_START_ON", ...
    is_critical: bool = False   # Có nằm trên critical path không
    free_slack_days: float = 0.0
    total_slack_days: float = 0.0
    notes: str = ""             # Ghi chú của task (plain text)
    resource_names: list[str] = field(default_factory=list)   # Tên resources được gán

    @property
    def duration_days(self) -> float:
        """Quy đổi duration sang số ngày làm việc (8h/ngày), tiện cho hiển thị Excel/PDF."""
        return round(self.duration_hours / 8, 2) if self.duration_hours else 0.0


@dataclass
class ProjectData:
    """Toàn bộ dữ liệu của 1 file .mpp sau khi đã được parse và chuẩn hoá."""
    name: str
    start_date: Optional[datetime]
    finish_date: Optional[datetime]
    tasks: list[Task] = field(default_factory=list)
    resources: list[Resource] = field(default_factory=list)
    assignments: list[Assignment] = field(default_factory=list)

    # --- Project metadata mở rộng ---
    author: str = ""
    last_saved: Optional[datetime] = None
    currency_symbol: str = ""
    minutes_per_day: int = 480          # 8h mặc định
    calendar_name: str = ""
    revision: int = 0
    custom_properties: dict = field(default_factory=dict)   # key-value từ file

    @property
    def task_count(self) -> int:
        return len([t for t in self.tasks if not t.is_summary])

    @property
    def milestone_count(self) -> int:
        return len([t for t in self.tasks if t.is_milestone])

    def get_resources_for_task(self, task_id: int) -> list[Resource]:
        """Helper: trả về danh sách resource được assign cho 1 task cụ thể."""
        resource_ids = {a.resource_id for a in self.assignments if a.task_id == task_id}
        return [r for r in self.resources if r.id in resource_ids]
