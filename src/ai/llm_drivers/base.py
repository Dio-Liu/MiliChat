"""LLM 基类 - 定义统一接口"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Iterator


class BaseLLM(ABC):
    """
    LLM 基类
    
    所有 LLM 驱动必须实现此接口，以确保在 Agent 中可以无缝切换
    """
    
    def __init__(self, api_key: str, base_url: str = None, model_name: str = None, **kwargs):
        """
        初始化 LLM
        
        Args:
            api_key: API Key
            base_url: API Base URL (可选)
            model_name: 模型名称 (可选)
            **kwargs: 其他参数
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.extra_params = kwargs
    
    @abstractmethod
    def chat(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        """
        非流式对话
        
        Args:
            messages: 消息列表，格式：[{"role": "user", "content": "..."}]
            **kwargs: 额外参数（如 temperature, max_tokens, tools 等）
        
        Returns:
            AI 回复文本
        """
        pass
    
    @abstractmethod
    def chat_stream(self, messages: List[Dict[str, Any]], **kwargs) -> Iterator[str]:
        """
        流式对话
        
        Args:
            messages: 消息列表
            **kwargs: 额外参数
        
        Yields:
            AI 回复的文本片段
        """
        pass
    
    def supports_vision(self) -> bool:
        """
        是否支持视觉输入
        
        Returns:
            True 表示支持，False 表示不支持
        """
        return False
    
    def supports_tools(self) -> bool:
        """
        是否支持工具调用 (Function Calling)
        
        Returns:
            True 表示支持，False 表示不支持
        """
        return False
