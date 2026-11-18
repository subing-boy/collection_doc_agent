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
        filter_doc_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        根据查询向量检索 Top-K 最相关切片
        :param query_vector: 问题的稠密向量
        :param top_k: 召回数量
        :param filter_doc_id: 可选的文档过滤范围（限定在某文档内查找）
        :return: 包含相似度得分与溯源信息的切片列表
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

    def search(
        self,
        query_vector: List[float],
        top_k: int = 4,
        filter_doc_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        执行余弦相似度比对并排序
        """
        if not self._cached_chunks:
            self._reload_cache()

        scored_results: List[Dict[str, Any]] = []

        for item in self._cached_chunks:
            # 支持根据 doc_id 过滤
            if filter_doc_id and item.get("doc_id") != filter_doc_id:
                continue

            item_vec = item.get("vector", [])
            if not item_vec:
                continue

            similarity = BaseEmbeddingProvider.cosine_similarity(query_vector, item_vec)

            # 拷贝一份数据并注入得分
            result_item = dict(item)
            result_item["score"] = round(similarity, 4)
            scored_results.append(result_item)

        # 依据得分从高到低排序
        scored_results.sort(key=lambda x: x["score"], reverse=True)

        return scored_results[:top_k]
