"""LLM 工厂 - 根据配置创建对应的 LLM 驱动"""
from typing import Dict, Any

from .base import BaseLLM
from .openai_driver import OpenAIDriver
from .gemini_driver import GeminiDriver


def get_llm_driver(config: Dict[str, Any]) -> BaseLLM:
    """
    根据配置创建 LLM 驱动
    
    Args:
        config: 配置字典，包含以下字段：
            - provider: 提供商 ("deepseek", "openai", "gemini", "ollama")
            - api_key: API Key
            - base_url: API Base URL (可选)
            - model_name: 模型名称
            - temperature: 温度参数 (可选)
            - max_tokens: 最大输出长度 (可选)
    
    Returns:
        BaseLLM 实例
    
    Raises:
        ValueError: 如果提供商不支持
    """
    provider = config.get("provider", "").lower()
    api_key = config.get("api_key")
    base_url = config.get("base_url")
    model_name = config.get("model_name")
    
    # 参数校验
    if not api_key:
        raise ValueError("❌ API Key 不能为空")
    
    if not model_name:
        raise ValueError("❌ Model Name 不能为空")
    
    # 根据提供商创建对应的驱动
    if provider in ["deepseek", "openai"]:
        # DeepSeek 和 OpenAI 都使用 OpenAI 兼容接口
        return OpenAIDriver(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            temperature=config.get("temperature", 1.0),
            max_tokens=config.get("max_tokens", 2000)
        )
    
    elif provider == "gemini":
        return GeminiDriver(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            temperature=config.get("temperature", 1.0),
            max_tokens=config.get("max_tokens", 2000)
        )
    
    elif provider == "ollama":
        # Ollama 使用 OpenAI 兼容接口（本地运行）
        if not base_url:
            base_url = "http://localhost:11434/v1"  # Ollama 默认地址
        
        return OpenAIDriver(
            api_key="ollama",  # Ollama 不需要真实 API Key
            base_url=base_url,
            model_name=model_name,
            temperature=config.get("temperature", 1.0),
            max_tokens=config.get("max_tokens", 2000)
        )
    
    else:
        raise ValueError(
            f"❌ 不支持的 LLM 提供商: {provider}\n"
            f"💡 支持的提供商: deepseek, openai, gemini, ollama"
        )


def get_vision_driver(config: Dict[str, Any]) -> BaseLLM:
    """
    创建视觉模型驱动（用于屏幕感知）
    
    Args:
        config: 配置字典
    
    Returns:
        支持视觉的 LLM 驱动
    """
    provider = config.get("provider", "").lower()
    
    # 如果使用 Gemini (通过中转 API 或原生)
    if provider == "gemini":
        return GeminiDriver(
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
            model_name=config.get("model_name", "gemini-2.5-flash")
        )
    
    # 如果使用 OpenAI Vision
    elif provider == "openai":
        return OpenAIDriver(
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
            model_name=config.get("model_name", "gpt-4o")
        )
    
    else:
        raise ValueError(f"❌ 不支持的视觉模型提供商: {provider}")
