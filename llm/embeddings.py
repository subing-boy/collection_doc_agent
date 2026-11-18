"""
==============================================================================
模块名称: llm/embeddings.py
功能描述: 文本向量化 (Embeddings) 接口与实现
          提供纯 Python 零依赖的字符 N-Gram 哈希稠密向量计算（默认激活），
          确保在任意机器、Python 3.14 及无 GPU/C 编译环境下即开即用；
          同时保留 Sentence-Transformers 与外部 API 的标准接入插槽。
可移植性: 零外部编译依赖，仅使用 Python 内置 math, hashlib 模块。
==============================================================================
"""

import math
import hashlib
from abc import ABC, abstractmethod
from typing import List


class BaseEmbeddingProvider(ABC):
    """
    文本向量化抽象基类
    """

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """
        计算单个文本片段的稠密向量
        :param text: 输入文本
        :return: 归一化后的浮点数列表 (向量)
        """
        pass

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量计算文本向量
        :param texts: 文本列表
        :return: 向量列表
        """
        return [self.embed_text(t) for t in texts]

    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """
        纯 Python 计算两个向量之间的余弦相似度
        cos(A, B) = (A · B) / (||A|| * ||B||)
        """
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm_a = math.sqrt(sum(a * a for a in vec1))
        norm_b = math.sqrt(sum(b * b for b in vec2))

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return dot_product / (norm_a * norm_b)


class PurePythonEmbeddingProvider(BaseEmbeddingProvider):
    """
    纯 Python 零依赖轻量级稠密向量实现 (基于字符 N-Gram 哈希与 L2 归一化)
    特点：
    1. 零 C++ 扩展、无需 PyTorch 或 NumPy，在任何 Python 版本（包括 3.14）秒级运行。
    2. 对中文分词、中英夹杂具有稳定的特征映射与余弦相似度区分度。
    3. 适合做离线自测、轻量部署及无需额外网络开销的本地 RAG。
    """

    def __init__(self, dimension: int = 128) -> None:
        """
        :param dimension: 目标向量维度 (默认 128 维)
        """
        self.dimension = dimension

    def embed_text(self, text: str) -> List[float]:
        """
        提取字符 N-gram (1-gram 和 2-gram) 并哈希映射到固定维度
        """
        clean_text = text.strip().lower()
        if not clean_text:
            return [0.0] * self.dimension

        vector = [0.0] * self.dimension

        # 提取 1-gram 和 2-gram 特征
        tokens = []
        for i in range(len(clean_text)):
            tokens.append(clean_text[i])
            if i + 1 < len(clean_text):
                tokens.append(clean_text[i:i+2])

        # 哈希投影与累加权重
        for token in tokens:
            # 使用 md5 哈希映射到维度索引和符号
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            sign = 1.0 if (h >> 16) % 2 == 0 else -1.0
            vector[idx] += sign

        # L2 正则化 (归一化为单位向量)
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0.0:
            vector = [x / norm for x in vector]

        return vector


# ==============================================================================
# 扩展预留接口 (如用户后续安装了 sentence-transformers 可直接切换)
# ==============================================================================

class SentenceTransformersEmbeddingProvider(BaseEmbeddingProvider):
    """
    【扩展预留】基于 HuggingFace / sentence-transformers (如 BAAI/bge-small-zh) 的向量化
    当环境中安装了 sentence_transformers 库时可启用本类。
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5") -> None:
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model_name)
        except ImportError:
            raise ImportError(
                "未检测到 sentence_transformers 库！"
                "如需使用本地深度学习模型，请先安装: pip install sentence-transformers"
            )

    def embed_text(self, text: str) -> List[float]:
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()
