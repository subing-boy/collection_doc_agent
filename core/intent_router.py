"""
==============================================================================
模块名称: core/intent_router.py
功能描述: 快慢双车道智能意图路由器 (Fast-Slow Dual Lane Intent Router)
          1. 快车道 (Fast Lane, 0ms):
             - 纯本地确定性正则规则秒级抽取动作与目标目录；
             - 覆盖明确命令 (make-doc/make-ppt/list/exit) 与高频口语模式；
          2. 慢车道 (Slow Lane, 语义分析):
             - 针对复杂歧义长句、口语化变体，调用大模型进行轻量结构化意图分类与参数提纯；
             - 彻底杜绝词法枚举遗漏；
          3. 严格安全与离线降级:
             - 自动归一化 Windows 盘符路径 (D:\\download -> /mnt/d/download)；
             - 网络异常或离线时自动降级为规则兜底，永不崩溃。
==============================================================================
"""

import re
import json
from pathlib import Path
from typing import Dict, Any, Optional

from llm.base_provider import BaseLLMProvider


class IntentRouter:
    """
    智能体快慢双车道意图分流与参数提取引擎
    """

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None) -> None:
        self.llm = llm_provider

    def analyze_intent(self, raw_text: str) -> Dict[str, Any]:
        """
        综合分析用户输入的真实意图与参数
        :param raw_text: 用户原始自然语言长句
        :return: {"intent": "make_doc" | "make_ppt" | "ask", "topic": str, "target_dir": Optional[Path]}
        """
        clean_text = raw_text.strip()
        if not clean_text:
            return {"intent": "ask", "topic": "", "target_dir": None}

        # ----------------------------------------------------------------------
        # 车道 1: 本地快车道 (Fast Lane, 纯本地确定性规则毫秒级匹配)
        # ----------------------------------------------------------------------
        fast_result = self._fast_heuristic_check(clean_text)
        if fast_result is not None:
            return fast_result

        # ----------------------------------------------------------------------
        # 车道 2: 语义慢车道 (Slow Lane, 大模型轻量结构化意图推理)
        # ----------------------------------------------------------------------
        if self.llm and self.llm.is_available():
            try:
                llm_result = self._llm_semantic_classify(clean_text)
                if llm_result is not None:
                    return llm_result
            except Exception:
                pass

        # 最终安全回退：默认归为常规知识问答
        return {
            "intent": "ask",
            "topic": clean_text,
            "target_dir": None
        }

    def _fast_heuristic_check(self, text: str) -> Optional[Dict[str, Any]]:
        """
        车道 1 确定性规则快速分析
        """
        # 1. 抽取目标输出目录 (涵盖 到/至/放在/放至/保存到/输出到 等多种介词)
        target_dir = self._extract_target_dir(text)

        # 2. 检查 PPT 生成意图
        ppt_pat = re.compile(
            r'(?:生成|制作|做成|做一份|做个|导出一份|导出|规划)\s*(?:16:9|现代版式)?\s*(?:ppt|pptx|演示文稿|幻灯片)|^make-ppt\b|^生成ppt\b',
            re.I
        )
        has_ppt = bool(ppt_pat.search(text))

        # 3. 检查 DOC / 方案 / 文档 / 报告生成意图
        doc_explicit_pat = re.compile(r'\b(?:word|doc|docx)\b|^make-doc\b|^生成doc\b', re.I)
        doc_phrase_pat = re.compile(
            r'(?:生成|制作|做成|做一份|做个|编写|写一份|写个|整理|输出|导出|出)\s*(?:一个|一份|个)?.*?(?:文档|报告|报表|方案|需求方案|需求文档|说明书|规格书|白皮书)',
            re.I
        )
        has_doc = bool(doc_explicit_pat.search(text)) or bool(doc_phrase_pat.search(text))

        # 若两者均未命中，快车道无法100%确定，转交慢车道
        if not has_ppt and not has_doc:
            return None

        # PPT 优先级高于 Doc（若明确出现 PPT 则认定为 PPT）
        action_type = "make_ppt" if has_ppt else "make_doc"

        # 4. 剥离动作词与路径，提纯核心 Topic
        clean_topic = text
        dir_match = re.search(
            r'(?:到|至|保存到|保存至|输出到|输出至|存放于|保存在|放在|放至|存到|存至)\s*([A-Za-z]:[\\/][^?？\s,，。！!]+|/(?:mnt/[a-zA-Z]|home/[^/\s]+)/[^?？\s,，。！!]+)',
            clean_topic
        )
        if dir_match:
            clean_topic = clean_topic.replace(dir_match.group(0), "")
        clean_topic = re.sub(r'(?:路径下|目录下|目录|路径)', '', clean_topic)

        if action_type == "make_ppt":
            clean_topic = ppt_pat.sub('', clean_topic)
        else:
            clean_topic = re.sub(r'^(?:生成|制作|做成|做一份|做个|编写|写一份|写个|整理|输出|导出|出)\s*(?:一个|一份|个)?', '', clean_topic, flags=re.I)
            clean_topic = doc_explicit_pat.sub('', clean_topic)

        clean_topic = clean_topic.strip('\"\' :：。，,！!？? \t\r\n')

        return {
            "intent": action_type,
            "topic": clean_topic or text,
            "target_dir": target_dir
        }

    def _llm_semantic_classify(self, text: str) -> Optional[Dict[str, Any]]:
        """
        车道 2 调用大模型进行轻量意图分类与槽位填充
        """
        system_instruction = (
            "你是一个高精度的意图识别与参数抽取引擎。请分析用户的输入，严格输出一个 JSON 对象。\n"
            "【输出字段】:\n"
            "1. intent: 字符串，仅限以下三选一:\n"
            "   - 'make_doc': 用户希望生成/制作/编写/输出 Word、需求方案、技术文档、规格书、报告、说明书、白皮书等；\n"
            "   - 'make_ppt': 用户希望生成/制作/规划 16:9 幻灯片、演示文稿、PPT 等；\n"
            "   - 'ask': 用户单纯询问技术细节、检索协议或进行常规知识问答。\n"
            "2. topic: 提纯后的核心业务主题 (剥离制作、输出、保存目录等动词，保留完整的技术概念)。\n"
            "3. target_dir: 用户指定的保存目标路径 (如 'D:\\download')，若未指定则输出 null。\n\n"
            "严格只返回 JSON，禁止返回任何其他文字或 Markdown 标记。"
        )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": f"用户输入: {text}"}
        ]

        raw_response = self.llm.chat_complete(messages, temperature=0.1, json_mode=True)
        # 清洗可能存在的 Markdown 代码块
        clean_json = raw_response.strip()
        if clean_json.startswith("```"):
            clean_json = re.sub(r"^```(?:json)?", "", clean_json)
            clean_json = re.sub(r"```$", "", clean_json).strip()

        data = json.loads(clean_json)
        intent = data.get("intent", "ask")
        if intent not in ("make_doc", "make_ppt", "ask"):
            intent = "ask"

        topic = data.get("topic") or text
        raw_dir = data.get("target_dir")
        target_dir = self._normalize_dir_path(raw_dir) if raw_dir else None

        return {
            "intent": intent,
            "topic": topic.strip(),
            "target_dir": target_dir
        }

    @staticmethod
    def _extract_target_dir(text: str) -> Optional[Path]:
        """从自然语言中正则抽取目标路径并归一化"""
        dir_match = re.search(
            r'(?:到|至|保存到|保存至|输出到|输出至|存放于|保存在|放在|放至|存到|存至)\s*([A-Za-z]:[\\/][^?？\s,，。！!]+|/(?:mnt/[a-zA-Z]|home/[^/\s]+)/[^?？\s,，。！!]+)',
            text
        )
        if not dir_match:
            return None

        dir_str = dir_match.group(1).rstrip('\"\'/\\')
        dir_str = re.sub(r'(?:路径下|目录下|目录|路径)$', '', dir_str).strip()
        return IntentRouter._normalize_dir_path(dir_str)

    @staticmethod
    def _normalize_dir_path(path_str: str) -> Optional[Path]:
        """将 Windows / Linux 路径统一转换为系统可用 Path"""
        if not path_str or str(path_str).lower() == "null":
            return None

        clean_p = str(path_str).strip('\"\' ')
        # 处理 Windows 盘符 D:\ -> /mnt/d/
        if re.match(r'^[A-Za-z]:', clean_p):
            drive = clean_p[0].lower()
            rest = clean_p[2:].replace('\\', '/').lstrip('/')
            return Path(f'/mnt/{drive}/{rest}').resolve()

        return Path(clean_p.replace('\\', '/')).resolve()
