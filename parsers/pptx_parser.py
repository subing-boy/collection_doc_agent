"""
==============================================================================
模块名称: parsers/pptx_parser.py
功能描述: PowerPoint 演示文稿 (.pptx) 逐页解析器
          将 PPT 的每一页 (Slide) 转化为原子切片 Chunk，
          提取元素包括：标题、正文文本框、表格矩阵数据、演讲者备注 (Notes)。
可移植性: 基于官方 python-pptx 库，代码含多重空值防护。
==============================================================================
"""

from pathlib import Path
from typing import List, Optional
import pptx
from pptx.enum.shapes import MSO_SHAPE_TYPE

from parsers.base_parser import BaseParser, DocumentChunk, ParsedDocument


class PPTXParser(BaseParser):
    """
    PowerPoint (.pptx) 格式解析器
    按 '1 Slide = 1 Chunk' 的高内聚原则切片，保证溯源时精准定位到幻灯片页码
    """

    def supports(self, file_path: Path) -> bool:
        """检查文件后缀是否为 .pptx"""
        return file_path.suffix.lower() in [".pptx"]

    def parse(self, file_path: Path, doc_id: Optional[str] = None) -> ParsedDocument:
        """
        解析 PPTX 文件并生成切片列表
        """
        file_path = Path(file_path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"未找到指定的 PPTX 文件: {file_path}")

        document_id = doc_id or self.generate_id()
        prs = pptx.Presentation(str(file_path))

        chunks: List[DocumentChunk] = []
        preview_texts: List[str] = []

        # 遍历每一页幻灯片 (序号从 1 开始)
        for idx, slide in enumerate(prs.slides, start=1):
            slide_title = ""
            body_texts: List[str] = []
            table_texts: List[str] = []
            notes_text = ""

            # 1. 尝试提取幻灯片自带的标题 Shape
            if slide.shapes.title and slide.shapes.title.has_text_frame:
                slide_title = slide.shapes.title.text.strip()

            # 2. 遍历幻灯片中的所有形状 (文本框、表格等)
            for shape in slide.shapes:
                # 排除已经作为主标题提取过的形状
                if shape == slide.shapes.title:
                    continue

                # 提取普通文本框
                if shape.has_text_frame:
                    text = shape.text.strip()
                    if text:
                        # 如果前面未找到标题，拿首个短文本作为标题候选
                        if not slide_title and len(text) < 30:
                            slide_title = text
                        else:
                            body_texts.append(text)

                # 提取表格内容 (转换为 Markdown 表格格式，保留数据对齐结构)
                elif shape.has_table:
                    table_md = self._parse_table(shape.table)
                    if table_md:
                        table_texts.append(table_md)

            # 3. 提取演讲者备注 (Speaker Notes)
            try:
                if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                    raw_notes = slide.notes_slide.notes_text_frame.text.strip()
                    if raw_notes:
                        notes_text = raw_notes
            except Exception:
                # 部分损坏或特殊版式的备注静默跳过
                pass

            # 4. 组装当前幻灯片的结构化正文
            title_display = slide_title if slide_title else "未命名幻灯片"
            content_parts = [f"【幻灯片标题】: {title_display}"]

            if body_texts:
                content_parts.append("【正文要点】:\n" + "\n".join(body_texts))

            if table_texts:
                content_parts.append("【表格数据】:\n" + "\n\n".join(table_texts))

            if notes_text:
                content_parts.append(f"【演讲者备注】: {notes_text}")

            full_slide_content = "\n\n".join(content_parts)

            # 5. 构造切片对象
            chunk = DocumentChunk(
                chunk_id=self.generate_id(),
                doc_id=document_id,
                source_filename=file_path.name,
                chunk_type="slide",
                page_or_slide=idx,
                location_label=f"第{idx}页 ({title_display})",
                content=full_slide_content
            )
            chunks.append(chunk)

            # 收集用于大模型分类的前情提要预览
            if len("".join(preview_texts)) < 1200:
                preview_texts.append(f"[P{idx}] {title_display}: {' '.join(body_texts[:2])}")

        full_preview = "\n".join(preview_texts)

        return ParsedDocument(
            doc_id=document_id,
            filename=file_path.name,
            file_type="pptx",
            total_pages=len(prs.slides),
            full_text_preview=full_preview,
            chunks=chunks
        )

    @staticmethod
    def _parse_table(table) -> str:
        """
        将 PPT 表格转换为清晰的 Markdown 表格文本
        """
        rows_data = []
        for row in table.rows:
            cell_texts = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            rows_data.append(cell_texts)

        if not rows_data:
            return ""

        lines = []
        # 表头
        lines.append("| " + " | ".join(rows_data[0]) + " |")
        lines.append("| " + " | ".join(["---"] * len(rows_data[0])) + " |")
        # 数据行
        for row in rows_data[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)
