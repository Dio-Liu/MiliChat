"""Google Gemini 驱动"""
from typing import Dict, Any, List, Iterator
import google.generativeai as genai
from PIL import Image

from .base import BaseLLM


class GeminiDriver(BaseLLM):
    """
    Google Gemini 驱动
    
    适用于：
    - Gemini Pro
    - Gemini Pro Vision
    - Gemini 2.5 Flash
    """
    
    def __init__(self, api_key: str, base_url: str = None, model_name: str = "gemini-pro", **kwargs):
        """
        初始化 Gemini 驱动
        
        Args:
            api_key: Google API Key
            base_url: 自定义 Base URL (可选，用于中转)
            model_name: 模型名称
            **kwargs: 其他参数
        """
        super().__init__(api_key, base_url, model_name, **kwargs)
        
        # 配置 Gemini
        genai.configure(api_key=self.api_key)
        
        # 如果提供了自定义 base_url，需要通过 OpenAI 兼容接口调用
        # 否则使用原生 Gemini SDK
        self.use_native = (base_url is None)
        
        if self.use_native:
            self.model = genai.GenerativeModel(self.model_name)
            print(f"✅ [GeminiDriver] 已初始化 (原生): {model_name}")
        else:
            # 如果用户提供了中转 URL，使用 OpenAI 兼容模式
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            print(f"✅ [GeminiDriver] 已初始化 (OpenAI 兼容): {model_name} @ {base_url}")
    
    def chat(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        """
        非流式对话
        
        Args:
            messages: 消息列表
            **kwargs: 额外参数
        
        Returns:
            AI 回复文本
        """
        if self.use_native:
            # 原生 Gemini SDK
            # 需要转换消息格式
            history = []
            for msg in messages[:-1]:
                history.append({
                    "role": "user" if msg["role"] == "user" else "model",
                    "parts": [msg["content"]]
                })
            
            chat = self.model.start_chat(history=history)
            response = chat.send_message(messages[-1]["content"])
            return response.text
        else:
            # OpenAI 兼容模式
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                **kwargs
            )
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
        if self.use_native:
            # 原生 Gemini SDK 流式输出
            history = []
            for msg in messages[:-1]:
                history.append({
                    "role": "user" if msg["role"] == "user" else "model",
                    "parts": [msg["content"]]
                })
            
            chat = self.model.start_chat(history=history)
            response = chat.send_message(messages[-1]["content"], stream=True)
            
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        else:
            # OpenAI 兼容模式
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                stream=True,
                **kwargs
            )
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
    
    def supports_vision(self) -> bool:
        """
        是否支持视觉输入
        
        Returns:
            True (Gemini 大部分模型都支持视觉)
        """
        return True
    
    def supports_tools(self) -> bool:
        """
        是否支持工具调用
        
        Returns:
            True (Gemini 支持 Function Calling)
        """
        return True
