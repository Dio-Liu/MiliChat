"""视觉感知模块 - 使用智能路由 (OCR + 双模型) 分析屏幕内容"""
import time
import json
import base64
import asyncio
import random
import traceback
from PIL import ImageGrab
from openai import OpenAI
from PySide6.QtCore import QThread, Signal

from src.core.config import (
    VISION_API_KEY, 
    VISION_API_BASE_URL,
    VISION_CHECK_INTERVAL_MIN,
    VISION_CHECK_INTERVAL_MAX,
    VISION_SYSTEM_PROMPTS,  # ✅ 改成列表
    VISION_SYSTEM_PROMPT_ABSTRACT,  # ★★★ 新增：用于识别抽象模式
    VISION_MODEL_NAME
)

# ★★★ 导入路由器 ★★★
from src.ai.router import ModalityRouter


class VisionSensor:
    """视觉传感器 - 负责截图和智能路由分析"""
    
    def __init__(self, agent_ref=None):
        """
        初始化 客户端和路由器
        
        Args:
            agent_ref: DeepSeekAgent 实例的引用（用于调用文本吐槽功能）
        """
        self.agent = agent_ref
        
        # 初始化路由器
        self.router = ModalityRouter()
        print(f"✅ [Vision] 路由器已初始化 (OCR: {self.router.use_ocr})")
        
        # ★★★ 新增：视觉吐槽历史记录 (用于防止重复) ★★★
        from collections import deque
        self.vision_history = deque(maxlen=5)  # 保留最近5次视觉吐槽
        self.last_scene_description = None  # 上一次场景描述
        
        if not VISION_API_KEY or "你的" in VISION_API_KEY:
            print("⚠️ [Vision] 未配置 VISION_API_KEY，视觉功能禁用。")
            self.client = None
            return
        
        try:
            self.client = OpenAI(
                api_key=VISION_API_KEY,
                base_url=VISION_API_BASE_URL
            )
            print(f"✅ [Vision] 已连接到 API: {VISION_API_BASE_URL}")
            print(f"✅ [Vision] 使用模型: {VISION_MODEL_NAME}")
        except Exception as e:
            print(f"❌ [Vision] 客户端初始化失败: {e}")
            traceback.print_exc()
            self.client = None
    
    def capture_screen(self):
        """截取屏幕（支持灵活的裁剪配置）"""
        try:
            full_screenshot = ImageGrab.grab()
            width, height = full_screenshot.size
            
            # 根据配置决定裁剪范围
            from src.core.config import (
                VISION_SCREEN_CROP_RATIO,
                VISION_SCREEN_CROP_TOP,
                VISION_SCREEN_CROP_BOTTOM
            )
            
            # 计算四个边的裁剪量
            # 左右边的裁剪（基于 VISION_SCREEN_CROP_RATIO）
            if VISION_SCREEN_CROP_RATIO >= 1.0:
                margin_x = 0
            else:
                margin_x = int(width * (1 - VISION_SCREEN_CROP_RATIO) / 2)
            
            # 顶部裁剪
            margin_top = int(height * VISION_SCREEN_CROP_TOP)
            
            # 底部裁剪
            margin_bottom = int(height * VISION_SCREEN_CROP_BOTTOM)
            
            # 构建裁剪框（left, top, right, bottom）
            bbox = (
                margin_x,                           # left
                margin_top,                         # top
                width - margin_x,                   # right
                height - margin_bottom              # bottom
            )
            
            screenshot = full_screenshot.crop(bbox)
            
            # 日志输出
            crop_info = []
            if VISION_SCREEN_CROP_RATIO < 1.0:
                crop_percent = int(VISION_SCREEN_CROP_RATIO * 100)
                crop_info.append(f"横向{crop_percent}%")
            
            if VISION_SCREEN_CROP_TOP > 0:
                crop_info.append(f"顶部{int(VISION_SCREEN_CROP_TOP*100)}%")
            
            if VISION_SCREEN_CROP_BOTTOM > 0:
                crop_info.append(f"底部{int(VISION_SCREEN_CROP_BOTTOM*100)}%")
            
            if crop_info:
                crop_desc = "（去除" + "+".join(crop_info) + "）"
            else:
                crop_desc = "（全屏）"
            
            print(f"📸 [Vision] 截图: {width}x{height} → {screenshot.size[0]}x{screenshot.size[1]} {crop_desc}")
            
            return screenshot
        except Exception as e:
            print(f"❌ [Vision] 截图失败: {e}")
            return None
    
    def image_to_base64(self, image):
        """将 PIL Image 转换为 base64 字符串"""
        import io
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_data = buffered.getvalue()
        return base64.b64encode(img_data).decode()
    
    def analyze(self, history=None, long_term_memory=""):
        """
        智能分析屏幕内容（路由决策）
        
        流程：
        0. 随机选择 prompt 类型（毒舌/温柔/抽象）- 根据时间动态调整比例
        1. 如果是抽象模式 → 跳过截图，直接生成抽象内容
        2. 否则 → 截图 → 路由决策 → 选择 TEXT/VISION 流
        
        Args:
            history: 对话历史列表 [(role, content), ...]
            long_term_memory: 长期记忆文本
            
        Returns:
            tuple: (response_text, mode) - (LLM 的原始回复文本, 使用的模型类型)
            (None, None): 分析失败时返回
        """
        if not self.client:
            return None, None
        
        # Step 0: 根据时间动态调整 prompt 比例
        from src.core.config import VISION_SYSTEM_PROMPT_TOXIC, VISION_SYSTEM_PROMPT_GENTLE
        import datetime
        
        current_hour = datetime.datetime.now().hour
        
        # 白天时段 (6:00-18:00): 毒舌比例更高
        # 晚上时段 (18:00-6:00): 温柔比例更高
        if 6 <= current_hour < 18:
            # 白天：TOXIC:GENTLE:ABSTRACT = 6:2:2
            prompt_pool = [
                VISION_SYSTEM_PROMPT_TOXIC,
                VISION_SYSTEM_PROMPT_TOXIC,
                VISION_SYSTEM_PROMPT_TOXIC,
                VISION_SYSTEM_PROMPT_TOXIC,
                VISION_SYSTEM_PROMPT_TOXIC,
                VISION_SYSTEM_PROMPT_TOXIC,
                VISION_SYSTEM_PROMPT_GENTLE,
                VISION_SYSTEM_PROMPT_GENTLE,
                VISION_SYSTEM_PROMPT_ABSTRACT,
                VISION_SYSTEM_PROMPT_ABSTRACT
            ]
            time_mode = "白天"
        else:
            # 晚上：TOXIC:GENTLE:ABSTRACT = 2:6:2
            prompt_pool = [
                VISION_SYSTEM_PROMPT_TOXIC,
                VISION_SYSTEM_PROMPT_TOXIC,
                VISION_SYSTEM_PROMPT_TOXIC,
                VISION_SYSTEM_PROMPT_GENTLE,
                VISION_SYSTEM_PROMPT_GENTLE,
                VISION_SYSTEM_PROMPT_GENTLE,
                VISION_SYSTEM_PROMPT_GENTLE,
                VISION_SYSTEM_PROMPT_GENTLE,
                VISION_SYSTEM_PROMPT_ABSTRACT,
                VISION_SYSTEM_PROMPT_ABSTRACT
            ]
            time_mode = "晚上"
        
        selected_prompt = random.choice(prompt_pool)
        
        # 打印调试信息
        if selected_prompt == VISION_SYSTEM_PROMPT_TOXIC:
            prompt_type = "毒舌"
        elif selected_prompt == VISION_SYSTEM_PROMPT_GENTLE:
            prompt_type = "温柔"
        else:
            prompt_type = "抽象"
        print(f"🎭 [Vision] {time_mode}模式 - 选择 Prompt: {prompt_type}")
        
        # ★★★ 判断是否为抽象模式 ★★★
        if selected_prompt == VISION_SYSTEM_PROMPT_ABSTRACT:
            print(f"🎪 [Vision] 触发抽象模式！跳过截图，准备整活...")
            # 抽象模式：不需要截图，直接生成内容
            response = self._analyze_abstract(selected_prompt, long_term_memory)
            return response, "Abstract"
        
        # 普通模式：需要截图
        # Step 1: 截图
        screenshot = self.capture_screen()
        if not screenshot:
            return None, None
        
        # Step 2: 路由决策 (OCR + 判断)
        try:
            # 使用 asyncio.run 在同步环境中运行异步函数
            route_result = asyncio.run(self.router.route(screenshot))
            mode = route_result["mode"]
            content = route_result["content"]
            reason = route_result["reason"]
            
            print(f"🔀 [Vision] 路由决策: {mode} ({reason})")
            
        except Exception as e:
            print(f"❌ [Vision] 路由决策失败: {e}")
            traceback.print_exc()
            # 回退到视觉流
            mode = "VISION"
            content = screenshot
        
        # Step 3: 根据路由结果调用不同的模型
        if mode == "TEXT":
            # 文本流：使用 DeepSeek 文本吐槽
            response = self._analyze_text(content)
            return response, "DeepSeek"
        else:
            # 视觉流：使用 Gemini 视觉分析（传入已选择的 prompt）
            response = self._analyze_vision(screenshot, history, long_term_memory, selected_prompt)
            return response, "Gemini"
    
    def _analyze_abstract(self, prompt: str, long_term_memory: str = "") -> str:
        """
        抽象流：不基于视觉内容，纯粹让 AI 整活
        
        Args:
            prompt: 抽象模式的 system prompt
            long_term_memory: 长期记忆（虽然抽象模式不需要，但保留参数以保持接口一致）
        
        Returns:
            str: 抽象整活内容（包含 ###JSON### 格式）
        """
        try:
            print(f"🎪 [Vision] 执行抽象流 (纯粹整活)...")
            
            # 构建消息（注意：不需要记忆，不需要历史，不需要图片）
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "开始你的表演吧！"}
            ]
            
            # 调用 API
            response = self.client.chat.completions.create(
                model=VISION_MODEL_NAME,
                messages=messages,
                temperature=1.2,  # 高温度，让输出更随机
                top_p=0.95,
                max_tokens=1000   # ★ 增加到 1000，确保完整的 JSON 和多句话能完整返回
            )
            
            raw_content = response.choices[0].message.content.strip()
            finish_reason = response.choices[0].finish_reason
            
            # ★ 检查是否被截断
            if finish_reason == "length":
                print(f"⚠️ [Vision] 抽象内容被截断！finish_reason=length")
                print(f"   截断内容长度: {len(raw_content)} 字符")
                print(f"   截断内容: {raw_content}")
                # 如果被截断，尝试补全JSON
                if raw_content.startswith("###JSON###") and not raw_content.rstrip().endswith("}"):
                    print(f"⚠️ [Vision] JSON 被截断，尝试补全...")
                    lines = raw_content.split("\n", 1)
                    json_part = lines[0].replace("###JSON###", "").strip()
                    # 补全JSON
                    json_part = json_part.rstrip('"').rstrip(',')
                    if json_part.count('"') % 2 == 1:
                        json_part += '"'
                    if '"motion"' not in json_part:
                        json_part += ',"motion":"perform"'
                    if '"should_trigger"' not in json_part:
                        json_part += ',"should_trigger":true'
                    if not json_part.endswith("}"):
                        json_part += "}"
                    raw_content = f"###JSON###{json_part}\n" + (lines[1] if len(lines) > 1 else "")
            
            # 清洗可能的 markdown 代码块
            if raw_content.startswith("```"):
                raw_content = raw_content.replace("```json", "").replace("```", "").strip()
            
            print(f"🎪 [Vision] 抽象整活: {raw_content}")
            
            return raw_content
            
        except Exception as e:
            print(f"❌ [Vision] 抽象整活失败: {e}")
            traceback.print_exc()
            # 返回一个默认的整活
            return '###JSON###{"expression": "happy", "motion": "perform", "should_trigger": true}\n突然想吟诗一首：代码千行终有 bug，调试万次总见光～'
    
    def _analyze_text(self, ocr_text: str) -> str:
        """
        文本流：使用 DeepSeek 文本吐槽
        
        Args:
            ocr_text: OCR 识别的文本
        
        Returns:
            str: 吐槽文本（包含 ###JSON### 格式）
        """
        if not self.agent:
            print("⚠️ [Vision] Agent 未设置，无法执行文本吐槽")
            return None
        
        try:
            print(f"📝 [Vision] 执行文本流 (DeepSeek)...")
            tucao = self.agent.generate_text_tucao(ocr_text)
            return tucao
        except Exception as e:
            print(f"❌ [Vision] 文本吐槽失败: {e}")
            traceback.print_exc()
            return None
    
    def _analyze_vision(self, screenshot, history=None, long_term_memory="", selected_prompt=None):
        """
        视觉流：使用 Gemini 视觉分析（原有逻辑）
        
        Args:
            screenshot: PIL Image 对象
            history: 对话历史
            long_term_memory: 长期记忆
            selected_prompt: 已选择的 prompt（如果为 None，则随机选择）
        
        Returns:
            str: Gemini 的回复文本
        """
        try:
            print(f"👁️ [Vision] 执行视觉流 (Gemini)...")
            
            # 将截图转换为 base64
            b64_image = self.image_to_base64(screenshot)
            
            # 构建消息列表
            messages = []
            
            # 1. System Prompt (注入记忆 + 使用传入的 prompt 或随机选择)
            if selected_prompt is None:
                selected_prompt = random.choice(VISION_SYSTEM_PROMPTS)
            system_prompt = selected_prompt.replace("{long_term_memory}", long_term_memory)
            
            # ★★★ 新增：注入视觉历史记录到 prompt 中 ★★★
            if self.vision_history:
                vision_history_text = "\n\n【最近的视觉吐槽历史】（避免重复）：\n"
                for i, vhist in enumerate(self.vision_history, 1):
                    vision_history_text += f"{i}. {vhist}\n"
                vision_history_text += "\n⚠️ 如果本次场景与以上历史非常相似，请换个角度吐槽，或者直接整活，千万不要重复说一样的话！\n"
                system_prompt += vision_history_text
            
            messages.append({
                "role": "system",
                "content": system_prompt
            })
            
            # 2. 注入对话历史（保持上下文连贯）
            if history:
                # 只取最近 5 轮，避免 token 过多
                recent_history = list(history)[-10:]
                for role, content in recent_history:
                    messages.append({"role": role, "content": content})
            
            # 3. 当前的视觉输入
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": "这是当前的屏幕画面，请做出反应。"},
                    {"type": "image_url", 
                     "image_url": {"url": f"data:image/png;base64,{b64_image}"}}
                ]
            })
            
            # 调用 API
            response = self.client.chat.completions.create(
                model=VISION_MODEL_NAME,
                messages=messages,
                temperature=1.1,  # 提高温度，强迫模型创新
                top_p=0.95,       # 配合 top_p
            )
            
            raw_content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            
            # 检查是否因为长度限制被截断
            if finish_reason == "length":
                print(f"⚠️ [Vision] 响应被截断 (finish_reason=length)，尝试增加 max_tokens")
            
            raw_content = raw_content.strip()
            
            # 简单清洗，防止模型多输出 markdown 代码块
            if raw_content.startswith("```"):
                raw_content = raw_content.replace("```json", "").replace("```", "").strip()
            
            print(f"👁️ [Vision] Gemini 回复长度: {len(raw_content)} 字符")
            print(f"👁️ [Vision] Finish reason: {finish_reason}")
            print(f"👁️ [Vision] 原始回复: {raw_content[:100]}...")
            
            # --- 🛠️ 修复开始：增加文本内容查重 ---
            # 检查本次生成的文本是否与最近的历史记录高度重复
            is_text_repeated = False
            for v_hist in self.vision_history:
                # v_hist 格式是 "[Desc...] Content..."，我们需要提取 Content 部分
                # 或者简单粗暴地检查包含关系
                # 如果生成的回复在历史记录里出现过（去掉标点后比较更准，这里简化处理）
                if raw_content.strip() in v_hist or v_hist.endswith(raw_content.strip()):
                    is_text_repeated = True
                    break

            if is_text_repeated:
                print(f"⚠️ [Vision] 检测到文本内容与历史完全重复，强制重试或忽略！")
                # 策略 A: 直接设为不触发
                return '###JSON###{"expression": "sleepy", "motion": "idle", "should_trigger": false, "description": "Duplicate content detected"}'
                # 策略 B (更高级):在此处添加递归调用，强制要求 LLM 重写 (慎用，防死循环)
            # --- 🛠️ 修复结束 ---

            # ★★★ 新增：提取场景描述并去重检查 ★★★
            try:
                if "###JSON###" in raw_content:
                    json_line = raw_content.split("\n")[0]
                    json_str = json_line.replace("###JSON###", "").strip()
                    meta_data = json.loads(json_str)
                    
                    # 提取场景描述
                    current_description = meta_data.get("description", "")
                    
                    # 场景去重：如果与上次描述非常相似，不触发
                    if current_description and self.last_scene_description:
                        # 计算相似度（简单字符串包含检查）
                        similarity = self._calculate_similarity(current_description, self.last_scene_description)
                        print(f"🔍 [Vision] 场景相似度: {similarity:.2f}")
                        
                        if similarity > 0.7:  # 相似度阈值
                            print(f"⚠️ [Vision] 场景与上次过于相似，抑制重复吐槽")
                            # 强制设置 should_trigger = false
                            meta_data["should_trigger"] = False
                            # 重构 raw_content
                            json_line = f"###JSON###{json.dumps(meta_data, ensure_ascii=False)}"
                            content_lines = raw_content.split("\n", 1)
                            raw_content = json_line if len(content_lines) == 1 else json_line + "\n" + content_lines[1]
                    
                    # 如果触发了，更新历史
                    if meta_data.get("should_trigger", True):
                        # 提取正文（用于历史记录）
                        content_lines = raw_content.split("\n", 1)
                        actual_content = content_lines[1].strip() if len(content_lines) > 1 else ""
                        if actual_content:
                            self.vision_history.append(f"[{current_description[:30]}...] {actual_content[:50]}...")
                        self.last_scene_description = current_description
                        print(f"✅ [Vision] 场景已记录: {current_description[:50]}...")
            except Exception as e:
                print(f"⚠️ [Vision] 场景去重检查失败: {e}")
            
            return raw_content
            
        except Exception as e:
            print(f"❌ [Vision] 生成出错: {e}")
            traceback.print_exc()
            return None
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的相似度（简单实现）
        
        Args:
            text1: 第一个文本
            text2: 第二个文本
        
        Returns:
            float: 相似度分数 (0-1)
        """
        if not text1 or not text2:
            return 0.0
        
        # 转小写并分词
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        # Jaccard 相似度
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        if union == 0:
            return 0.0
        
        return intersection / union


class VisionThread(QThread):
    """视觉线程 - 定期截图并分析"""
    
    # ★ 修改信号：直接发送 LLM 完整回复文本
    vision_reaction = Signal(str)
    
    def __init__(self, agent_ref):
        """
        Args:
            agent_ref: DeepSeekAgent 实例的引用（用于获取历史记录和记忆，以及文本吐槽）
        """
        super().__init__()
        # ★ 将 agent 引用传给 sensor
        self.sensor = VisionSensor(agent_ref=agent_ref)
        self.agent = agent_ref
        self.is_running = True
        self.check_interval = self._generate_random_interval()  # 每次动态生成
        
        # ★ 新增：追踪最后一次聊天时间
        self.last_chat_time = time.time()  # 初始化为现在
        self.last_scan_time = 0
    
    def _generate_random_interval(self):
        """每次都生成新的随机间隔（秒）"""
        return random.randint(VISION_CHECK_INTERVAL_MIN, VISION_CHECK_INTERVAL_MAX)
    
    def on_chat_detected(self):
        """
        当检测到聊天活动时调用此方法
        重新设置计时器，确保视觉检查在聊天结束后才进行
        """
        self.last_chat_time = time.time()
        # 生成新的随机间隔
        self.check_interval = self._generate_random_interval()
        print(f"🗨️ [Vision] 检测到聊天，重置视觉检查计时器 - 新间隔: {self.check_interval}秒")
    
    def run(self):
        """主循环 - 在聊天结束后检测屏幕内容"""
        if not self.sensor.client:
            print("⚠️ [Vision] API 客户端未加载，线程退出")
            return
        
        print(f"👁️ 视觉神经已启动... (聊天结束后 {self.check_interval}秒触发)")
        
        while self.is_running:
            # 1. 检查是否距离上次聊天已经超过 VISION_CHECK_INTERVAL
            current_time = time.time()
            last_activity_time = max(self.last_chat_time, self.last_scan_time)
            time_since_activity = current_time - last_activity_time
            time_since_chat = current_time - self.last_chat_time
            
            if time_since_activity < self.check_interval:
                # 还没到触发时间，睡眠 1 秒后重新检查
                time.sleep(1)
                continue
            
            # 2. 执行分析（传入历史记录和长期记忆）
            print(f"\n👁️ 正在扫描屏幕 - 距离上次聊天 {time_since_chat:.0f}秒...")
            # 在此次扫描后重新生成下一次的随机间隔
            self.check_interval = self._generate_random_interval()
            print(f"⏲️ 下一次扫描间隔: {self.check_interval}秒") # 调试输出
            
            # 从 agent 获取只读的历史副本和长期记忆
            current_history = list(self.agent.history) if self.agent else []
            long_term_memory = self.agent.get_formatted_memory() if self.agent else ""
            
            raw_response, model_used = self.sensor.analyze(
                history=current_history,
                long_term_memory=long_term_memory
            )
            
            # ★ 关键：在分析完成后立即更新 last_scan_time，防止重复触发
            self.last_scan_time = time.time()
            
            if raw_response:
                # 预判 should_trigger 以避免无效触发
                if '"should_trigger": false' in raw_response or '"should_trigger":false' in raw_response:
                    print(f"👁️ 视觉忽略 ({model_used}) (should_trigger=False)")
                else:
                    print(f"👁️ 视觉触发回复 ({model_used}): {raw_response[:80]}...")
                    self.vision_reaction.emit(raw_response)
                    # ★ 发送信号后再次更新时间，确保不会立即重复
                    self.last_scan_time = time.time()
            else:
                print("👁️ 视觉分析无返回")
            import random
            # 重新随机一个 120 到 240 秒之间的值
            self.check_interval = random.randint(120, 240)
            print(f"🎲 [Vision] 下次检查将在 {self.check_interval} 秒后")

            # 原有代码：更新时间戳
            self.last_scan_time = time.time()
    
    def stop(self):
        """停止线程"""
        print("👁️ 正在停止视觉线程...")
        self.is_running = False
        self.wait()
    
    def set_interval(self, seconds: int):
        """动态调整检查间隔"""
        self.check_interval = max(60, seconds)  # 最小 1 分钟
        print(f"👁️ 视觉检查间隔已调整为 {self.check_interval} 秒")
