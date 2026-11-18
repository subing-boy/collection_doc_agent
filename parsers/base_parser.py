"""
==============================================================================
模块名称: parsers/base_parser.py
功能描述: 文档解析器抽象基类与数据契约定义
          标准化解析输出，确保 PPTX 幻灯片与 DOCX 章节切片均携带完整溯源元数据
          （源文件名、页码、章节层级标签、切片唯一 ID）。
可移植性: 仅使用 Python 内置 dataclasses 与 typing 模块。
==============================================================================
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional


@dataclass
class DocumentChunk:
    """
    单个文本切片数据契约 (Chunk)
    RAG 检索与溯源问答的原子单位
    """
    chunk_id: str                      # 切片全局唯一 ID (UUID)
    doc_id: str                        # 所属文档 ID
    source_filename: str               # 来源原始文件名 (如: 架构设计.pptx)
    chunk_type: str                    # 切片类型: "slide" (幻灯片) 或 "section" (章节段落)
    page_or_slide: int                 # 物理页码或幻灯片序号 (从 1 开始)
    location_label: str                # 定位面包屑 (如: "第3页 (技术架构)" 或 "1.2 核心模块")
    content: str                       # 切片具体文本内容
    vector: Optional[List[float]] = field(default=None)  # 对应的向量表示

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示"""
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "source_filename": self.source_filename,
            "chunk_type": self.chunk_type,
            "page_or_slide": self.page_or_slide,
            "location_label": self.location_label,
            "content": self.content,
            "vector": self.vector
        }


@dataclass
class ParsedDocument:
    """
    整篇文档解析后的结构化产物
    """
    doc_id: str                        # 文档唯一 ID
    filename: str                      # 文件名
    file_type: str                     # 文件扩展名 (pptx / docx 等)
    total_pages: int                   # 总页数或总章节数
    full_text_preview: str             # 前 1000 字符文本预览 (用于大模型智能分类与打标)
    chunks: List[DocumentChunk]        # 切分好的知识切片列表


class BaseParser(ABC):
    """
    文档解析器抽象基类 (Interface)
    """

    @abstractmethod
    def supports(self, file_path: Path) -> bool:
        """
        判断当前解析器是否支持处理该文件类型
        """
        pass

    @abstractmethod
    def parse(self, file_path: Path, doc_id: Optional[str] = None) -> ParsedDocument:
        """
        执行文件解析与知识切片提取
        :param file_path: 本地文件路径
        :param doc_id: 文档 ID，如不提供则自动生成 UUID
        :return: 结构化解析产物 ParsedDocument
        """
        pass

    @staticmethod
    def generate_id() -> str:
        """生成唯一标识 UUID"""
        return str(uuid.uuid4())
