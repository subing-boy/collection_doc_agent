"""
==============================================================================
模块名称: storage/vector_store.py
功能描述: 向量检索存储引擎抽象基类与轻量级嵌入式实现
          负责切片向量的内存/持久化存储与基于余弦相似度的相似性排重检索。
          返回结果完整保留源文档、物理页码、章节标题坐标，专为 RAG 精确溯源打造。
可移植性: 零外部重型依赖，完全基于标准库 math 和已建好的 MetadataDB。
==============================================================================
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from storage.metadata_db import MetadataDB
from llm.embeddings import BaseEmbeddingProvider, PurePythonEmbeddingProvider


class BaseVectorStore(ABC):
    """
    向量存储抽象基类 (Interface)
    后续若迁移至 LanceDB, ChromaDB 或 Milvus，只需继承本接口。
    """

    @abstractmethod
    def add_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        """
        批量添加切片及其向量
        :param chunks: 切片字典列表，包含 content, vector, source_filename 等元数据
        """
        pass

    @abstractmethod
    def search(
        self,
        query_vector: List[float],
        top_k: int = 4,
        filter_doc_id: Optional[str] = None,
        keywords: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        根据查询向量检索 Top-K 最相关切片 (支持关键词精准双路混合检索)
        :param query_vector: 问题的稠密向量
        :param top_k: 召回数量
        :param filter_doc_id: 可选的文档过滤范围（限定在某文档内查找）
        :param keywords: 可选的核心关键词列表（用于倒排精确命中加权）
        :return: 包含相似度得分与溯源信息的切片列表
        """
        pass

    @abstractmethod
    def delete_doc_chunks(self, doc_id: str) -> None:
        """
        从存储与内存索引中同步移除指定文档的全部旧切片
        """
        pass


class EmbeddedVectorStore(BaseVectorStore):
    """
    轻量级嵌入式向量存储实现
    特点：
    1. 基于 SQLite 持久化切片向量，同时在内存中维护轻量索引，毫秒级响应。
    2. 支持按文档限定范围，支持余弦相似度计算与严格阈值过滤。
    3. 零跨进程通信，随代码一键打包移植。
    """

    def __init__(
        self,
        metadata_db: Optional[MetadataDB] = None,
        embedding_provider: Optional[BaseEmbeddingProvider] = None
    ) -> None:
        self.db = metadata_db or MetadataDB()
        self.embedding_provider = embedding_provider or PurePythonEmbeddingProvider()
        # 内存索引缓存：缓存已加载的 chunks
        self._cached_chunks: List[Dict[str, Any]] = []
        self._reload_cache()

    def _reload_cache(self) -> None:
        """
        从 SQLite 数据库中重新同步切片与向量到内存缓存
        """
        self._cached_chunks = self.db.get_all_chunks()

    def add_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        """
        添加切片：如果切片尚无向量，则自动调用 embedding_provider 计算，并持久化到 SQLite
        """
        if not chunks:
            return

        for chunk in chunks:
            if "vector" not in chunk or not chunk["vector"]:
                chunk["vector"] = self.embedding_provider.embed_text(chunk["content"])

        # 写入数据库持久化
        self.db.save_chunks(chunks)

        # 刷新内存缓存
        self._reload_cache()

    def delete_doc_chunks(self, doc_id: str) -> None:
        """
        从 SQLite 与内存向量索引中级联清除指定文档的全部旧切片
        """
        self.db.delete_chunks_by_doc_id(doc_id)
        self._reload_cache()

    def search(
        self,
        query_vector: List[float],
        top_k: int = 4,
        filter_doc_id: Optional[str] = None,
        keywords: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        执行双路混合检索：
        路 1: 语义向量余弦相似度计算 (0.0 ~ 1.0)
        路 2: 核心关键词/专有名词精确命中加权 (0.0 ~ 1.0)
        最终得分: 动态融合两路信号，长句口语下专有名词切片也能精准直达 Top-1
        """
        if not self._cached_chunks:
            self._reload_cache()

        scored_results: List[Dict[str, Any]] = []
        clean_kws = [k.lower().strip() for k in (keywords or []) if k.strip()]

        for item in self._cached_chunks:
            # 支持根据 doc_id 过滤
            if filter_doc_id and item.get("doc_id") != filter_doc_id:
                continue

            item_vec = item.get("vector", [])
            if not item_vec:
                continue

            # 1. 语义向量相似度 (归一化至 0.0 ~ 1.0)
            v_similarity = max(0.0, BaseEmbeddingProvider.cosine_similarity(query_vector, item_vec))

            # 2. 关键词精准命中打分
            kw_score = 0.0
            if clean_kws:
                loc_lower = item.get("location_label", "").lower()
                content_lower = item.get("content", "").lower()
                for kw in clean_kws:
                    # 标题/章节层级直接命中 (强信号)
                    if kw in loc_lower:
                        kw_score += 0.6 if " " in kw else 0.4
                    # 正文内容命中
                    if kw in content_lower:
                        kw_score += 0.4 if " " in kw else 0.25
                kw_score = min(1.0, kw_score)

            # 3. 动态融合权重 (统一量纲)
            if clean_kws:
                final_score = 0.5 * v_similarity + 0.5 * kw_score
            else:
                final_score = v_similarity

            # 拷贝一份数据并注入得分
            result_item = dict(item)
            result_item["score"] = round(final_score, 4)
            result_item["vector_similarity"] = round(v_similarity, 4)
            result_item["keyword_score"] = round(kw_score, 4)
            scored_results.append(result_item)

        # 依据得分从高到低排序
        scored_results.sort(key=lambda x: x["score"], reverse=True)

        return scored_results[:top_k]
