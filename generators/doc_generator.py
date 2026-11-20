"""
==============================================================================
模块名称: generators/doc_generator.py
功能描述: Word 文档 (.docx) 逆向生成器
          基于结构化提纲或 Markdown 风格文本，自动生成排版规范、样式统一的 Word 文档。
          支持主副标题、章节层级 (H1/H2)、要点列表及数据表格渲染。
可移植性: 依赖 python-docx，零其他第三方依赖。
==============================================================================
"""

from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

import config


class DocGenerator:
    """
    Word 文档生成器
    负责将 Agent 总结与整合出的知识内容导出为专业格式的 .docx
    """

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self.output_dir = output_dir or config.OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_document(
        self,
        title: str,
        sections: List[Dict[str, Any]],
        output_filename: Optional[str] = None,
        output_dir: Optional[Path] = None
    ) -> Path:
        """
        根据结构化章节数据生成并导出 Word 文档
        
        :param title: 文档主标题
        :param sections: 章节列表
        :param output_filename: 指定导出文件名，如不提供则自动以时间戳命名
        :param output_dir: 指定保存目录 (可选，默认使用 self.output_dir)
        :return: 生成的 docx 文件绝对路径
        """
        doc = docx.Document()

        # 1. 页面边距设置 (上/下/左/右各 1 英寸)
        for section in doc.sections:
            section.top_margin = Inches(1.0)
            section.bottom_margin = Inches(1.0)
            section.left_margin = Inches(1.0)
            section.right_margin = Inches(1.0)

        # 2. 渲染主标题 (Title)
        title_para = doc.add_paragraph()
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_run = title_para.add_run(title)
        title_run.font.name = "Microsoft YaHei"
        title_run.font.size = Pt(22)
        title_run.font.bold = True
        title_run.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)  # 深青石灰

        # 3. 渲染副标题与生成元信息
        meta_para = doc.add_paragraph()
        meta_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        meta_run = meta_para.add_run(f"由『个人文档管家 Agent』智能生成  |  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        meta_run.font.name = "Microsoft YaHei"
        meta_run.font.size = Pt(9.5)
        meta_run.font.italic = True
        meta_run.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)

        doc.add_paragraph()  # 留白空行

        # 4. 遍历各个章节渲染正文
        for sec in sections:
            heading_text = sec.get("heading", "")
            level = sec.get("level", 1)

            if heading_text:
                h = doc.add_heading(heading_text, level=min(level, 3))
                h_run = h.runs[0] if h.runs else h.add_run()
                h_run.font.name = "Microsoft YaHei"
                h_run.font.bold = True
                if level == 1:
                    h_run.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)  # 科技深蓝
                else:
                    h_run.font.color.rgb = RGBColor(0x37, 0x41, 0x51)

            # 段落渲染
            for p_text in sec.get("paragraphs", []):
                p = doc.add_paragraph()
                p.paragraph_format.line_spacing = 1.25
                p.paragraph_format.space_after = Pt(6)
                p_run = p.add_run(p_text)
                p_run.font.name = "Microsoft YaHei"
                p_run.font.size = Pt(10.5)

            # 项目符号要点渲染
            for b_text in sec.get("bullet_points", []):
                bp = doc.add_paragraph(style='List Bullet')
                bp.paragraph_format.line_spacing = 1.2
                bp.paragraph_format.space_after = Pt(3)
                bp_run = bp.add_run(b_text)
                bp_run.font.name = "Microsoft YaHei"
                bp_run.font.size = Pt(10)

            # 表格渲染
            table_data = sec.get("table_data")
            if table_data and len(table_data) > 0:
                self._render_table(doc, table_data)

            doc.add_paragraph()  # 章节间空行分隔

        # 5. 确定保存文件名并导出
        if not output_filename:
            clean_title = "".join(c for c in title if c.isalnum() or c in ("-", "_")).strip()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{clean_title or '智能文档'}_{timestamp}.docx"

        if not output_filename.endswith(".docx"):
            output_filename += ".docx"

        save_dir = Path(output_dir).resolve() if output_dir else self.output_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        target_path = save_dir / output_filename
        doc.save(str(target_path))
        return target_path

    @staticmethod
    def _render_table(doc: docx.Document, table_data: List[List[str]]) -> None:
        """渲染带边框和灰度表头的表格"""
        rows = len(table_data)
        cols = len(table_data[0]) if rows > 0 else 0
        if rows == 0 or cols == 0:
            return

        table = doc.add_table(rows=rows, cols=cols)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.style = 'Table Grid'

        # 填充单元格数据
        for r_idx, row_list in enumerate(table_data):
            for c_idx, cell_value in enumerate(row_list):
                cell = table.cell(r_idx, c_idx)
                cell.text = str(cell_value)
                # 针对表头加粗
                if r_idx == 0:
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            run.font.name = "Microsoft YaHei"
                            run.font.bold = True
                            run.font.size = Pt(10)
                else:
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            run.font.name = "Microsoft YaHei"
                            run.font.size = Pt(9.5)
