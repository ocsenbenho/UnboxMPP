"""
main.py — CLI entry point cho tool mpp-convert.

Cách dùng:
    python main.py input.mpp --format excel --output report.xlsx
    python main.py input.mpp --format pdf --output report.pdf
    python main.py input.mpp --format both --output-dir ./out/
"""

import argparse
import logging
import sys
from pathlib import Path

from core.mpp_reader import MppReadError, read_mpp
from exporters.excel_exporter import ExcelExporter
from exporters.pdf_exporter import PdfExporter


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mpp-convert",
        description="Chuyển đổi file Microsoft Project (.mpp) sang Excel hoặc PDF.",
    )
    parser.add_argument("input", help="Đường dẫn file .mpp đầu vào")
    parser.add_argument(
        "--format",
        choices=["excel", "pdf", "both"],
        required=True,
        help="Định dạng output mong muốn",
    )
    parser.add_argument(
        "--output",
        help="Đường dẫn file output (bắt buộc khi --format là excel hoặc pdf)",
    )
    parser.add_argument(
        "--output-dir",
        help="Thư mục output (bắt buộc khi --format là both)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="In log chi tiết quá trình đọc/convert",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger(__name__)

    # --- Validate tham số output theo format đã chọn ---
    if args.format in ("excel", "pdf") and not args.output:
        parser.error(f"--output là bắt buộc khi --format={args.format}")
    if args.format == "both" and not args.output_dir:
        parser.error("--output-dir là bắt buộc khi --format=both")

    # --- Đọc file .mpp ---
    try:
        logger.info("Đang đọc file: %s", args.input)
        project_data = read_mpp(args.input)
        logger.info(
            "Đọc thành công: %d task, %d milestone, %d resource",
            project_data.task_count,
            project_data.milestone_count,
            len(project_data.resources),
        )
    except MppReadError as exc:
        logger.error("Lỗi đọc file: %s", exc)
        return 1

    # --- Xuất file theo format được chọn ---
    try:
        if args.format == "excel":
            ExcelExporter(project_data).export(args.output)
            logger.info("Đã xuất Excel: %s", args.output)

        elif args.format == "pdf":
            PdfExporter(project_data).export(args.output)
            logger.info("Đã xuất PDF: %s", args.output)

        elif args.format == "both":
            output_dir = Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            base_name = Path(args.input).stem

            excel_path = output_dir / f"{base_name}.xlsx"
            pdf_path = output_dir / f"{base_name}.pdf"

            ExcelExporter(project_data).export(str(excel_path))
            logger.info("Đã xuất Excel: %s", excel_path)

            PdfExporter(project_data).export(str(pdf_path))
            logger.info("Đã xuất PDF: %s", pdf_path)

    except Exception as exc:  # noqa: BLE001 — refine exception type cụ thể khi implement exporter
        logger.exception("Lỗi khi xuất file")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
