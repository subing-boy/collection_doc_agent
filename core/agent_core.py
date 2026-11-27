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
import re
import time
import hashlib
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
from core.intent_router import IntentRouter
from core.trace_logger import HarnessTraceLogger, HarnessTraceContext
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
        metadata_db: Optional[MetadataDB] = None,
        storage_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        trace_logger: Optional[HarnessTraceLogger] = None
    ) -> None:
        """
        初始化 Agent 核心组件
        支持依赖注入，默认均加载全局配置的标准实现
        """
        # 1. 基础设施注入
        self.metadata_db = metadata_db or MetadataDB()
        self.llm = llm_provider or get_llm_provider()
        self.embedding = embedding_provider or get_embedding_provider()
        self.storage_dir = storage_dir or config.STORAGE_DIR
        self.output_dir = output_dir or config.OUTPUT_DIR
        self.trace_logger = trace_logger or HarnessTraceLogger()
        self.intent_router = IntentRouter(llm_provider=self.llm)
        
        # 2. 向量检索存储引擎
        self.vector_store = vector_store or EmbeddedVectorStore(
            metadata_db=self.metadata_db,
            embedding_provider=self.embedding
        )

        # 3. 业务功能模块
        self.classifier = DocumentClassifier(llm_provider=self.llm)
        self.doc_generator = DocGenerator(output_dir=self.output_dir)
        self.ppt_generator = PPTGenerator(output_dir=self.output_dir)
        
        # 4. 增强机制模块（首版骨架）
        self.memory_manager = MemoryManager()
        self.query_optimizer = QueryOptimizer()

    # ==========================================================================
    # 一、文档输入与分类存储链路 (Ingestion Pipeline)
    # ==========================================================================

    @staticmethod
    def calculate_file_sha256(file_path: Path) -> str:
        """计算文件的 SHA256 哈希值作为内容全局唯一指纹"""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def ingest_document(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        上传并归档一份新的 Office 文档 (PPTX 或 DOCX)
        内置四象限状态决策引擎 (基于内容 SHA256 指纹 + 原始文件名)：
        - 象限 1 (同名同Hash): 完全重复提交，秒级跳过，避免无谓重算；
        - 象限 2 (同名异Hash): 版本迭代更新，级联清理该文件旧切片并就地刷新落库；
        - 象限 3 (异名同Hash): 识别为改名副本，绑定文件名别名，避免向量空间切片污染；
        - 象限 4 (异名异Hash): 全新文档标准入库。
        
        :param file_path: 本地文件路径
        :return: 归档结果报告（含 status, doc_id, category, message 等）
        """
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"传入的路径并非有效文件: {path}")

        file_hash = self.calculate_file_sha256(path)
        filename = path.name

        # 查询数据库中是否已存在相同内容 Hash 或同名记录
        existing_by_hash = self.metadata_db.get_document_by_hash(file_hash)
        existing_by_name = self.metadata_db.get_document_by_filename(filename)

        # ----------------------------------------------------------------------
        # 象限 1: 同名且同内容 Hash (完全重复提交)
        # ----------------------------------------------------------------------
        if existing_by_name and existing_by_name.get("file_hash") == file_hash:
            return {
                "status": "skipped_duplicate",
                "doc_id": existing_by_name["doc_id"],
                "filename": filename,
                "category": existing_by_name["category"],
                "stored_path": existing_by_name["stored_path"],
                "summary": existing_by_name["summary"],
                "tags": existing_by_name["tags"],
                "chunks_count": 0,
                "message": f"文档【{filename}】在知识库中已存在且内容未改动，已跳过重复入库。"
            }

        # ----------------------------------------------------------------------
        # 象限 3: 改名副本 (内容 Hash 相同，但当前提交的文件名不同)
        # ----------------------------------------------------------------------
        if existing_by_hash and existing_by_hash["original_filename"] != filename:
            # 追加文件名别名映射标签，物理上不重复切片，保护向量空间纯净
            self.metadata_db.add_document_alias(existing_by_hash["doc_id"], filename)
            updated_doc = self.metadata_db.get_document_by_id(existing_by_hash["doc_id"])
            return {
                "status": "aliased_duplicate",
                "doc_id": existing_by_hash["doc_id"],
                "filename": filename,
                "original_filename": existing_by_hash["original_filename"],
                "category": existing_by_hash["category"],
                "stored_path": existing_by_hash["stored_path"],
                "summary": existing_by_hash["summary"],
                "tags": updated_doc["tags"] if updated_doc else existing_by_hash["tags"],
                "chunks_count": 0,
                "message": f"该文档内容与已有文档【{existing_by_hash['original_filename']}】完全一致，已自动建立文件名别名映射，无需重复入库！"
            }

        # ----------------------------------------------------------------------
        # 象限 2: 同名但内容 Hash 变动 (就地版本迭代更新)
        # 象限 4: 全新文件 (异名且异Hash) 或 双因子语义版本迭代更新
        # ----------------------------------------------------------------------
        is_version_update = bool(existing_by_name and existing_by_name.get("file_hash") != file_hash)
        matched_old_doc = existing_by_name if is_version_update else None

        # 1. 选择解析器并执行切片
        parser = get_parser_for_file(path)
        parsed_doc = parser.parse(path)

        # 2. 若未命中同名更新，启动【双因子语义版本决策引擎】(跨格式、跨版本尾缀自动归纳)
        if not is_version_update:
            semantic_match = self._find_semantic_version_match(filename, parsed_doc.full_text_preview)
            if semantic_match:
                is_version_update = True
                matched_old_doc = semantic_match

        target_doc_id = matched_old_doc["doc_id"] if is_version_update else parsed_doc.doc_id
        parsed_doc.doc_id = target_doc_id
        for chunk in parsed_doc.chunks:
            chunk.doc_id = target_doc_id

        # 若为就地版本更新：首先清除该文档在 SQLite 和内存向量索引中的全部旧切片
        if is_version_update:
            self.vector_store.delete_doc_chunks(target_doc_id)

        # 3. 智能分类与物理文件搬运归档 (Word 统一按 .md 落地，版本更新时 overwrite=True)
        archive_info = self.classifier.classify_and_archive(
            source_file=path,
            parsed_doc=parsed_doc,
            storage_base_dir=self.storage_dir,
            overwrite=is_version_update
        )

        # 若就地更新且旧存储文件路径发生变化（如从 .docx 升级为 .md），彻底清理旧物理文件
        if is_version_update and matched_old_doc:
            old_stored = Path(matched_old_doc.get("stored_path", ""))
            if old_stored.exists() and str(old_stored) != archive_info["stored_path"]:
                old_stored.unlink(missing_ok=True)

        # 4. 保存或更新文档主表元数据 (注入 file_hash 指纹)
        self.metadata_db.save_document(
            doc_id=target_doc_id,
            original_filename=parsed_doc.filename,
            category=archive_info["category"],
            stored_path=archive_info["stored_path"],
            summary=archive_info["summary"],
            tags=archive_info["tags"],
            page_count=parsed_doc.total_pages,
            file_hash=file_hash
        )

        # 5. 批量计算新切片向量并存入向量引擎
        chunks_data = [chunk.to_dict() for chunk in parsed_doc.chunks]
        self.vector_store.add_chunks(chunks_data)

        status_str = "updated_version" if is_version_update else "success"
        if is_version_update and matched_old_doc and matched_old_doc.get("original_filename") != filename:
            message_str = f"检测到文档【{filename}】为已有文档【{matched_old_doc['original_filename']}】的迭代升级版本，已自动就地升级切片至最新版本！"
        elif is_version_update:
            message_str = f"检测到文档【{filename}】存在内容更新，已自动刷新知识切片与向量索引至最新版本！"
        else:
            message_str = "文档已成功完成全新分类归档！"

        return {
            "status": status_str,
            "doc_id": target_doc_id,
            "filename": parsed_doc.filename,
            "category": archive_info["category"],
            "stored_path": archive_info["stored_path"],
            "summary": archive_info["summary"],
            "tags": archive_info["tags"],
            "chunks_count": len(parsed_doc.chunks),
            "message": message_str
        }

    @staticmethod
    def canonicalize_title(filename: str) -> str:
        """
        提取文件名的主干核心名称，去除后缀与末尾的版本号、日期、阶段标识
        支持全角/半角括号: (v1.0), （11.26）, (2.1.3, 11.26), _v1.0, -20261126 等
        """
        stem = Path(filename).stem
        # 1. 剥离末尾括号内的版本、日期、纯数字组合
        stem = re.sub(r'[\(（\[【][^\)）\]】]*?(?:\d+|v\d+|初版|终审|修订|draft|final)[^\)）\]】]*?[\)）\]】]\s*$', '', stem, flags=re.I)
        # 2. 剥离末尾的下划线/中划线版本号与日期 (如 _v1.0, -20261126, _11.26)
        stem = re.sub(r'[-_ ]+(?:v?\d+(?:\.\d+)*|\d{4}[-_.]?\d{2}[-_.]?\d{2}|\d{1,2}\.\d{1,2})$', '', stem, flags=re.I)
        # 3. 符号清洗与空白折叠
        clean = re.sub(r'[-_ ]+', ' ', stem).strip()
        return clean.lower()

    def _find_semantic_version_match(self, filename: str, preview_text: str) -> Optional[Dict[str, Any]]:
        """
        双因子语义版本匹配:
        因子 1: 标题主干归一化匹配 (忽略版本尾缀与后缀格式差异)
        因子 2: 文档级指纹向量余弦相似度比对 (>= 0.65 判定为同源迭代)
        """
        new_canonical = self.canonicalize_title(filename)
        if not new_canonical or len(new_canonical) < 2:
            return None

        all_docs = self.metadata_db.list_documents()
        if not all_docs:
            return None

        new_fingerprint = f"{new_canonical} {preview_text[:500]}"
        new_vec = self.embedding.embed_text(new_fingerprint)

        best_match = None
        highest_sim = 0.0

        for doc in all_docs:
            old_name = doc.get("original_filename", "")
            if old_name == filename:
                continue

            old_canonical = self.canonicalize_title(old_name)
            # 因子 1: 主干名相同，或主干存在强包含关系
            canonical_match = (new_canonical == old_canonical) or (
                len(new_canonical) > 4 and len(old_canonical) > 4 and 
                (new_canonical in old_canonical or old_canonical in new_canonical)
            )

            # 因子 2: 计算文档指纹相似度
            old_fingerprint = f"{old_canonical} {doc.get('summary', '')}"
            old_vec = self.embedding.embed_text(old_fingerprint)
            sim = BaseEmbeddingProvider.cosine_similarity(new_vec, old_vec)

            # 双因子判定门槛: 主干完全一致时相似度 >= 0.40，主干包含时相似度 >= 0.75
            threshold = 0.40 if (new_canonical == old_canonical) else 0.75

            if not canonical_match:
                continue

            if sim >= threshold and sim > highest_sim:
                highest_sim = sim
                best_match = doc

        return best_match

    # ==========================================================================
    # 二、带严格出处的知识溯源问答 (Sourced RAG Q&A)
    # ==========================================================================

    @staticmethod
    def clean_query_and_extract_keywords(raw_query: str) -> tuple[str, List[str]]:
        """
        提问预处理与停用词清洗（纯本地 0 Token 毫秒级）：
        1. 剥离无实际检索语义的元语言和口语废话（如 '知识库中寻找'、'相关的内容'、'帮我查一下' 等）；
        2. 提取出英文单词、复合专有名词短语以及核心词汇作为关键词；
        3. 返回 (清洗后的纯净Query, 提取出的关键词列表)。
        """
        STOP_PHRASES = [
            "在知识库中寻找", "知识库中寻找", "在知识库中查找", "知识库中查找", "在知识库中搜索", "知识库中搜索",
            "从知识库中查找", "从知识库中寻找", "知识库中", "从知识库中", "在知识库里", "知识库里",
            "帮我查一下", "帮我查找", "帮我找一下", "帮我搜一下", "帮我看看", "我想了解一下", "我想了解", "我想查询", "我想知道",
            "请问一下", "请问", "告诉我", "搜一下", "查一下", "找一下", "检索一下",
            "相关的内容", "相关的内容吗", "相关信息", "相关资料", "相关的", "有关内容", "有关信息",
            "都有什么", "有哪些", "是什么", "怎么样", "具体定义", "的具体逻辑", "具体逻辑"
        ]
        text = raw_query.strip()
        for p in sorted(STOP_PHRASES, key=len, reverse=True):
            text = text.replace(p, " ")

        text = re.sub(r"^[的和与中在关于找寻]+", "", text.strip()).strip()
        text = re.sub(r"[的和与中在关于找寻]+$", "", text).strip()
        text = re.sub(r"[\s,，。？！?!]+", " ", text).strip()

        keywords: List[str] = []
        # 提取英文和数字专有名词 (如 ai, chat, l2cap, coc, 0x21)
        eng_words = re.findall(r"[A-Za-z0-9_#.-]+", raw_query)
        for w in eng_words:
            if len(w) >= 2 and w.lower() not in ["in", "to", "of", "and", "or", "the", "is", "for"]:
                keywords.append(w.lower())

        # 提取连续英文短语 (如 ai chat, l2cap coc)
        eng_phrases = re.findall(r"[A-Za-z0-9_.-]+(?:\s+[A-Za-z0-9_.-]+)+", raw_query)
        for ep in eng_phrases:
            keywords.append(ep.lower())

        clean_q = text if text else raw_query
        # 去重并保持顺序
        dedup_keywords = list(dict.fromkeys(keywords))
        return clean_q, dedup_keywords

    def ask(
        self,
        query: str,
        session_id: str = "default_user",
        top_k: int = config.DEFAULT_RETRIEVAL_TOP_K,
        filter_doc_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        针对已有知识库进行带出处问答 (采用双路混合检索与提问预处理)
        
        :param query: 用户问题
        :param session_id: 会话标识（用于多轮记忆管理）
        :param top_k: 召回最相关切片数量
        :param filter_doc_id: 可选，限定检索具体某篇文档
        :return: 包含回答文本和精准出处列表的字典
        """
        clean_query = query.strip()
        if not clean_query:
            return {"answer": "请输入具体的问题内容。", "sources": []}

        start_time = time.time()

        # 1. 记录原始用户输入到记忆管理器中
        self.memory_manager.add_message(session_id, "user", clean_query)
        self.memory_manager.compress_history(session_id, llm_provider=self.llm)

        # 2. 提问提纯与初始双路混合检索 (语义向量 + 关键词加权)
        clean_text, keywords = self.clean_query_and_extract_keywords(clean_query)
        query_vector = self.embedding.embed_text(clean_text)
        initial_chunks = self.vector_store.search(
            query_vector=query_vector,
            top_k=top_k,
            filter_doc_id=filter_doc_id,
            keywords=keywords
        )

        # 3. 构建强制溯源系统指令 (System Prompt)
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

        # ======================================================================
        # 4. Agent Loop 多轮自主纠错与深度筛查闭环 (最多 4 轮循环，防死循环安全锁)
        # ======================================================================
        MAX_AGENT_LOOPS = 4
        active_chunks: List[Dict[str, Any]] = list(initial_chunks)
        called_tool_signatures = set()
        invoked_tools_meta: List[Dict[str, Any]] = [{
            "tool": "HybridSearch",
            "keywords": keywords,
            "top_k": top_k,
            "retrieved_count": len(initial_chunks)
        }]

        answer = ""
        current_turn_prompt = ""
        sources_meta: List[Dict[str, Any]] = []

        for loop_turn in range(1, MAX_AGENT_LOOPS + 1):
            # 门禁 1: 检查提问中核心专有名词是否有遗漏
            missing_terms = self.query_optimizer.check_missing_core_terms(keywords, active_chunks)

            # 如果检测到关键实体遗漏且尚未达到最大轮次，自主唤醒深度筛查工具
            if missing_terms and loop_turn < MAX_AGENT_LOOPS:
                for term in missing_terms:
                    grep_sig = f"grep:{term}"
                    if grep_sig not in called_tool_signatures:
                        called_tool_signatures.add(grep_sig)
                        grep_results = self.metadata_db.grep_chunks_by_term(term, doc_id=filter_doc_id)
                        if grep_results:
                            invoked_tools_meta.append({
                                "tool": "deep_keyword_grep",
                                "term": term,
                                "hit_count": len(grep_results)
                            })
                            # 合并新切片并去重
                            existing_ids = {c.get("chunk_id") for c in active_chunks}
                            for gh in grep_results[:3]:
                                if gh.get("chunk_id") not in existing_ids:
                                    active_chunks.append(gh)
                                    existing_ids.add(gh.get("chunk_id"))

                            # 对首个命中切片执行邻近章节上下文扩展 (保证 Phase 1 / Phase 2 完整性)
                            top_hit = grep_results[0]
                            adj_sig = f"adj:{top_hit['doc_id']}:{top_hit['page_or_slide']}"
                            if adj_sig not in called_tool_signatures:
                                called_tool_signatures.add(adj_sig)
                                adj_chunks = self.metadata_db.get_adjacent_chunks(
                                    doc_id=top_hit["doc_id"],
                                    page_or_slide=top_hit["page_or_slide"],
                                    window=1
                                )
                                if adj_chunks:
                                    invoked_tools_meta.append({
                                        "tool": "expand_adjacent_chunks",
                                        "source": top_hit["source_filename"],
                                        "center_page": top_hit["page_or_slide"],
                                        "expanded_count": len(adj_chunks)
                                    })
                                    for ac in adj_chunks:
                                        if ac.get("chunk_id") not in existing_ids:
                                            active_chunks.append(ac)
                                            existing_ids.add(ac.get("chunk_id"))
                            break

            # 组装本轮参考材料
            context_blocks = []
            sources_meta = []
            for i, c in enumerate(active_chunks, start=1):
                source_tag = f"【参考材料 {i}】 (来源: {c['source_filename']} | 坐标: {c['location_label']} | 匹配度: {c.get('score', 0):.2f})"
                context_blocks.append(f"{source_tag}\n{c['content']}")
                sources_meta.append({
                    "source_filename": c["source_filename"],
                    "location_label": c["location_label"],
                    "score": c.get("score", 0),
                    "preview": c["content"][:120] + "..."
                })

            context_text = "\n\n" + ("="*60 + "\n").join(context_blocks) if context_blocks else "（无相关资料）"

            # 组装消息并调用大模型
            current_turn_prompt = f"【参考材料】:\n{context_text}\n\n【用户提问】: {clean_query}"
            messages: List[Dict[str, str]] = [{"role": "system", "content": system_instruction}]
            history_msgs = self.memory_manager.get_messages(session_id)
            if len(history_msgs) > 1:
                messages.extend(history_msgs[:-1])
            messages.append({"role": "user", "content": current_turn_prompt})

            if self.llm and self.llm.is_available():
                try:
                    answer = self.llm.chat_complete(messages, temperature=0.3)
                except Exception as e:
                    answer = f"【调用大模型发生异常】: {e}"
            else:
                answer = (
                    f"【骨架演示模式 - 未配置 DEEPSEEK_API_KEY】\n"
                    f"系统已成功在向量库与深度筛查工具中汇总了 {len(active_chunks)} 个高匹配切片！\n"
                    f"配置有效 API Key 后，大模型将在此精准回答并注入出处引用。"
                )

            # 门禁 2: 检查大模型是否回答未找到
            if self.query_optimizer.is_answer_indicating_miss(answer):
                # 若未找到且未达上限，下一轮继续自愈
                if loop_turn < MAX_AGENT_LOOPS:
                    continue
                else:
                    break
            else:
                # 成功找到有效答案，提前退出 Loop！
                break

        # 5. 记录助手回答并计算耗时
        self.memory_manager.add_message(session_id, "assistant", answer)
        elapsed_ms = (time.time() - start_time) * 1000.0

        # 6. 维测打点记录：结构化记录 Harness ⇄ LLM 交互轨迹 (仅当 AGENT_DEBUG 开启时生效)
        trace_ctx = HarnessTraceContext(
            query=clean_query,
            session_id=session_id,
            system_prompt=system_instruction,
            history_dialog=history_msgs[:-1] if len(history_msgs) > 1 else [],
            available_tools=[
                "DocumentIngest (文档精密解析与分类归档)",
                "HybridSearch (提问预处理与关键词+向量双路混合检索)",
                "deep_keyword_grep (全库穿透深度专有名词筛查)",
                "expand_adjacent_chunks (章节连续上下文扩展)",
                "MakeDoc (专业结构化 Word 报表导出)",
                "MakePPT (16:9 现代商业版式幻灯片导出)"
            ],
            invoked_tools=invoked_tools_meta,
            current_prompt=current_turn_prompt,
            llm_config={
                "provider": config.DEFAULT_LLM_PROVIDER,
                "model": config.DEEPSEEK_MODEL,
                "temperature": 0.3
            },
            ai_response=answer,
            execution_time_ms=elapsed_ms
        )
        self.trace_logger.record_trace(trace_ctx)

        return {
            "query": clean_query,
            "answer": answer,
            "sources": sources_meta,
            "chunks_count": len(active_chunks)
        }

    # ==========================================================================
    # 三、跨资料综合与逆向生成新文档/PPT (Synthesis & Generation)
    # ==========================================================================

    def generate_new_doc(
        self,
        topic: str,
        output_filename: Optional[str] = None,
        output_dir: Optional[Path] = None,
        top_k: int = 6
    ) -> Path:
        """
        根据知识库资料，综合提炼并生成一份排版精美的 Word 专题总结报告
        
        :param topic: 报告主题或用户指令 (如: "总结知识库中所有关于数据同步架构的内容")
        :param output_filename: 指定输出文件名 (可选)
        :param output_dir: 指定目标输出目录 (可选)
        :param top_k: 综合参考的切片数量
        :return: 生成的 docx 文件路径
        """
        start_time = time.time()

        # 1. 召回与主题相关的知识资产 (混合检索)
        clean_topic, keywords = self.clean_query_and_extract_keywords(topic)
        q_vec = self.embedding.embed_text(clean_topic)
        chunks = self.vector_store.search(q_vec, top_k=top_k, keywords=keywords)

        context_materials = "\n\n".join(
            [f"[{c['source_filename']} - {c['location_label']}]:\n{c['content']}" for c in chunks]
        )

        # 2. 动态加载用户可编辑的 Word/Doc 生成 Prompt 模板
        prompt = self._load_doc_prompt(topic=topic, context_materials=context_materials)
        system_instruction = "你是一个专业的工程方案与技术需求文档撰写专家，严格输出 JSON。"
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ]

        if self.llm and self.llm.is_available():
            try:
                res = self.llm.chat_complete(messages, temperature=0.4, json_mode=True)
                clean_json = self._clean_json_str(res)
                data = json.loads(clean_json)
                doc_title = data.get("doc_title") or data.get("title") or topic
                sections = data.get("sections", [])
            except Exception:
                doc_title = topic
                sections = self._build_default_doc_sections(topic, chunks)
        else:
            doc_title = topic
            sections = self._build_default_doc_sections(topic, chunks)

        # 3. 调用 DocGenerator 导出实体文件
        generated_path = self.doc_generator.generate_document(
            title=doc_title,
            sections=sections,
            output_filename=output_filename,
            output_dir=output_dir
        )

        # 4. 维测打点记录：记录实际调用的 Prompt 内容与输出结果
        elapsed_ms = (time.time() - start_time) * 1000.0
        trace_ctx = HarnessTraceContext(
            query=f"[生成Doc] {topic}",
            system_prompt=system_instruction,
            available_tools=["MakeDoc (专业结构化 Word 报表导出)", "HybridSearch (双路混合检索)"],
            invoked_tools=[{
                "tool": "MakeDoc",
                "topic": topic,
                "output_path": str(generated_path),
                "retrieved_chunks": [
                    {"source_filename": c.get("source_filename"), "location_label": c.get("location_label"), "score": c.get("score", 0.0)}
                    for c in chunks
                ]
            }],
            current_prompt=prompt,
            llm_config={"model": config.DEEPSEEK_MODEL, "temperature": 0.4, "provider": config.DEFAULT_LLM_PROVIDER},
            ai_response=f"成功根据自定义 Prompt 生成技术需求文档: {generated_path}",
            execution_time_ms=elapsed_ms
        )
        self.trace_logger.record_trace(trace_ctx)

        return generated_path

    @staticmethod
    def _load_doc_prompt(topic: str, context_materials: str) -> str:
        """
        动态热加载用户可编辑的 Word/Doc 生成 Prompt 模板文件
        若模板文件存在，则读取并替换 {topic} 与 {context_materials}；
        若不存在或发生异常，安全回退到内置标准提示词。
        """
        template_file = config.DOC_PROMPT_TEMPLATE_PATH
        if template_file.is_file():
            try:
                template_str = template_file.read_text(encoding="utf-8")
                return template_str.format(topic=topic, context_materials=context_materials)
            except Exception:
                pass

        return f"""请针对主题：“{topic}”，综合以下参考文档资料，撰写一份结构严谨、内容详实的高质量技术需求与方案文档。

【参考资料】:
{context_materials}

【输出格式要求】:
必须返回一个合法标准的 JSON 对象，格式定义如下:
{{
    "doc_title": "文档主标题",
    "sections": [
        {{
            "heading": "1. 概述与业务背景",
            "level": 1,
            "paragraphs": [
                "综合正文分析...",
                "关键细节与数据..."
            ],
            "bullet_points": [
                "要点一说明 (标注出处: 如 [出处: xxx.docx])"
            ]
        }}
    ]
}}
"""

    def generate_new_ppt(
        self,
        topic: str,
        output_filename: Optional[str] = None,
        output_dir: Optional[Path] = None,
        top_k: int = 6
    ) -> Path:
        """
        根据知识库资料与用户自定义编辑的 Prompt 模板，综合提炼并生成一份现代 16:9 商业宽屏演示文稿 (.pptx)
        
        :param topic: 演示主题
        :param output_filename: 指定输出文件名 (可选)
        :param output_dir: 指定目标输出目录 (可选，如 D:\\download)
        :param top_k: 综合参考的切片数量
        :return: 生成的 pptx 文件绝对路径
        """
        start_time = time.time()

        # 1. 召回与主题相关的切片 (混合检索)
        clean_topic, keywords = self.clean_query_and_extract_keywords(topic)
        q_vec = self.embedding.embed_text(clean_topic)
        chunks = self.vector_store.search(q_vec, top_k=top_k, keywords=keywords)

        context_materials = "\n\n".join(
            [f"[{c['source_filename']} - {c['location_label']}]:\n{c['content']}" for c in chunks]
        )

        # 2. 动态读取用户可编辑的 PPT 生成 Prompt 模板文件
        prompt = self._load_ppt_prompt(topic=topic, context_materials=context_materials)

        system_instruction = "你是一位资深演示文稿设计师与技术布道师，擅长将复杂文档转化为结构化卡片 PPT，严格输出 JSON。"
        messages = [
            {"role": "system", "content": system_instruction},
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

        # 3. 调用 PPTGenerator 导出实体文件至目标目录
        generated_path = self.ppt_generator.generate_presentation(
            deck_title=deck_title,
            deck_subtitle=deck_sub,
            slides_data=slides,
            output_filename=output_filename,
            output_dir=output_dir
        )

        # 4. 维测打点记录：记录实际调用的 Prompt 内容与输出结果
        elapsed_ms = (time.time() - start_time) * 1000.0
        trace_ctx = HarnessTraceContext(
            query=f"[生成PPT] {topic}",
            system_prompt=system_instruction,
            available_tools=["MakePPT (16:9 现代商业版式幻灯片导出)", "HybridSearch (双路混合检索)"],
            invoked_tools=[{
                "tool": "MakePPT",
                "topic": topic,
                "output_path": str(generated_path),
                "retrieved_chunks": [
                    {"source_filename": c.get("source_filename"), "location_label": c.get("location_label"), "score": c.get("score", 0.0)}
                    for c in chunks
                ]
            }],
            current_prompt=prompt,
            llm_config={"model": config.DEEPSEEK_MODEL, "temperature": 0.4, "provider": config.DEFAULT_LLM_PROVIDER},
            ai_response=f"成功根据自定义 Prompt 生成 16:9 商业 PPT 文件: {generated_path}",
            execution_time_ms=elapsed_ms
        )
        self.trace_logger.record_trace(trace_ctx)

        return generated_path

    @staticmethod
    def _load_ppt_prompt(topic: str, context_materials: str) -> str:
        """
        动态热加载用户可编辑的 PPT Prompt 模板文件
        若模板文件存在，则读取并替换 {topic} 与 {context_materials}；
        若不存在或发生异常，安全回退到内置标准提示词。
        """
        template_file = config.PPT_PROMPT_TEMPLATE_PATH
        if template_file.is_file():
            try:
                template_str = template_file.read_text(encoding="utf-8")
                return template_str.format(topic=topic, context_materials=context_materials)
            except Exception:
                pass

        return f"""请针对主题：“{topic}”，综合以下参考文档资料，规划并撰写一份现代 16:9 商业汇报演示文稿的内容。

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
