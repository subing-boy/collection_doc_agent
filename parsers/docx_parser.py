"""
==============================================================================
模块名称: parsers/docx_parser.py
功能描述: Word 文档 (.docx) 结构化解析器
          依据标题层级 (Heading 1/2/3) 与段落语义进行知识切片，
          自动维护章节面包屑路径（如: '1. 架构总览 > 1.2 存储设计'），
          支持自动解析表格并转换为 Markdown 格式。
可移植性: 基于官方 python-docx 库，逻辑严密，具有容错保护。
==============================================================================
"""

from pathlib import Path
from typing import List, Optional
import docx

from parsers.base_parser import BaseParser, DocumentChunk, ParsedDocument


class DOCXParser(BaseParser):
    """
    Word (.docx) 格式文档解析器
    按章节与语义段落切片，完整保留章节路径供精准溯源
    """

    def supports(self, file_path: Path) -> bool:
        """检查文件后缀是否为 .docx"""
        return file_path.suffix.lower() in [".docx"]

    def parse(self, file_path: Path, doc_id: Optional[str] = None) -> ParsedDocument:
        """
        解析 DOCX 文件并生成切片列表
        """
        file_path = Path(file_path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"未找到指定的 DOCX 文件: {file_path}")

        document_id = doc_id or self.generate_id()
        doc = docx.Document(str(file_path))

        chunks: List[DocumentChunk] = []
        preview_texts: List[str] = []

        # 维护当前的章节层级路径，例如: ["第1章 概述", "1.1 背景"]
        heading_stack: List[str] = []
        current_section_texts: List[str] = []
        section_idx = 1

        def flush_current_chunk():
            """将当前累积的段落刷新为一个独立 Chunk"""
            nonlocal section_idx, current_section_texts
            if not current_section_texts:
                return

            location = " > ".join(heading_stack) if heading_stack else f"第{section_idx}部分"
            content = "\n\n".join(current_section_texts)

            chunk = DocumentChunk(
                chunk_id=self.generate_id(),
                doc_id=document_id,
                source_filename=file_path.name,
                chunk_type="section",
                page_or_slide=section_idx,
                location_label=location,
                content=f"【章节位置】: {location}\n\n{content}"
            )
            chunks.append(chunk)
            section_idx += 1
            current_section_texts = []

        # 1. 遍历正文段落
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            style_name = para.style.name.lower() if para.style else ""

            # 判断是否是标题样式
            if "heading 1" in style_name or "title" in style_name:
                flush_current_chunk()
                heading_stack = [text]
            elif "heading 2" in style_name:
                flush_current_chunk()
                if len(heading_stack) >= 1:
                    heading_stack = [heading_stack[0], text]
                else:
                    heading_stack = [text]
            elif "heading 3" in style_name:
                flush_current_chunk()
                if len(heading_stack) >= 2:
                    heading_stack = [heading_stack[0], heading_stack[1], text]
                else:
                    heading_stack.append(text)
            else:
                # 普通段落内容
                current_section_texts.append(text)

                # 如果当前切片积累文本过长（>800字），切分出一段，保持检索颗粒度精细
                if sum(len(t) for t in current_section_texts) > 800:
                    flush_current_chunk()

            # 抓取文档前缀作为全局分类预览
            if len("".join(preview_texts)) < 1200:
                preview_texts.append(text)

        # 刷新最后剩余的段落
        flush_current_chunk()

        # 2. 补充提取表格内容（作为独立的数据切片加入）
        for t_idx, table in enumerate(doc.tables, start=1):
            table_md = self._parse_docx_table(table)
            if table_md:
                chunks.append(DocumentChunk(
                    chunk_id=self.generate_id(),
                    doc_id=document_id,
                    source_filename=file_path.name,
                    chunk_type="table",
                    page_or_slide=section_idx,
                    location_label=f"附表{t_idx}",
                    content=f"【附表{t_idx}】:\n\n{table_md}"
                ))
                section_idx += 1

        full_preview = "\n".join(preview_texts)

        return ParsedDocument(
            doc_id=document_id,
            filename=file_path.name,
            file_type="docx",
            total_pages=len(chunks),
            full_text_preview=full_preview,
            chunks=chunks
        )

    @staticmethod
    def _parse_docx_table(table) -> str:
        """
        将 Word 表格转换为 Markdown 表格格式
        """
        rows_data = []
        for row in table.rows:
            cell_texts = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            rows_data.append(cell_texts)

        if not rows_data or not rows_data[0]:
            return ""

        lines = []
        lines.append("| " + " | ".join(rows_data[0]) + " |")
        lines.append("| " + " | ".join(["---"] * len(rows_data[0])) + " |")
        for row in rows_data[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    def to_markdown(self, file_path: Path) -> str:
        """
        将 Word (.docx) 文档转录为结构化、纯净的 Markdown 文本
        保留 Heading 1/2/3 标题层级 (#, ##, ###) 和 Markdown 表格
        """
        file_path = Path(file_path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"未找到指定的 DOCX 文件: {file_path}")

        doc = docx.Document(str(file_path))
        lines: List[str] = []

        # 遍历正文段落
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            style_name = para.style.name.lower() if para.style else ""
            if "heading 1" in style_name or "title" in style_name:
                lines.append(f"\n# {text}\n")
            elif "heading 2" in style_name:
                lines.append(f"\n## {text}\n")
            elif "heading 3" in style_name:
                lines.append(f"\n### {text}\n")
            else:
                lines.append(text)

        # 转换附表为 Markdown 表格
        if doc.tables:
            for t_idx, table in enumerate(doc.tables, start=1):
                table_md = self._parse_docx_table(table)
                if table_md:
                    lines.append(f"\n### 附表 {t_idx}\n\n{table_md}\n")

        return "\n\n".join(lines).strip()
