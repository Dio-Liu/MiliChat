"""OpenAI 兼容驱动 - 支持 DeepSeek, OpenAI, 以及任何 OpenAI 兼容的 API"""
from typing import Dict, Any, List, Iterator
from openai import OpenAI

from .base import BaseLLM


class OpenAIDriver(BaseLLM):
    """
    OpenAI 兼容驱动
    
    适用于：
    - OpenAI GPT-4, GPT-3.5
    - DeepSeek
    - 任何使用 OpenAI API 格式的服务
    """
    
    def __init__(self, api_key: str, base_url: str = None, model_name: str = "gpt-3.5-turbo", **kwargs):
        """
        初始化 OpenAI 驱动
        
        Args:
            api_key: API Key
            base_url: API Base URL (如果使用 DeepSeek 或中转服务)
            model_name: 模型名称
            **kwargs: 其他参数
        """
        super().__init__(api_key, base_url, model_name, **kwargs)
        
        # 初始化 OpenAI 客户端
        client_params = {"api_key": self.api_key}
        if self.base_url:
            client_params["base_url"] = self.base_url
        
        self.client = OpenAI(**client_params)
        self.raw_client = self.client  # 提供原始客户端访问
        print(f"✅ [OpenAIDriver] 已初始化: {model_name} @ {base_url or 'api.openai.com'}")
    
    def chat(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        """
        非流式对话
        
        Args:
            messages: 消息列表
            **kwargs: 额外参数（temperature, max_tokens, tools 等）
        
        Returns:
            AI 回复文本
        """
        params = {
            "model": self.model_name,
            "messages": messages,
            **kwargs
        }
        
        response = self.client.chat.completions.create(**params)
        return response.choices[0].message.content
    
    def chat_stream(self, messages: List[Dict[str, Any]], **kwargs) -> Iterator[str]:
        """
        流式对话
        
        Args:
            messages: 消息列表
            **kwargs: 额外参数
        
        Yields:
            AI 回复的文本片段
        """
        params = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            **kwargs
        }
        
        stream = self.client.chat.completions.create(**params)
        
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    def supports_vision(self) -> bool:
        """
        是否支持视觉输入
        
        Returns:
            True 如果模型支持视觉 (如 gpt-4-vision-preview)
        """
        vision_models = ["gpt-4-vision", "gpt-4o", "gpt-4-turbo"]
        return any(vm in self.model_name.lower() for vm in vision_models)
    
    def supports_tools(self) -> bool:
        """
        是否支持工具调用
        
        Returns:
            True (OpenAI 兼容接口都支持工具调用)
        """
        return True
