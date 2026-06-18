"""
font_utils.py — Tìm và đăng ký font Unicode cho reportlab + matplotlib.

Mục tiêu: giữ đúng ký tự tiếng Việt (và mọi ngôn ngữ Latin extended) khi
xuất PDF và vẽ Gantt chart, không bị mất dấu hay hiện ký tự lạ.

Chiến lược tìm font (ưu tiên theo thứ tự):
  1. Arial (hỗ trợ đầy đủ tiếng Việt) — macOS Supplemental fonts
  2. DejaVu Sans (bundled sẵn với matplotlib, bao gồm Latin Extended-Additional)
  3. Liberation Sans / FreeSans — Linux
"""

import sys
import logging
from pathlib import Path

import matplotlib.font_manager as fm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

# Tên nội bộ dùng trong reportlab
FONT_REGULAR = "UniFont"
FONT_BOLD = "UniFont-Bold"

# Cờ đảm bảo chỉ đăng ký một lần
_registered = False


def _candidate_pairs() -> list[tuple[str, str]]:
    """Trả về danh sách (regular_path, bold_path) theo ưu tiên nền tảng."""
    if sys.platform == "darwin":
        sup = Path("/System/Library/Fonts/Supplemental")
        return [
            (str(sup / "Arial.ttf"), str(sup / "Arial Bold.ttf")),
        ]
    if sys.platform == "win32":
        win = Path(r"C:\Windows\Fonts")
        return [
            (str(win / "arial.ttf"), str(win / "arialbd.ttf")),
            (str(win / "times.ttf"), str(win / "timesbd.ttf")),
        ]
    # Linux
    return [
        (
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ),
        (
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ),
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
    ]


def _find_dejavu() -> tuple[str, str]:
    """Trả về đường dẫn DejaVu Sans regular và bold (luôn có sẵn với matplotlib)."""
    regular = fm.findfont("DejaVu Sans", fallback_to_default=True)
    bold = fm.findfont("DejaVu Sans:bold", fallback_to_default=True)
    # Nếu fm trả về cùng một file (không có bold riêng), dùng regular cho cả hai
    return regular, bold


def register_fonts() -> None:
    """
    Đăng ký font Unicode với reportlab (chỉ chạy một lần).

    Sau khi gọi hàm này:
      - reportlab có thể dùng tên 'UniFont' và 'UniFont-Bold'
      - matplotlib được cấu hình để dùng cùng font (qua rcParams)
    """
    global _registered
    if _registered:
        return

    chosen_regular: str | None = None
    chosen_bold: str | None = None

    # Thử các font system theo ưu tiên
    for reg_path, bold_path in _candidate_pairs():
        if Path(reg_path).exists() and Path(bold_path).exists():
            chosen_regular = reg_path
            chosen_bold = bold_path
            logger.debug("Unicode font found: %s", reg_path)
            break

    # Fallback về DejaVu Sans (luôn đi kèm matplotlib)
    if chosen_regular is None:
        chosen_regular, chosen_bold = _find_dejavu()
        logger.debug("Using DejaVu Sans as fallback: %s", chosen_regular)

    # Đăng ký vào reportlab
    try:
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, chosen_regular))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, chosen_bold))
        logger.debug("Reportlab fonts registered: %s / %s", FONT_REGULAR, FONT_BOLD)
    except Exception as exc:
        logger.warning("Font registration failed (%s); falling back to DejaVu", exc)
        reg, bold = _find_dejavu()
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, reg))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, bold))

    # Cấu hình matplotlib cùng font
    import matplotlib as mpl
    font_name = Path(chosen_regular).stem  # e.g. "Arial" hoặc "DejaVuSans"
    mpl.rcParams["font.family"] = "sans-serif"
    # Thêm tên font vào đầu danh sách ưu tiên, giữ DejaVu Sans làm fallback
    mpl.rcParams["font.sans-serif"] = [
        font_name,
        "DejaVu Sans",
        "Arial",
        "Liberation Sans",
        "sans-serif",
    ]
    # Tắt cảnh báo "Glyph X missing from current font"
    import logging as _logging
    _logging.getLogger("matplotlib.font_manager").setLevel(_logging.ERROR)

    _registered = True
