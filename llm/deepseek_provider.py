"""
==============================================================================
模块名称: llm/deepseek_provider.py
功能描述: DeepSeek API 具体驱动实现
          兼容 OpenAI 标准接口协议（/chat/completions），采用标准 requests 库实现，
          内置超时保护、指数退避重试、JSON 模式以及结构化错误处理。
可移植性: 仅依赖 requests 库，免除对特定 openai sdk 版本兼容性问题的困扰。
==============================================================================
"""

import json
import time
from typing import List, Dict, Any, Optional
import requests

from llm.base_provider import BaseLLMProvider


class DeepSeekProvider(BaseLLMProvider):
    """
    DeepSeek 大模型客户端封装
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model_name: str = "deepseek-chat",
        timeout: int = 60,
        max_retries: int = 3,
        **kwargs: Any
    ) -> None:
        """
        初始化 DeepSeek 客户端
        :param api_key: DeepSeek API Key (如未配置，系统可在无 key 模式下启动骨架自测)
        :param base_url: API 请求根路径
        :param model_name: 调用的模型型号 (如 deepseek-chat 或 deepseek-reasoner)
        :param timeout: 单次请求超时时间（秒）
        :param max_retries: 遇偶发网络抖动时的最大重试次数
        """
        super().__init__(api_key, base_url, model_name, **kwargs)
        self.timeout = timeout
        self.max_retries = max_retries

    def is_available(self) -> bool:
        """
        检查 API Key 是否有效配置
        """
        return bool(self.api_key and self.api_key.strip() and not self.api_key.startswith("your_"))

    def chat_complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """
        向 DeepSeek 发起聊天补全请求
        """
        # 1. 前置检查：检查 Key 是否已就绪
        if not self.is_available():
            raise ValueError(
                "【配置缺失】未检测到有效的 DEEPSEEK_API_KEY！\n"
                "请在项目根目录的 .env 文件中填入实际的 API Key：\n"
                "  DEEPSEEK_API_KEY=sk-xxxxxx\n"
                "如暂未配置，可先通过骨架单测验证无 API 依赖的解析与存储流程。"
            )

        # 2. 构造请求头与端点
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # 3. 构造请求体 payload
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": False
        }

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        # 如果开启了 JSON 模式，指定输出格式为 json_object
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        # 4. 执行重试循环
        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                
                # 检查 HTTP 状态码
                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices", [])
                    if not choices:
                        raise ValueError("DeepSeek API 返回结果为空 (无 choices 节点)")
                    content = choices[0].get("message", {}).get("content", "")
                    return content
                
                # 特殊状态码捕获
                elif response.status_code == 401:
                    raise PermissionError(f"【鉴权失败】DeepSeek API Key 无效或过期: {response.text}")
                elif response.status_code == 429:
                    # 速率限制或余额不足，等待后重试
                    wait_time = attempt * 2
                    time.sleep(wait_time)
                    continue
                else:
                    response.raise_for_status()

            except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
                last_exception = e
                # 指数退避等待
                time.sleep(attempt * 1.5)

        raise RuntimeError(f"调用 DeepSeek API 失败，重试 {self.max_retries} 次后仍未成功: {last_exception}")
