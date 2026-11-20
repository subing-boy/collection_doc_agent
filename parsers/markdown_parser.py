"""
==============================================================================
模块名称: parsers/markdown_parser.py
功能描述: Markdown (.md) 与纯文本 (.txt) 结构化解析器
          基于 Python 内置文本处理，零外部三方依赖：
          1. 自动识别 `#` 标题层级 (H1/H2/H3/H4)，构建面包屑路径；
          2. 按章节与语义段落切片，每片携带完整标题坐标；
          3. 出处坐标精确标注至标题层级 (如: '1. 设备设计总览 > 1.2 硬件接口规范')；
          4. 纯文本文件 (.txt) 自动降级为语义段落分块。
==============================================================================
"""

import re
from pathlib import Path
from typing import List, Optional

from parsers.base_parser import BaseParser, DocumentChunk, ParsedDocument


class MarkdownParser(BaseParser):
    """
    Markdown (.md, .markdown) 与纯文本 (.txt) 格式解析器
    """

    def supports(self, file_path: Path) -> bool:
        """检查文件后缀是否为 Markdown 或纯文本"""
        return file_path.suffix.lower() in [".md", ".markdown", ".txt"]

    def parse(self, file_path: Path, doc_id: Optional[str] = None) -> ParsedDocument:
        """
        解析 Markdown 或文本文件并生成携带章节面包屑的切片列表
        """
        file_path = Path(file_path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"未找到指定的文档文件: {file_path}")

        document_id = doc_id or self.generate_id()
        chunks: List[DocumentChunk] = []

        # 尝试使用 utf-8 读取，遇到异常则降级为 gbk
        try:
            raw_content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw_content = file_path.read_text(encoding="gbk", errors="ignore")

        lines = raw_content.splitlines()
        preview_text = raw_content[:1200].strip()

        heading_stack: List[str] = []
        current_lines: List[str] = []
        chunk_idx = 1

        def flush_current_chunk():
            """将当前累积的段落内容导出为一个独立 Chunk"""
            nonlocal chunk_idx, current_lines
            content = "\n".join(current_lines).strip()
            if not content:
                current_lines = []
                return

            location = " > ".join(heading_stack) if heading_stack else f"第{chunk_idx}部分"
            chunk_content = f"【章节位置】: {location}\n\n{content}"

            chunks.append(DocumentChunk(
                chunk_id=self.generate_id(),
                doc_id=document_id,
                source_filename=file_path.name,
                chunk_type="markdown_section",
                page_or_slide=chunk_idx,
                location_label=location,
                content=chunk_content
            ))
            chunk_idx += 1
            current_lines = []

        # 逐行扫描标题与段落
        for line in lines:
            line_stripped = line.strip()

            # 匹配 Markdown 标题：如 # 标题, ## 标题
            heading_match = re.match(r'^(#{1,4})\s+(.+)$', line_stripped)
            if heading_match:
                # 遇到新标题，先将上一章节内容刷新出块
                flush_current_chunk()

                level = len(heading_match.group(1))  # 1~4 级
                heading_title = heading_match.group(2).strip()

                # 维护章节面包屑栈
                if level == 1:
                    heading_stack = [heading_title]
                elif level == 2:
                    if len(heading_stack) >= 1:
                        heading_stack = [heading_stack[0], heading_title]
                    else:
                        heading_stack = [heading_title]
                elif level == 3:
                    if len(heading_stack) >= 2:
                        heading_stack = [heading_stack[0], heading_stack[1], heading_title]
                    else:
                        heading_stack.append(heading_title)
                else:
                    if len(heading_stack) >= 3:
                        heading_stack = [heading_stack[0], heading_stack[1], heading_stack[2], heading_title]
                    else:
                        heading_stack.append(heading_title)
            else:
                current_lines.append(line)
                # 如果当前小节内容过长 (>800字)，按段落切分出块
                if sum(len(l) for l in current_lines) >= 800 and not line_stripped:
                    flush_current_chunk()

        # 刷新最后剩余内容
        flush_current_chunk()

        # 如果全文完全没有匹配到任何标题（如普通纯文本文件），按固定字数兜底分块
        if not chunks and raw_content.strip():
            chunks.append(DocumentChunk(
                chunk_id=self.generate_id(),
                doc_id=document_id,
                source_filename=file_path.name,
                chunk_type="text_block",
                page_or_slide=1,
                location_label="全文内容",
                content=f"【文档名称】: {file_path.name}\n\n{raw_content.strip()}"
            ))

        return ParsedDocument(
            doc_id=document_id,
            filename=file_path.name,
            file_type=file_path.suffix.lstrip(".").lower() or "txt",
            total_pages=len(chunks),
            full_text_preview=preview_text,
            chunks=chunks
        )
