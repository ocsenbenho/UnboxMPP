"""
pdf_exporter.py — Xuất ProjectData ra file PDF bằng reportlab.

Cấu trúc PDF:
  Trang 1     — thông tin tổng quan project
  Trang 2..n  — bảng task list (auto ngắt trang, header lặp lại)
  Trang cuối  — Gantt chart visual
"""

import tempfile
from pathlib import Path

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for headless rendering
import matplotlib.pyplot as plt

from core.gantt_renderer import build_gantt_figure_for_pdf
from core.font_utils import register_fonts, FONT_REGULAR, FONT_BOLD

# Đăng ký font Unicode cho reportlab và matplotlib ngay khi import module
register_fonts()

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image

from core.data_model import ProjectData
from exporters.base_exporter import BaseExporter


class PdfExporter(BaseExporter):
    def export(self, output_path: str) -> None:
        self.validate_output_path(output_path, ".pdf")

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2.5 * cm,
            bottomMargin=2.5 * cm,
        )

        story = []
        story.extend(self._build_summary_page())
        story.extend(self._build_task_table())

        gantt_image_path = self._build_gantt_image()
        story.extend(self._build_gantt_page(gantt_image_path))

        doc.build(
            story,
            onFirstPage=self._draw_header_footer,
            onLaterPages=self._draw_header_footer,
        )

        # Cleanup file ảnh Gantt tạm sau khi build xong
        if gantt_image_path and Path(gantt_image_path).exists():
            Path(gantt_image_path).unlink()

    def _build_summary_page(self) -> list:
        """
        Trang tổng quan gồm:
        - Tên project
        - Start date / Finish date
        - Tổng số task, milestone, resource
        - PageBreak() ở cuối
        """
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'SummaryTitle',
            parent=styles['Heading1'],
            fontSize=26,
            leading=32,
            textColor=HexColor("#2E5C8A"),
            spaceAfter=20
        )
        
        meta_label_style = ParagraphStyle(
            'MetaLabel',
            parent=styles['Normal'],
            fontSize=11,
            leading=15,
            textColor=HexColor("#555555"),
            fontName=FONT_BOLD
        )
        
        meta_value_style = ParagraphStyle(
            'MetaValue',
            parent=styles['Normal'],
            fontSize=11,
            leading=15,
            fontName=FONT_REGULAR,
            textColor=HexColor("#222222")
        )

        story = [
            Spacer(1, 3 * cm),
            Paragraph("BÁO CÁO TỔNG QUAN DỰ ÁN", title_style),
            Paragraph(f"Dự án: {self.project_data.name}", ParagraphStyle('ProjName', parent=styles['Heading2'], fontSize=15, leading=19, spaceAfter=20)),
            Spacer(1, 1 * cm)
        ]

        start_str = self.project_data.start_date.strftime("%Y-%m-%d") if self.project_data.start_date else "N/A"
        finish_str = self.project_data.finish_date.strftime("%Y-%m-%d") if self.project_data.finish_date else "N/A"
        
        data = [
            [Paragraph("Ngày bắt đầu (Start Date):", meta_label_style), Paragraph(start_str, meta_value_style)],
            [Paragraph("Ngày kết thúc (Finish Date):", meta_label_style), Paragraph(finish_str, meta_value_style)],
            [Paragraph("Tổng số Tasks:", meta_label_style), Paragraph(str(self.project_data.task_count), meta_value_style)],
            [Paragraph("Tổng số Milestones:", meta_label_style), Paragraph(str(self.project_data.milestone_count), meta_value_style)],
            [Paragraph("Số lượng Resources:", meta_label_style), Paragraph(str(len(self.project_data.resources)), meta_value_style)]
        ]

        table = Table(data, colWidths=[6 * cm, 11 * cm])
        table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, HexColor("#EEEEEE")),
        ]))
        
        story.append(table)
        story.append(PageBreak())
        return story

    def _build_task_table(self) -> list:
        """
        Bảng task list bằng reportlab Table:
        - Header row: Name, Start, Finish, Duration, % Complete
        - Indent tên task theo outline_level
        - Bold summary tasks. Highlight milestone rows.
        - RepeatRows=1 để header lặp lại mỗi khi ngắt trang.
        """
        styles = getSampleStyleSheet()
        story = [
            Paragraph("Danh Sách Công Việc (Task List)", ParagraphStyle('ListTitle', parent=styles['Heading2'], fontSize=15, leading=19, textColor=HexColor("#2E5C8A"), spaceAfter=15))
        ]

        header = ["Tên công việc (Name)", "Bắt đầu", "Kết thúc", "Duration", "% Hoàn thành"]
        table_data = [header]

        for task in self.project_data.tasks:
            # Indent tên công việc theo outline_level
            task_name_style = ParagraphStyle(
                f'TaskName_{task.id}',
                parent=styles['Normal'],
                fontSize=8.5,
                leading=10.5,
                leftIndent=task.outline_level * 12
            )
            if task.is_summary:
                task_name_style.fontName = FONT_BOLD
                task_name_style.fontSize = 9
                task_name_style.leading = 11

            name_p = Paragraph(task.name, task_name_style)
            
            start_str = task.start.strftime("%Y-%m-%d") if task.start else ""
            finish_str = task.finish.strftime("%Y-%m-%d") if task.finish else ""
            duration_str = f"{task.duration_days:.2f}d" if task.duration_hours else "0.00d"
            percent_str = f"{int(task.percent_complete)}%"

            cell_style = ParagraphStyle(
                f'Cell_{task.id}',
                parent=styles['Normal'],
                fontSize=8.5,
                leading=10.5,
                alignment=1 if not task.is_summary else 0  # Căn giữa ngoại trừ cột Name
            )
            if task.is_summary:
                cell_style.fontName = FONT_BOLD

            table_data.append([
                name_p,
                Paragraph(start_str, cell_style),
                Paragraph(finish_str, cell_style),
                Paragraph(duration_str, cell_style),
                Paragraph(percent_str, cell_style)
            ])

        # A4 width (21cm) - margins (4cm) = 17cm
        col_widths = [7.5 * cm, 2.5 * cm, 2.5 * cm, 2.3 * cm, 2.2 * cm]
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        t_style = [
            ('BACKGROUND', (0,0), (-1,0), HexColor("#2E5C8A")),
            ('TEXTCOLOR', (0,0), (-1,0), HexColor("#FFFFFF")),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), FONT_BOLD),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('BOTTOMPADDING', (0,0), (-1,0), 6),
            ('TOPPADDING', (0,0), (-1,0), 6),
            ('GRID', (0,0), (-1,-1), 0.5, HexColor("#DDDDDD")),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]

        for idx, task in enumerate(self.project_data.tasks, start=1):
            if task.is_milestone:
                t_style.append(('BACKGROUND', (0, idx), (-1, idx), HexColor("#FFD966")))
            elif task.is_summary:
                t_style.append(('BACKGROUND', (0, idx), (-1, idx), HexColor("#F5F5F5")))
                
            t_style.append(('TOPPADDING', (0, idx), (-1, idx), 4))
            t_style.append(('BOTTOMPADDING', (0, idx), (-1, idx), 4))

        t.setStyle(TableStyle(t_style))
        story.append(t)
        story.append(PageBreak())
        return story

    def _build_gantt_image(self) -> str:
        """Vẽ Gantt chart bằng gantt_renderer.build_gantt_figure() và lưu ra file PNG tạm."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        fig = build_gantt_figure_for_pdf(self.project_data)
        fig.savefig(tmp_path, dpi=150, bbox_inches='tight')
        plt.close(fig)

        return tmp_path

    def _build_gantt_page(self, image_path: str) -> list:
        """Chèn ảnh Gantt vào 1 trang PDF mới, scale vừa khổ A4."""
        if not image_path or not Path(image_path).exists():
            return []
            
        styles = getSampleStyleSheet()
        story = [
            Paragraph("Biểu Đồ Gantt (Gantt Chart)", ParagraphStyle('GanttTitle', parent=styles['Heading2'], fontSize=15, leading=19, textColor=HexColor("#2E5C8A"), spaceAfter=15)),
            Spacer(1, 0.5 * cm)
        ]
        
        # Scale theo chiều cao tối đa của vùng in
        tasks_count = len(self.project_data.tasks)
        calc_height = max(tasks_count * 0.35 + 2, 4) * cm
        img_height = min(calc_height, 19 * cm)
        
        img = Image(image_path, width=17 * cm, height=img_height)
        story.append(img)
        return story

    def _draw_header_footer(self, canvas, doc) -> None:
        """Vẽ header (tên project) và footer (số trang) trên mỗi trang."""
        canvas.saveState()
        canvas.setFont(FONT_REGULAR, 8)
        canvas.setFillColor(HexColor("#666666"))
        
        # Header
        canvas.drawString(2 * cm, 28 * cm, f"Dự án: {self.project_data.name}")
        canvas.setStrokeColor(HexColor("#CCCCCC"))
        canvas.setLineWidth(0.5)
        canvas.line(2 * cm, 27.8 * cm, 19 * cm, 27.8 * cm)
        
        # Footer
        canvas.drawCentredString(10.5 * cm, 1.2 * cm, f"Trang {doc.page}")
        canvas.restoreState()

