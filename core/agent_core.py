"""
==============================================================================
模块名称: core/agent_core.py
功能描述: 个人文档管家 Agent 核心调度中枢 (AgentCore)
          串联并统领以下完整工作流：
          1. 文档上传分类流: 文件类型分发 ➔ 逐页/逐节切片 ➔ 语义分类 ➔ 物理归档 ➔ 向量索引落库
          2. 知识溯源问答流: 问题向量化 ➔ Top-K 相似度检索 ➔ 构造严格出处 Prompt ➔ LLM 生成 ➔ 溯源校验
          3. 记忆与重试联动: 会话轮次跟踪与记忆降维插槽 + 未命中拦截重试插槽
          4. 逆向生成综合流: 聚合多文档知识资产 ➔ LLM 生成结构化大纲 ➔ 导出 Word/PPTX
可移植性: 采用高内聚、低耦合的依赖注入设计，所有子模块可自由替换。
==============================================================================
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

import config
from llm import get_llm_provider, get_embedding_provider
from llm.base_provider import BaseLLMProvider
from llm.embeddings import BaseEmbeddingProvider
from storage.metadata_db import MetadataDB
from storage.vector_store import BaseVectorStore, EmbeddedVectorStore
from parsers import get_parser_for_file
from core.classifier import DocumentClassifier
from core.memory_manager import MemoryManager
from core.query_optimizer import QueryOptimizer
from generators.doc_generator import DocGenerator
from generators.ppt_generator import PPTGenerator


class AgentCore:
    """
    个人文档管家核心大脑
    """

    def __init__(
        self,
        llm_provider: Optional[BaseLLMProvider] = None,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
        vector_store: Optional[BaseVectorStore] = None,
        metadata_db: Optional[MetadataDB] = None
    ) -> None:
        """
        初始化 Agent 核心组件
        支持依赖注入，默认均加载全局配置的标准实现
        """
        # 1. 基础设施注入
        self.metadata_db = metadata_db or MetadataDB()
        self.llm = llm_provider or get_llm_provider()
        self.embedding = embedding_provider or get_embedding_provider()
        
        # 2. 向量检索存储引擎
        self.vector_store = vector_store or EmbeddedVectorStore(
            metadata_db=self.metadata_db,
            embedding_provider=self.embedding
        )

        # 3. 业务功能模块
        self.classifier = DocumentClassifier(llm_provider=self.llm)
        self.doc_generator = DocGenerator()
        self.ppt_generator = PPTGenerator()
        
        # 4. 增强机制模块（首版骨架）
        self.memory_manager = MemoryManager()
        self.query_optimizer = QueryOptimizer()

    # ==========================================================================
    # 一、文档输入与分类存储链路 (Ingestion Pipeline)
    # ==========================================================================

    def ingest_document(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        上传并归档一份新的 Office 文档 (PPTX 或 DOCX)
        
        执行全流程：
        1. 寻找匹配的文件解析器并执行精密语义切片；
        2. 推断文档分类并将其物理迁移归档到对应子目录；
        3. 元数据入库 SQLite，切片及其向量索引落库向量引擎。
        
        :param file_path: 本地文件路径
        :return: 归档结果报告（含 doc_id, category, stored_path, 切片数等）
        """
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"传入的路径并非有效文件: {path}")

        # 1. 选择解析器并执行切片
        parser = get_parser_for_file(path)
        parsed_doc = parser.parse(path)

        # 2. 智能分类与物理文件搬运归档
        archive_info = self.classifier.classify_and_archive(
            source_file=path,
            parsed_doc=parsed_doc,
            storage_base_dir=config.STORAGE_DIR
        )

        # 3. 保存文档主表元数据
        self.metadata_db.save_document(
            doc_id=parsed_doc.doc_id,
            original_filename=parsed_doc.filename,
            category=archive_info["category"],
            stored_path=archive_info["stored_path"],
            summary=archive_info["summary"],
            tags=archive_info["tags"],
            page_count=parsed_doc.total_pages
        )

        # 4. 批量计算向量并存入向量引擎
        chunks_data = [chunk.to_dict() for chunk in parsed_doc.chunks]
        self.vector_store.add_chunks(chunks_data)

        return {
            "status": "success",
            "doc_id": parsed_doc.doc_id,
            "filename": parsed_doc.filename,
            "category": archive_info["category"],
            "stored_path": archive_info["stored_path"],
            "summary": archive_info["summary"],
            "tags": archive_info["tags"],
            "chunks_count": len(parsed_doc.chunks)
        }

    # ==========================================================================
    # 二、带严格出处的知识溯源问答 (Sourced RAG Q&A)
    # ==========================================================================

    def ask(
        self,
        query: str,
        session_id: str = "default_user",
        top_k: int = config.DEFAULT_RETRIEVAL_TOP_K,
        filter_doc_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        针对已有知识库进行带出处问答
        
        :param query: 用户问题
        :param session_id: 会话标识（用于多轮记忆管理）
        :param top_k: 召回最相关切片数量
        :param filter_doc_id: 可选，限定检索具体某篇文档
        :return: 包含回答文本和精准出处列表的字典
        """
        clean_query = query.strip()
        if not clean_query:
            return {"answer": "请输入具体的问题内容。", "sources": []}

        # 1. 记录用户输入到记忆管理器中
        self.memory_manager.add_message(session_id, "user", clean_query)
        self.memory_manager.compress_history(session_id, llm_provider=self.llm)

        # 2. 向量化检索
        query_vector = self.embedding.embed_text(clean_query)
        retrieved_chunks = self.vector_store.search(
            query_vector=query_vector,
            top_k=top_k,
            filter_doc_id=filter_doc_id
        )

        # 3. 构造出处标记清晰的参考上下文 (Context)
        context_blocks = []
        sources_meta = []
        for i, c in enumerate(retrieved_chunks, start=1):
            source_tag = f"【参考材料 {i}】 (来源: {c['source_filename']} | 坐标: {c['location_label']} | 匹配度: {c.get('score', 0):.2f})"
            context_blocks.append(f"{source_tag}\n{c['content']}")
            sources_meta.append({
                "source_filename": c["source_filename"],
                "location_label": c["location_label"],
                "score": c.get("score", 0),
                "preview": c["content"][:120] + "..."
            })

        context_text = "\n\n" + ("="*60 + "\n").join(context_blocks) if context_blocks else "（无相关资料）"

        # 4. 构建强制溯源系统指令 (System Prompt)
        system_instruction = (
            "你是一个高度专业、严谨求实的个人文档管家知识助手。\n"
            "请基于下方提供的【参考材料】回答用户的问题。\n\n"
            "【严格出处标注准则】:\n"
            "1. 凡是回答中引述的事实、技术参数、方案结论或数据，必须在对应陈述后明确注明出处。\n"
            "   出处格式统一为: [出处: 文件名, 坐标] ，例如: [出处: 架构设计.pptx, 第3页: 核心架构]。\n"
            "2. 如果参考材料中完全没有提及该问题，或者材料不足以推导结论，请明确告知：\n"
            "   '根据已有文档库，未找到相关信息。'，绝对禁止随意编造内容或捏造虚假出处！\n"
            "3. 保持回答条理清晰、层次分明。"
        )

        # 5. 装配大模型调用消息序列
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_instruction}]
        
        # 拼接多轮历史上下文
        history_msgs = self.memory_manager.get_messages(session_id)
        if len(history_msgs) > 1:
            # 加入除本轮 user 外的过去轮次
            messages.extend(history_msgs[:-1])

        # 本轮当前问题与检索材料
        current_turn_prompt = f"【参考材料】:\n{context_text}\n\n【用户提问】: {clean_query}"
        messages.append({"role": "user", "content": current_turn_prompt})

        # 6. 调用大模型生成回答 (如 API 不可用则提供离线自测响应)
        if self.llm and self.llm.is_available():
            try:
                answer = self.llm.chat_complete(messages, temperature=0.3)
            except Exception as e:
                answer = f"【调用大模型发生异常】: {e}"
        else:
            # 离线或骨架单测降级呈现
            answer = (
                f"【骨架演示模式 - 未配置 DEEPSEEK_API_KEY】\n"
                f"系统已成功在向量库中召回了 {len(retrieved_chunks)} 个匹配切片！\n"
                f"配置有效 API Key 后，大模型将在此精准回答并注入出处引用。"
            )

        # 7. 检查是否触发重试机制优化插槽
        if self.query_optimizer.should_trigger_retry(retrieved_chunks, answer):
            # 记录重试钩子（首版仅打桩预留）
            pass

        # 8. 记录助手回答并返回
        self.memory_manager.add_message(session_id, "assistant", answer)

        return {
            "query": clean_query,
            "answer": answer,
            "sources": sources_meta,
            "chunks_count": len(retrieved_chunks)
        }

    # ==========================================================================
    # 三、跨资料综合与逆向生成新文档/PPT (Synthesis & Generation)
    # ==========================================================================

    def generate_new_doc(
        self,
        topic: str,
        output_filename: Optional[str] = None,
        top_k: int = 6
    ) -> Path:
        """
        根据知识库资料，综合提炼并生成一份排版精美的 Word 专题总结报告
        
        :param topic: 报告主题或用户指令 (如: "总结知识库中所有关于数据同步架构的内容")
        :param output_filename: 指定输出文件名 (可选)
        :param top_k: 综合参考的切片数量
        :return: 生成的 docx 文件路径
        """
        # 1. 召回与主题相关的知识资产
        q_vec = self.embedding.embed_text(topic)
        chunks = self.vector_store.search(q_vec, top_k=top_k)

        context_materials = "\n\n".join(
            [f"[{c['source_filename']} - {c['location_label']}]:\n{c['content']}" for c in chunks]
        )

        # 2. 要求大模型输出结构化的章节大纲 JSON
        prompt = f"""请针对主题：“{topic}”，综合以下参考文档资料，撰写一份结构严谨、内容详实的专业总结文档。

【参考资料】:
{context_materials}

【输出格式要求】:
必须返回一个合法标准的 JSON 对象，格式定义如下:
{{
    "title": "文档主标题",
    "sections": [
        {{
            "heading": "1. 核心架构概述",
            "level": 1,
            "paragraphs": [
                "综合正文分析...",
                "关键细节与数据..."
            ],
            "bullet_points": [
                "要点一说明 (标注出处: 如 [出处: xxx.docx])",
                "要点二说明"
            ]
        }}
    ]
}}
"""
        messages = [
            {"role": "system", "content": "你是一个专业的工程文档撰写专家，严格输出 JSON。"},
            {"role": "user", "content": prompt}
        ]

        if self.llm and self.llm.is_available():
            try:
                res = self.llm.chat_complete(messages, temperature=0.4, json_mode=True)
                clean_json = self._clean_json_str(res)
                data = json.loads(clean_json)
                doc_title = data.get("title", topic)
                sections = data.get("sections", [])
            except Exception:
                doc_title = topic
                sections = self._build_default_doc_sections(topic, chunks)
        else:
            doc_title = topic
            sections = self._build_default_doc_sections(topic, chunks)

        # 3. 调用 DocGenerator 导出实体文件
        return self.doc_generator.generate_document(
            title=doc_title,
            sections=sections,
            output_filename=output_filename
        )

    def generate_new_ppt(
        self,
        topic: str,
        output_filename: Optional[str] = None,
        top_k: int = 6
    ) -> Path:
        """
        根据知识库资料，综合提炼并生成一份现代 16:9 商业宽屏演示文稿 (.pptx)
        
        :param topic: 演示主题
        :param output_filename: 指定输出文件名 (可选)
        :param top_k: 综合参考的切片数量
        :return: 生成的 pptx 文件路径
        """
        # 1. 召回与主题相关的切片
        q_vec = self.embedding.embed_text(topic)
        chunks = self.vector_store.search(q_vec, top_k=top_k)

        context_materials = "\n\n".join(
            [f"[{c['source_filename']} - {c['location_label']}]:\n{c['content']}" for c in chunks]
        )

        # 2. 引导大模型输出幻灯片卡片阵列 JSON
        prompt = f"""请针对主题：“{topic}”，综合以下参考文档资料，规划并撰写一份现代 16:9 商业汇报演示文稿的内容。

【参考资料】:
{context_materials}

【输出格式要求】:
必须返回一个合法标准的 JSON 对象，格式定义如下:
{{
    "deck_title": "演示文稿大标题",
    "deck_subtitle": "一句话副标题或业务背景",
    "slides": [
        {{
            "type": "content_cards",
            "title": "页面核心主题",
            "takeaway": "核心结论一句话提炼",
            "cards": [
                {{
                    "card_title": "卡片要点1",
                    "points": ["事实与论据", "支撑数据与出处"]
                }},
                {{
                    "card_title": "卡片要点2",
                    "points": ["事实与论据", "支撑数据与出处"]
                }}
            ]
        }},
        {{
            "type": "summary",
            "title": "总结与后续行动",
            "points": [
                "阶段性总结要点 1",
                "下一步落地计划 2"
            ]
        }}
    ]
}}
"""
        messages = [
            {"role": "system", "content": "你是一位资深演示文稿设计师，擅长将复杂文档转化为结构化卡片 PPT，严格输出 JSON。"},
            {"role": "user", "content": prompt}
        ]

        if self.llm and self.llm.is_available():
            try:
                res = self.llm.chat_complete(messages, temperature=0.4, json_mode=True)
                clean_json = self._clean_json_str(res)
                data = json.loads(clean_json)
                deck_title = data.get("deck_title", topic)
                deck_sub = data.get("deck_subtitle", "知识库综合汇报")
                slides = data.get("slides", [])
            except Exception:
                deck_title = topic
                deck_sub = "知识库综合提炼"
                slides = self._build_default_ppt_slides(topic, chunks)
        else:
            deck_title = topic
            deck_sub = "知识库综合提炼 (骨架模式)"
            slides = self._build_default_ppt_slides(topic, chunks)

        # 3. 调用 PPTGenerator 导出实体文件
        return self.ppt_generator.generate_presentation(
            deck_title=deck_title,
            deck_subtitle=deck_sub,
            slides_data=slides,
            output_filename=output_filename
        )

    # ==========================================================================
    # 四、辅助工具与离线降级辅助方法
    # ==========================================================================

    def list_documents(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """查看知识库中已存储归档的所有文档列表"""
        return self.metadata_db.list_documents(category=category)

    @staticmethod
    def _clean_json_str(raw_str: str) -> str:
        """剥离 Markdown 代码块标记，提取纯 JSON 字符串"""
        text = raw_str.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    @staticmethod
    def _build_default_doc_sections(topic: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """离线模式下的默认 Word 章节结构构建"""
        sec1_bullets = [f"参考来源: {c['source_filename']} ({c['location_label']})" for c in chunks[:4]]
        return [
            {
                "heading": f"1. 关于『{topic}』的研究与资料归集",
                "level": 1,
                "paragraphs": [
                    f"针对『{topic}』，系统从知识库中检索并匹配到相关知识资产。",
                    "以下为归集到的核心文档片段摘要。"
                ],
                "bullet_points": sec1_bullets if sec1_bullets else ["暂无精准匹配材料"]
            },
            {
                "heading": "2. 关键切片详述",
                "level": 1,
                "paragraphs": [c["content"][:200] + "..." for c in chunks[:2]]
            }
        ]

    @staticmethod
    def _build_default_ppt_slides(topic: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """离线模式下的默认 PPT 幻灯片卡片构建"""
        cards = []
        for i, c in enumerate(chunks[:2], start=1):
            cards.append({
                "card_title": f"资料 {i}: {c['source_filename'][:15]}",
                "points": [
                    f"定位: {c['location_label']}",
                    f"内容摘要: {c['content'][:60]}..."
                ]
            })

        return [
            {
                "type": "content_cards",
                "title": f"{topic} - 核心洞察",
                "takeaway": "核心结论: 基于已有知识资产提炼的关键信息",
                "cards": cards if cards else [{"card_title": "暂无资料", "points": ["知识库尚未建立充分关联"]}]
            },
            {
                "type": "summary",
                "title": "总结与后续行动",
                "points": [
                    "知识资产已完成标准化切片与向量化归档",
                    "可通过接入 DeepSeek API 获取更深层次的自动逻辑提炼"
                ]
            }
        ]
