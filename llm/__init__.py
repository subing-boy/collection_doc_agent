"""
==============================================================================
模块名称: llm/__init__.py
功能描述: LLM 与 Embedding 模块工厂
          集中对外暴露模型实例化函数，屏蔽底层细节，提供优雅的统一入口。
==============================================================================
"""

from typing import Optional
import config
from llm.base_provider import BaseLLMProvider
from llm.deepseek_provider import DeepSeekProvider
from llm.embeddings import BaseEmbeddingProvider, PurePythonEmbeddingProvider


def get_llm_provider(provider_type: Optional[str] = None) -> BaseLLMProvider:
    """
    获取大语言模型实例的工厂方法
    :param provider_type: 提供商类型（默认从 config 读取，如 "deepseek"）
    :return: 实现了 BaseLLMProvider 接口的模型客户端
    """
    p_type = (provider_type or config.DEFAULT_LLM_PROVIDER).lower()

    if p_type == "deepseek":
        return DeepSeekProvider(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            model_name=config.DEEPSEEK_MODEL,
            timeout=config.LLM_TIMEOUT,
            max_retries=config.LLM_MAX_RETRIES,
        )
    else:
        # 预留可扩展分支
        raise NotImplementedError(
            f"暂不支持的大模型提供商: {p_type}。如需扩展，请在 llm/ 目录下新增适配类并在工厂中注册。"
        )


def get_embedding_provider() -> BaseEmbeddingProvider:
    """
    获取向量化工具实例的工厂方法
    默认返回高移植性的纯 Python 稠密向量提供器
    """
    return PurePythonEmbeddingProvider(dimension=128)
