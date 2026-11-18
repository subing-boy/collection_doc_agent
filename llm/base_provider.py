"""
==============================================================================
模块名称: llm/base_provider.py
功能描述: 大语言模型 (LLM) 抽象基类定义
          为所有底层模型（DeepSeek, OpenAI, Claude, 本地模型）提供统一接口。
          通过面向对象的多态设计，确保核心业务与具体大模型供应商解耦。
可移植性: 仅使用 Python 内置 typing 和 abc 模块，纯抽象定义。
==============================================================================
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class BaseLLMProvider(ABC):
    """
    大语言模型提供商抽象基类 (Interface)
    所有具体的大模型适配器均须实现本类所定义的方法。
    """

    def __init__(self, api_key: str, base_url: str, model_name: str, **kwargs: Any) -> None:
        """
        初始化大模型提供商实例
        :param api_key: 访问凭据密钥
        :param base_url: API 基础端点地址 (如 https://api.deepseek.com)
        :param model_name: 调用的模型名称 (如 deepseek-chat)
        :param kwargs: 扩展参数（如超时时间、重试次数等）
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.extra_config = kwargs

    @abstractmethod
    def chat_complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """
        同步文本对话补全接口 (核心方法)
        
        :param messages: 符合标准格式的消息列表，例如:
                        [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        :param temperature: 采样温度 (0.0~2.0)，越低越严谨，越高越发散
        :param max_tokens: 最大输出 token 数
        :param json_mode: 是否强制要求大模型返回合法有效的 JSON 对象
        :return: 模型返回的文本结果 (纯字符串)
        :raises Exception: 当网络中断、Token超限、鉴权失败时抛出明确异常
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        健康检查接口
        检查当前配置与 API Key 是否具备调用条件（如是否配置了 key）
        :return: 布尔值，True 表示配置就绪
        """
        pass
