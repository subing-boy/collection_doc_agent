"""
==============================================================================
模块名称: core/query_optimizer.py
功能描述: 问题重写与检索重试优化器 (骨架与规范定义)

【设计初衷与后续扩展说明】:
在纯向量检索或关键字 RAG 中，用户提问往往非常口语化、包含代词（如“那个架构方案怎么样了”），
或者专业词汇与文档用词存在同义词差异，导致首次检索 Top-K 相似度过低甚至未命中。
本模块负责：
1. 监控和拦截初次检索质量（相似度低、检索集为空）以及大模型回答中的“未找到相关信息”标记；
2. 【待用户后续填入】调用大模型对原始问题进行 Query Rewrite（意图扩展、同义词发散、指代消解）；
3. 调整参数（放大 Top-K 召回范围）自动发起第二轮检索重试，提升长尾问答召回率。

【首版状态】:
已实现未命中检测与确定性规则拦截，并为大模型问题重写机制设计好了完备的插槽与开发文档规范，
方便团队后续补充 LLM API 调用。
==============================================================================
"""

from typing import List, Dict, Any, Optional


class QueryOptimizer:
    """
    问题改写与检索重试管理器
    """

    def __init__(self, score_threshold: float = 0.15) -> None:
        """
        :param score_threshold: 判定检索是否置信的余弦相似度下限阈值
        """
        self.score_threshold = score_threshold
        # 常见表明未在文档库中找到答案的典型短语
        self.no_info_indicators = [
            "未找到相关信息",
            "根据已有文档库，未找到",
            "资料中未提及",
            "知识库中没有",
            "现有文档不足以回答",
            "没有找到关于",
            "未提及具体实现",
            "文档中未说明"
        ]

    def check_missing_core_terms(
        self,
        query_keywords: List[str],
        retrieved_chunks: List[Dict[str, Any]]
    ) -> List[str]:
        """
        质量门禁：检查用户提问中的核心专有名词是否在召回切片中完全缺失
        重点关注生僻缩写或核心实体术语 (如 vad, l2cap, coc, mtu 等)
        :param query_keywords: 用户提问提纯出的关键词列表
        :param retrieved_chunks: 当前召回的切片集合
        :return: 在切片中完全未出现的遗漏核心词列表
        """
        if not query_keywords or not retrieved_chunks:
            return [k for k in query_keywords if k.strip()]

        combined_text = " ".join([
            f"{c.get('location_label', '')} {c.get('content', '')}".lower()
            for c in retrieved_chunks
        ])

        missing = []
        for kw in query_keywords:
            clean_kw = kw.lower().strip()
            if not clean_kw:
                continue
            if clean_kw not in combined_text:
                missing.append(clean_kw)

        return missing

    def is_retrieval_low_confidence(self, chunks: List[Dict[str, Any]]) -> bool:
        """
        判断检索结果是否属于低置信度（即需要触发重试）
        """
        if not chunks:
            return True
        # 如果最高得分低于置信阈值，视为召回质量不足
        top_score = chunks[0].get("score", 0.0)
        return top_score < self.score_threshold

    def is_answer_indicating_miss(self, answer: str) -> bool:
        """
        检查大模型的输出文本是否判定自己“未在材料中找到信息”
        """
        return any(indicator in answer for indicator in self.no_info_indicators)

    def rewrite_query(
        self,
        original_query: str,
        llm_provider: Optional[Any] = None,
        context_summary: str = ""
    ) -> List[str]:
        """
        【待实现接口 - 核心骨架】调用大模型进行多维度问题改写与同义词扩展
        
        后续补充步骤建议:
        -------------------------------------------------------------
        TODO 1: 检查 llm_provider 是否就绪。若不可用，直接返回 [original_query]。
        TODO 2: 构造问题改写 Prompt:
                "用户正在检索私有文档知识库。原问题为：'{original_query}'。
                 由于当前检索未命中，请结合上下文（如有：{context_summary}），
                 将该问题改写为 2 个不同表述但语义相同、更偏向正式文档用词的搜索查询语句。
                 输出格式：每行一个改写后的句子。"
        TODO 3: 调用 llm_provider.chat_complete(messages) 获取改写列表。
        TODO 4: 返回 [original_query] + 改写句子列表。
        -------------------------------------------------------------
        """
        # --- 骨架占位说明: 首版暂不发起外部 LLM 调用，直接透传原问题 ---
        rewritten_candidates = [original_query]
        
        # 示例：简单的本地口语化替换规则（作为骨架演示）
        if "怎么样" in original_query:
            rewritten_candidates.append(original_query.replace("怎么样", "核心架构与技术方案"))
        if "讲了啥" in original_query:
            rewritten_candidates.append(original_query.replace("讲了啥", "概述与核心内容"))

        return rewritten_candidates

    def should_trigger_retry(
        self,
        retrieved_chunks: List[Dict[str, Any]],
        llm_answer: Optional[str] = None
    ) -> bool:
        """
        综合判断是否需要启动重试链路
        :param retrieved_chunks: 当前召回的知识切片
        :param llm_answer: 大模型生成的初版回答（如果有）
        """
        # 情况 1: 切片为空或置信度过低
        if self.is_retrieval_low_confidence(retrieved_chunks):
            return True

        # 情况 2: 大模型明确告知在现有切片中未检索到
        if llm_answer and self.is_answer_indicating_miss(llm_answer):
            return True

        return False
