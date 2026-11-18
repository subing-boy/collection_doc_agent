"""
==============================================================================
模块名称: generators/__init__.py
功能描述: 逆向生成引擎对外导出
==============================================================================
"""

from generators.doc_generator import DocGenerator
from generators.ppt_generator import PPTGenerator

__all__ = ["DocGenerator", "PPTGenerator"]
