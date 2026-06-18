"""
base_exporter.py — Abstract class chung cho mọi exporter (Excel, PDF, ...).

Mục đích: đảm bảo mọi exporter có cùng interface, để main.py gọi thống nhất
mà không cần biết chi tiết implementation bên trong.
"""

from abc import ABC, abstractmethod

from core.data_model import ProjectData


class BaseExporter(ABC):
    """Mọi exporter mới (CSV, JSON, Google Sheets...) nên kế thừa class này."""

    def __init__(self, project_data: ProjectData):
        self.project_data = project_data

    @abstractmethod
    def export(self, output_path: str) -> None:
        """
        Xuất project_data ra file tại output_path.

        Args:
            output_path: đường dẫn file output đầy đủ (bao gồm tên file + đuôi).
        """
        raise NotImplementedError

    def validate_output_path(self, output_path: str, expected_suffix: str) -> None:
        """Helper chung: kiểm tra output_path có đúng đuôi file mong đợi không."""
        from pathlib import Path

        path = Path(output_path)
        if path.suffix.lower() != expected_suffix.lower():
            raise ValueError(
                f"Output path phải có đuôi {expected_suffix}, nhận được: {path.suffix}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
