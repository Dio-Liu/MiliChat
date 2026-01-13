"""
模态路由器 (Modality Router)
根据屏幕内容的文字密集度，决定使用文本流 (DeepSeek) 还是视觉流 (Gemini)
"""
import re
import asyncio
from typing import Dict, Any
from PIL import Image
import numpy as np

# 尝试导入 RapidOCR
try:
    from rapidocr_onnxruntime import RapidOCR
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    print("⚠️ [Router] RapidOCR 未安装，将默认使用视觉流。")
    print("💡 安装提示: pip install rapidocr-onnxruntime")

from src.core.config import (
    ROUTER_TEXT_THRESHOLD,
    ROUTER_KEYWORDS,
    ROUTER_SENSITIVE_PATTERNS
)


class ModalityRouter:
    """
    模态路由器
    
    核心职责：
    1. 对截图执行 OCR 识别
    2. 分析文字密集度和关键词
    3. 决定使用哪种处理流程：
       - TEXT: 使用 DeepSeek 文本模型（成本极低）
       - VISION: 使用 Gemini 视觉模型（成本较高，但能看懂图像）
    """
    
    def __init__(self):
        """初始化路由器"""
        self.use_ocr = HAS_OCR
        
        if not self.use_ocr:
            print("⚠️ [Router] OCR 功能不可用，所有请求将路由到 VISION 流")
        else:
            self.ocr_engine = RapidOCR()
            print("✅ [Router] RapidOCR 已就绪")
    
    async def route(self, image: Image.Image) -> Dict[str, Any]:
        """
        对图像进行路由决策
        
        Args:
            image: PIL Image 对象（屏幕截图）
        
        Returns:
            路由结果字典:
            {
                "mode": "TEXT" | "VISION",
                "content": str (OCR文本) | Image (原图),
                "reason": str (决策理由，用于日志)
            }
        """
        # 如果没有 OCR 能力，直接走视觉流
        if not self.use_ocr:
            return {
                "mode": "VISION",
                "content": image,
                "reason": "no_ocr_available"
            }
        
        # Step 1: 执行 OCR 识别
        try:
            # 将 PIL Image 转换为 numpy array（RapidOCR 需要）
            img_array = np.array(image)
            
            # RapidOCR 识别，返回 (result, elapse_list)
            # result 是列表，每项为 [box, text, confidence]
            ocr_output = self.ocr_engine(img_array)
            
            # 处理返回值 - RapidOCR 返回 tuple: (result, elapse_list)
            if isinstance(ocr_output, tuple) and len(ocr_output) >= 1:
                result = ocr_output[0]
            else:
                result = ocr_output
            
            # 提取所有文本并合并
            if result:
                extracted_text = '\n'.join([item[1] for item in result])
            else:
                extracted_text = ''
            
            extracted_text = extracted_text.strip()
            
        except Exception as e:
            print(f"❌ [Router] OCR 失败: {e}")
            import traceback
            traceback.print_exc()
            # OCR 失败时回退到视觉流
            return {
                "mode": "VISION",
                "content": image,
                "reason": "ocr_error"
            }
        
        # Step 2: 隐私过滤 (极其重要！)
        filtered_text = self._sanitize_text(extracted_text)
        
        # Step 3: 决策逻辑
        char_count = len(filtered_text)
        has_keyword = self._check_keywords(filtered_text)
        
        # 日志输出
        print(f"📊 [Router] OCR 识别: {char_count} 字符")
        if has_keyword:
            print(f"🔑 [Router] 检测到关键词")
        
        # 决策：字数达标 OR 包含关键词 → 文本流
        if char_count >= ROUTER_TEXT_THRESHOLD or has_keyword:
            return {
                "mode": "TEXT",
                "content": filtered_text,
                "reason": f"text_rich({char_count})" + ("_keyword" if has_keyword else "")
            }
        else:
            # 文字稀疏 → 视觉流
            return {
                "mode": "VISION",
                "content": image,
                "reason": f"text_sparse({char_count})"
            }
    
    def _sanitize_text(self, text: str) -> str:
        """
        隐私过滤 - 移除敏感信息
        
        Args:
            text: OCR 识别的原始文本
        
        Returns:
            过滤后的文本
        """
        sanitized = text
        
        # 应用所有敏感词模式
        for pattern in ROUTER_SENSITIVE_PATTERNS:
            sanitized = re.sub(pattern, '[REDACTED]', sanitized, flags=re.IGNORECASE)
        
        return sanitized
    
    def _check_keywords(self, text: str) -> bool:
        """
        检查文本中是否包含关键词
        
        Args:
            text: 待检查的文本
        
        Returns:
            是否包含关键词
        """
        text_lower = text.lower()
        for keyword in ROUTER_KEYWORDS:
            if keyword.lower() in text_lower:
                return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取路由器统计信息（可用于调试）
        
        Returns:
            统计信息字典
        """
        return {
            "ocr_available": self.use_ocr,
            "text_threshold": ROUTER_TEXT_THRESHOLD,
            "keywords_count": len(ROUTER_KEYWORDS)
        }
