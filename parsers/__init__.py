"""
==============================================================================
模块名称: parsers/__init__.py
功能描述: 解析器模块对外工厂函数
          根据文件扩展名自动路由到 PPTXParser 或 DOCXParser。
==============================================================================
"""

from pathlib import Path
from parsers.base_parser import BaseParser, DocumentChunk, ParsedDocument
from parsers.pptx_parser import PPTXParser
from parsers.docx_parser import DOCXParser

_AVAILABLE_PARSERS = [
    PPTXParser(),
    DOCXParser(),
]


def get_parser_for_file(file_path: Path) -> BaseParser:
    """
    根据文件类型获取适用的文档解析器
    :param file_path: 文件路径
    :return: 对应的 BaseParser 实例
    :raises ValueError: 如果该类型尚未受支持
    """
    path_obj = Path(file_path)
    for parser in _AVAILABLE_PARSERS:
        if parser.supports(path_obj):
            return parser

    raise ValueError(
        f"不支持的文件格式: {path_obj.suffix}。\n"
        f"当前系统已支持格式: {[p.__class__.__name__ for p in _AVAILABLE_PARSERS]} (.pptx, .docx)"
    )


__all__ = [
    "BaseParser",
    "DocumentChunk",
    "ParsedDocument",
    "PPTXParser",
    "DOCXParser",
    "get_parser_for_file",
]
