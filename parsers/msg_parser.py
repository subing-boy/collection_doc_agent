"""
==============================================================================
模块名称: parsers/msg_parser.py
功能描述: Outlook 邮件文件 (.msg) 结构化解析器
          基于 extract-msg 实现跨平台邮件头、通信人与正文切片提取：
          1. 自动抽取邮件通信元数据 (Subject, Sender, To, Date)；
          2. 将结构化邮件通信头作为切片前置上下文，保持事实严肃性；
          3. 出处坐标精确记录至发件人、主题与发送日期；
          4. 零 Outlook 客户端依赖，在 Linux/WSL 环境下原生运行。
==============================================================================
"""

from pathlib import Path
from typing import List, Optional
import extract_msg

from parsers.base_parser import BaseParser, DocumentChunk, ParsedDocument


class MSGParser(BaseParser):
    """
    Outlook 邮件 (.msg) 格式解析器
    """

    def supports(self, file_path: Path) -> bool:
        """检查文件后缀是否为 .msg"""
        return file_path.suffix.lower() in [".msg"]

    def parse(self, file_path: Path, doc_id: Optional[str] = None) -> ParsedDocument:
        """
        解析 .msg 邮件并生成携带通信元数据的切片列表
        """
        file_path = Path(file_path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"未找到指定的邮件文件: {file_path}")

        document_id = doc_id or self.generate_id()
        chunks: List[DocumentChunk] = []

        msg = extract_msg.Message(str(file_path))

        try:
            subject = str(msg.subject or "无主题邮件").strip()
            sender = str(msg.sender or "未知发件人").strip()
            recipients = str(msg.to or "未知收件人").strip()
            date_str = str(msg.date or "未知日期").strip()
            body_text = str(msg.body or "").strip()

            header_context = (
                f"【邮件主题】: {subject}\n"
                f"【发件人】: {sender}\n"
                f"【收件人】: {recipients}\n"
                f"【发送时间】: {date_str}"
            )

            # 构造简短的日期前缀用于出处标签
            date_display = date_str[:16] if len(date_str) >= 16 else date_str
            location_label = f"发件人: {sender}, 主题: {subject[:20]}, 时间: {date_display}"

            # 分段切片：如果正文过长（>800字），进行段落切分；若短文本直接生成一个 Chunk
            paragraphs = [p.strip() for p in body_text.split("\n\n") if p.strip()]
            
            if not paragraphs:
                paragraphs = ["(邮件正文为空)"]

            current_chunk_paras: List[str] = []
            chunk_idx = 1

            for para in paragraphs:
                current_chunk_paras.append(para)
                if sum(len(p) for p in current_chunk_paras) >= 800:
                    chunk_content = f"{header_context}\n\n【邮件正文】:\n" + "\n\n".join(current_chunk_paras)
                    chunks.append(DocumentChunk(
                        chunk_id=self.generate_id(),
                        doc_id=document_id,
                        source_filename=file_path.name,
                        chunk_type="email_msg",
                        page_or_slide=chunk_idx,
                        location_label=f"{location_label} (第{chunk_idx}段)",
                        content=chunk_content
                    ))
                    chunk_idx += 1
                    current_chunk_paras = []

            if current_chunk_paras:
                chunk_content = f"{header_context}\n\n【邮件正文】:\n" + "\n\n".join(current_chunk_paras)
                label = location_label if chunk_idx == 1 else f"{location_label} (第{chunk_idx}段)"
                chunks.append(DocumentChunk(
                    chunk_id=self.generate_id(),
                    doc_id=document_id,
                    source_filename=file_path.name,
                    chunk_type="email_msg",
                    page_or_slide=chunk_idx,
                    location_label=label,
                    content=chunk_content
                ))

        finally:
            msg.close()

        full_preview = (
            f"【邮件主题】: {subject}\n"
            f"【发件人】: {sender}\n"
            f"【正文前瞻】: {body_text[:800]}"
        )

        return ParsedDocument(
            doc_id=document_id,
            filename=file_path.name,
            file_type="msg",
            total_pages=len(chunks),
            full_text_preview=full_preview,
            chunks=chunks
        )
