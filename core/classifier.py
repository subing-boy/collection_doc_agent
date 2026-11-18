"""
==============================================================================
模块名称: core/classifier.py
功能描述: 智能文档分类与物理存储流转器
          解析文档文本后，调用大语言模型分析文档主旨，
          推荐最佳分类类别、抽取标签数组并生成一句话摘要；
          最后将文件由源目录安全迁移至 data/storage/<类别>/ 下进行持久化。
可移植性: 支持在未配置 API Key 时自动降级为基于关键词规则的本地分类，保证系统永不崩溃。
==============================================================================
"""

import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

import config
from llm.base_provider import BaseLLMProvider
from parsers.base_parser import ParsedDocument


class DocumentClassifier:
    """
    文档分类器
    结合 LLM 语义推理与规则降级双重保障
    """

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None) -> None:
        self.llm = llm_provider

    def classify_and_archive(
        self,
        source_file: Path,
        parsed_doc: ParsedDocument,
        storage_base_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        对已解析的文档进行智能归类，并将源文件安全归档至对应分类子目录下
        
        :param source_file: 原始上传/导入的文件路径
        :param parsed_doc: 解析器生成的 ParsedDocument 对象
        :param storage_base_dir: 存储根目录，默认使用 config.STORAGE_DIR
        :return: 包含 category, tags, summary, stored_path 的字典
        """
        source_file = Path(source_file).resolve()
        base_dir = storage_base_dir or config.STORAGE_DIR

        # 1. 尝试调用大模型提取元数据
        metadata = self._infer_metadata_with_llm(parsed_doc)

        category = metadata.get("category", "未分类杂项")
        tags = metadata.get("tags", [])
        summary = metadata.get("summary", "无摘要信息")

        # 2. 计算物理归档目标目录: data/storage/<category>/
        category_dir = base_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)

        target_file_path = category_dir / source_file.name

        # 3. 物理复制/迁移文件 (如果目标已存在同名文件，添加时间戳避免覆盖)
        if target_file_path.exists() and target_file_path != source_file:
            stem = source_file.stem
            suffix = source_file.suffix
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            target_file_path = category_dir / f"{stem}_{timestamp}{suffix}"

        # 执行文件拷贝保存
        if target_file_path != source_file:
            shutil.copy2(str(source_file), str(target_file_path))

        return {
            "category": category,
            "tags": tags,
            "summary": summary,
            "stored_path": str(target_file_path)
        }

    def _infer_metadata_with_llm(self, parsed_doc: ParsedDocument) -> Dict[str, Any]:
        """
        调用 LLM 推断分类与摘要，如 LLM 不可用则执行降级启发式匹配
        """
        # 如果 LLM 不可用，降级到本地规则分类
        if not self.llm or not self.llm.is_available():
            return self._heuristic_fallback(parsed_doc)

        prompt = f"""你是一个专业的文件资料管理专家。请根据以下文档的标题和内容预览，对其进行智能分类、标签提取并生成一句话精炼摘要。

【可选推荐分类】:
{json.dumps(config.DEFAULT_CATEGORIES, ensure_ascii=False)}

【待分析文档】:
文件名: {parsed_doc.filename}
内容前瞻摘要:
{parsed_doc.full_text_preview[:1000]}

【输出要求】:
必须直接返回一个合法的 JSON 对象，不要附加任何其他前后缀 Markdown 格式。
JSON 字段定义如下:
{{
    "category": "从可选分类中选取最契合的一项（如确实不契合，可自创4字以内的简短类别）",
    "tags": ["标签1", "标签2", "标签3"],
    "summary": "不超过60字的一句话内容精炼摘要"
}}
"""
        messages = [
            {"role": "system", "content": "你是一个严格输出 JSON 的文档归档助手。"},
            {"role": "user", "content": prompt}
        ]

        try:
            response_text = self.llm.chat_complete(messages, temperature=0.2, json_mode=True)
            # 解析 JSON
            clean_json = response_text.strip()
            if clean_json.startswith("```json"):
                clean_json = clean_json[7:]
            if clean_json.startswith("```"):
                clean_json = clean_json[3:]
            if clean_json.endswith("```"):
                clean_json = clean_json[:-3]
            
            data = json.loads(clean_json.strip())
            return {
                "category": data.get("category", "未分类杂项"),
                "tags": data.get("tags", []),
                "summary": data.get("summary", "")
            }
        except Exception:
            # 遇解析异常则安全回退
            return self._heuristic_fallback(parsed_doc)

    @staticmethod
    def _heuristic_fallback(parsed_doc: ParsedDocument) -> Dict[str, Any]:
        """
        本地启发式降级规则 (无需 API 密钥即可正常归档)
        """
        filename_lower = parsed_doc.filename.lower()
        preview = parsed_doc.full_text_preview.lower()

        if any(k in filename_lower or k in preview for k in ["架构", "方案", "技术", "设计", "agent", "api"]):
            cat = "技术架构与方案"
            tags = ["技术", "架构"]
        elif any(k in filename_lower or k in preview for k in ["需求", "prd", "功能", "用户"]):
            cat = "需求与产品设计"
            tags = ["需求", "产品"]
        elif any(k in filename_lower or k in preview for k in ["总结", "汇报", "汇报演示", "季度", "年终"]):
            cat = "总结与汇报演示"
            tags = ["总结", "汇报"]
        elif any(k in filename_lower or k in preview for k in ["会议", "纪要", "周报", "月报"]):
            cat = "会议纪要与周报"
            tags = ["会议", "纪要"]
        else:
            cat = "学习笔记与参考"
            tags = ["资料"]

        return {
            "category": cat,
            "tags": tags,
            "summary": f"基于本地规则自动归档的文件: {parsed_doc.filename}"
        }
