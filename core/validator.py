"""
validator.py — Logic validate dung chung truoc khi doc file hoac xuat file.

Tach rieng khoi mpp_reader.py de de unit test doc lap (khong can mock MPXJ).
"""

from pathlib import Path


def validate_input_file(file_path: str) -> None:
    """
    Validate file .mpp dau vao truoc khi doc.

    Raises:
        FileNotFoundError: file khong ton tai
        ValueError: sai dinh dang duoi file
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File khong ton tai: {file_path}")
    if not path.is_file():
        raise ValueError(f"Duong dan khong phai file: {file_path}")
    if path.suffix.lower() != ".mpp":
        raise ValueError(f"File phai co duoi .mpp, nhan duoc: {path.suffix}")


def validate_output_directory(dir_path: str) -> None:
    """Dam bao thu muc output ton tai, tao moi neu chua co."""
    Path(dir_path).mkdir(parents=True, exist_ok=True)
