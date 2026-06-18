"""
gantt_renderer.py — Vẽ Gantt chart và trả về matplotlib Figure.

Hàm `build_gantt_figure()` là trung tâm để tái sử dụng ở nhiều nơi:
  - `exporters/pdf_exporter.py`: lưu figure ra PNG tạm, nhúng vào PDF.
  - `gui/app.py`: nhúng trực tiếp vào Qt canvas qua FigureCanvasQTAgg.
"""

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from core.font_utils import register_fonts
from core.data_model import ProjectData

# Đăng ký font Unicode và cấu hình matplotlib ngay tại đây
register_fonts()

# Chiều cao tối thiểu mỗi hàng (inch) — đảm bảo label không bị chồng đè
_ROW_HEIGHT_INCH = 0.30
# Số task tối đa trước khi tự động ẩn task leaf (chỉ hiện summary/milestone)
_SUMMARY_ONLY_THRESHOLD = 80
# Độ dài tối đa của label trên trục Y (ký tự)
_MAX_LABEL_LEN = 55


def _truncate(text: str, max_len: int = _MAX_LABEL_LEN) -> str:
    """Cắt ngắn chuỗi và thêm '…' nếu vượt quá max_len."""
    return text if len(text) <= max_len else text[: max_len - 1] + "\u2026"


def build_gantt_figure(
    project_data: ProjectData,
    summary_only: bool | None = None,
) -> matplotlib.figure.Figure:
    """
    Vẽ Gantt chart dạng horizontal bar chart.

    Args:
        project_data:  Dữ liệu project đã được chuẩn hoá.
        summary_only:  True  → chỉ vẽ summary tasks (WBS level-1/2).
                       False → vẽ tất cả tasks.
                       None  → tự quyết định dựa vào số lượng task.

    Returns:
        matplotlib.figure.Figure sẵn sàng nhúng vào Qt canvas hoặc save PNG/PDF.
    """
    all_tasks = [t for t in project_data.tasks if t.start and t.finish]

    if not all_tasks:
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.text(
            0.5, 0.5,
            "Không có dữ liệu Gantt (task chưa có ngày bắt đầu/kết thúc).",
            ha="center", va="center", fontsize=11, color="#888888",
            transform=ax.transAxes,
        )
        ax.set_axis_off()
        fig.tight_layout()
        return fig

    # --- Quyết định có lọc chỉ summary hay không ---
    if summary_only is None:
        summary_only = len(all_tasks) > _SUMMARY_ONLY_THRESHOLD

    if summary_only:
        tasks = [t for t in all_tasks if t.is_summary or t.is_milestone]
        # Nếu lọc xong vẫn còn quá nhiều, chỉ lấy outline level <= 2
        if len(tasks) > _SUMMARY_ONLY_THRESHOLD:
            tasks = [t for t in tasks if t.outline_level <= 2]
    else:
        tasks = all_tasks

    if not tasks:
        tasks = all_tasks  # fallback: không lọc được gì

    # Vẽ từ dưới lên để task đầu tiên ở trên cùng
    ordered_tasks = list(reversed(tasks))
    n = len(ordered_tasks)

    names: list[str] = []
    starts = []
    finishes = []
    colors: list[str] = []
    milestone_flags: list[bool] = []
    summary_flags: list[bool] = []

    for task in ordered_tasks:
        indent = "  " * task.outline_level
        label = _truncate(indent + task.name)
        names.append(label)
        starts.append(task.start)
        finishes.append(task.finish)
        milestone_flags.append(task.is_milestone)
        summary_flags.append(task.is_summary)

        if task.is_milestone:
            colors.append("#FFD966")
        elif task.is_summary:
            colors.append("#6B8FB5")
        else:
            colors.append("#4F81BD")

    # --- Kích thước figure ---
    # Không cap chiều cao — để Qt canvas scroll; PDF exporter sẽ cap riêng
    fig_height = max(n * _ROW_HEIGHT_INCH + 1.5, 4.0)
    fig_width = 14.0

    # Font size co giãn theo số hàng
    if n <= 30:
        label_fs = 9
    elif n <= 60:
        label_fs = 8
    else:
        label_fs = 7

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    fig.patch.set_facecolor("#FAFBFC")
    ax.set_facecolor("#FAFBFC")

    md_starts = mdates.date2num(starts)
    md_finishes = mdates.date2num(finishes)
    durations = md_finishes - md_starts
    y_pos = list(range(n))

    bar_h_normal = min(0.55, _ROW_HEIGHT_INCH * 0.72)
    bar_h_summary = min(0.70, _ROW_HEIGHT_INCH * 0.90)

    for idx in range(n):
        if milestone_flags[idx]:
            ax.plot(
                md_starts[idx], y_pos[idx],
                marker="D", color="#FFD966", markersize=8,
                markeredgecolor="#B8860B", markeredgewidth=1.2,
                zorder=5,
            )
        else:
            bh = bar_h_summary if summary_flags[idx] else bar_h_normal
            ec = "#2E4B70" if summary_flags[idx] else "none"
            lw = 0.7 if summary_flags[idx] else 0
            ax.barh(
                y_pos[idx], durations[idx],
                left=md_starts[idx],
                height=bh,
                color=colors[idx],
                edgecolor=ec,
                linewidth=lw,
                zorder=3,
            )

    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=label_fs)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=8)

    ax.grid(axis="x", linestyle="--", alpha=0.35, color="#AAAAAA")
    ax.set_axisbelow(True)

    # Đường kẻ phân cách hàng
    for y in y_pos:
        ax.axhline(y=y - 0.5, color="#E8ECF0", linewidth=0.5, zorder=1)

    # Tiêu đề + chú thích khi đang filter
    subtitle = ""
    if summary_only and len(all_tasks) > len(tasks):
        subtitle = f"  (hiển thị {n}/{len(all_tasks)} tasks — chỉ summary/milestone)"
    title = f"Gantt Chart — {project_data.name}{subtitle}"
    ax.set_title(title, fontsize=11, fontweight="bold", pad=12, color="#2E5C8A")

    ax.set_ylim(-0.8, n - 0.2)
    fig.tight_layout(pad=1.2)
    return fig


def build_gantt_figure_for_pdf(project_data: ProjectData) -> matplotlib.figure.Figure:
    """
    Phiên bản dành riêng cho PDF — cap chiều cao tối đa 14 inch để vừa A4.
    """
    fig = build_gantt_figure(project_data, summary_only=None)
    w, h = fig.get_size_inches()
    if h > 14.0:
        fig.set_size_inches(w, 14.0)
        fig.tight_layout(pad=1.2)
    return fig
