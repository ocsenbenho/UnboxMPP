import os
from pathlib import Path
from core.mpp_reader import read_mpp
from exporters.excel_exporter import ExcelExporter
from exporters.pdf_exporter import PdfExporter

# Set JAVA_HOME automatically if needed for the test session
import sys
if sys.platform == "darwin" and "JAVA_HOME" not in os.environ:
    if os.path.exists("/opt/homebrew/opt/openjdk"):
        os.environ["JAVA_HOME"] = "/opt/homebrew/opt/openjdk"


def test_integration_mpp_conversion():
    mpp_path = "tests/sample_files/sample.mpp"
    assert os.path.exists(mpp_path), "Sample MPP file should exist for integration testing"

    # 1. Read the MPP file
    project_data = read_mpp(mpp_path)
    assert project_data.name == "budget-test-2"
    assert len(project_data.tasks) == 2
    assert len(project_data.resources) == 5
    assert len(project_data.assignments) == 5

    # Create temporary output directory inside workspace
    output_dir = Path("tests/out_test")
    output_dir.mkdir(parents=True, exist_ok=True)

    excel_output = output_dir / "report.xlsx"
    pdf_output = output_dir / "report.pdf"

    # Clean up old files if they exist
    if excel_output.exists():
        excel_output.unlink()
    if pdf_output.exists():
        pdf_output.unlink()

    # 2. Export to Excel
    excel_exporter = ExcelExporter(project_data)
    excel_exporter.export(str(excel_output))
    assert excel_output.exists(), "Excel file should be created"
    assert excel_output.stat().st_size > 0, "Excel file should not be empty"

    # 3. Export to PDF
    pdf_exporter = PdfExporter(project_data)
    pdf_exporter.export(str(pdf_output))
    assert pdf_output.exists(), "PDF file should be created"
    assert pdf_output.stat().st_size > 0, "PDF file should not be empty"

    # Clean up output files
    excel_output.unlink()
    pdf_output.unlink()
    output_dir.rmdir()
