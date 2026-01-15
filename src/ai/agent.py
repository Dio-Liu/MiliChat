"""AI Agent - 处理与 LLM 的交互"""
import re
import json
import threading
from collections import deque
from dataclasses import dataclass, asdict
from typing import Dict, Any, List

from src.core.config import (
    get_llm_config, SYSTEM_PROMPT_TEMPLATE, DB_PATH, MODEL_NAME,
    DEEPSEEK_TEXT_MODEL,
    DEEPSEEK_TEXT_MAX_LENGTH,
    DEEPSEEK_TEXT_SMART_SAMPLE,
    DEEPSEEK_SAMPLE_HEAD_LINES,
    DEEPSEEK_SAMPLE_TAIL_LINES,
    DEEPSEEK_SAMPLE_MIDDLE_LINES,
    DEEPSEEK_TEXT_TUCAO_SYSTEM_PROMPT,
    DEEPSEEK_TEXT_TEMPERATURE,
    DEEPSEEK_TEXT_MAX_TOKENS,
    DEEPSEEK_DEDUP_THRESHOLD,
    DEEPSEEK_DEDUP_PATTERNS,
    REFLECTION_THRESHOLD,
    REFLECTION_TEMPERATURE,
    REFLECTION_MAX_TOKENS,
    REFLECTION_SYSTEM_PROMPT
)

# 导入 LLM 驱动
from src.ai.llm_drivers import get_llm_driver

try:
    from memory_store import MemoryStore
except ImportError:
    print("❌ 错误: 未找到 memory_store.py，记忆功能将无法使用。")
    MemoryStore = None

# 导入工具管理器和工具
from src.ai.tools_manager import tool_manager
# 确保工具被加载 - 这会执行装饰器注册
import src.ai.tools.basic_tools
# ★★★ 系统控制工具：音量、亮度、应用启动 ★★★
import src.ai.tools.os_control


@dataclass
class AgentReply:
    """Agent 回复数据结构"""
    reply: str
    emotion: str = "smile"
    motion: str = "idle"
    voice: Dict[str, Any] = None
    memory_write: list = None
    tool_calls: list = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d["voice"] is None:
            d["voice"] = {"rate": 1.0, "pitch": 0.0, "volume": 1.0}
        if d["memory_write"] is None:
            d["memory_write"] = []
        if d["tool_calls"] is None:
            d["tool_calls"] = []
        return d


class DeepSeekAgent:
    """AI Agent - 负责对话生成和记忆管理"""
    
    def __init__(self, api_key: str = None, db_path: str = None):
        """
        初始化 Agent
        
        Args:
            api_key: API Key (可选，默认从配置读取)
            db_path: 数据库路径 (默认使用 config 中的配置)
        """
        # 获取 LLM 配置
        llm_config = get_llm_config()
        if api_key:
            llm_config["api_key"] = api_key
        
        # 使用 LLM 驱动工厂创建客户端
        try:
            self.llm = get_llm_driver(llm_config)
            # 为了兼容现有代码，提供 client 属性
            if hasattr(self.llm, 'raw_client'):
                self.client = self.llm.raw_client
            else:
                # 如果不是 OpenAI 兼容驱动，使用包装器
                self.client = None
                print("⚠️  [Agent] 警告: 当前 LLM 驱动不支持原始客户端访问，部分功能可能受限")
            print(f"✅ [Agent] LLM 驱动已初始化")
        except Exception as e:
            print(f"❌ [Agent] LLM 驱动初始化失败: {e}")
            raise
        
        # 初始化记忆库
        if MemoryStore:
            self.mem = MemoryStore(db_path=db_path or DB_PATH)
        else:
            self.mem = None
        
        self.history = deque(maxlen=20)
        self.system_prompt_template = SYSTEM_PROMPT_TEMPLATE
        
        # === 新增：记忆缓冲区 - 周期性反思机制 ===
        self.dialogue_buffer: List[Dict[str, str]] = []  # 暂存对话
        self.reflection_threshold = REFLECTION_THRESHOLD  # 从 config 读取
        self.reflection_thread = None  # 追踪反思线程，用于 close() 时等待
        print(f"🧠 [Agent] 记忆反思机制已启用 (阈值: {self.reflection_threshold} 轮对话)")

    
    def generate_text_tucao(self, ocr_text: str) -> str:
        """
        基于 OCR 文本生成吐槽（不发送图片）
        
        这个方法用于"文字密集场景"，通过纯文本理解用户在做什么，
        然后以 Mili 的角色进行简短吐槽。
        
        Args:
            ocr_text: OCR 识别出的屏幕文字内容
        
        Returns:
            str: Mili 的吐槽文本（包含 ###JSON### 格式）
        """
        # 采样文本，避免 token 爆炸
        if DEEPSEEK_TEXT_SMART_SAMPLE:
            truncated_text = self._smart_sample_text(ocr_text, DEEPSEEK_TEXT_MAX_LENGTH)
            sample_method = "智能采样"
        else:
            truncated_text = ocr_text[:DEEPSEEK_TEXT_MAX_LENGTH]
            sample_method = "简单截断"
            if len(ocr_text) > DEEPSEEK_TEXT_MAX_LENGTH:
                truncated_text += "\n...(内容过长，已截断)"
        
        # ★ 输出完整的输入内容供调试
        print(f"\n{'='*60}")
        print(f"📤 [Agent] 发送给 DeepSeek 的完整内容 ({sample_method}):")
        print(f"{'='*60}")
        print(f"原始文本: {len(ocr_text)} 字 → 采样后: {len(truncated_text)} 字")
        print(f"{'='*60}")
        print(f"屏幕文字内容：\n{truncated_text}")
        print(f"{'='*60}\n")
        
        try:
            # 调用 LLM 生成吐槽
            tucao = self.llm.chat(
                messages=[
                    {"role": "system", "content": DEEPSEEK_TEXT_TUCAO_SYSTEM_PROMPT},
                    {"role": "user", "content": f"屏幕文字内容：\n{truncated_text}"}
                ],
                temperature=DEEPSEEK_TEXT_TEMPERATURE,
                max_tokens=DEEPSEEK_TEXT_MAX_TOKENS
            )
            
            print(f"💬 [Agent] LLM 文本吐槽: {tucao[:100]}...")
            return tucao
            
        except Exception as e:
            print(f"❌ [Agent] DeepSeek 文本吐槽失败: {e}")
            # 返回一个默认吐槽
            return '###JSON###{"expression": "sleepy", "motion": "Idle", "should_trigger": true}\n看不懂你在干嘛...'
    
    def get_formatted_memory(self) -> str:
        """获取格式化的长期记忆（用于视觉模式）"""
        if not self.mem:
            return "（暂无记忆）"
        
        # 使用 search 获取最近的记忆
        try:
            # 用空查询获取一些记忆，或者用固定关键词
            all_memories = self.mem.search("用户", top_k=8)
            if not all_memories:
                return "（暂无记忆）"
            
            return "\n".join([f"- {m['text']}" for m in all_memories])
        except:
            return "（暂无记忆）"
    
    def _smart_sample_text(self, text: str, max_length: int) -> str:
        """
        智能采样 OCR 文本 - 语义块识别策略
        
        策略（经过测试验证的最优方案）：
        1. 识别语义块：错误堆栈、代码块、命令行、普通文本
        2. 优先级排序：错误信息(10) > 代码(8) > 命令(7) > 普通文本(1)
        3. 完整保留：错误堆栈和代码块尽量保持完整
        4. 贪心选择：在预算内优先选择高优先级块
        5. 添加标记：帮助 AI 理解内容结构
        
        测试结果：
        - 关键词保留率: 84.6%
        - 可读性: 76.7分
        - 综合得分: 83.9分（最高）
        
        Args:
            text: 原始 OCR 文本
            max_length: 最大字符数
            
        Returns:
            采样后的文本
        """
        if len(text) <= max_length:
            return text
        
        lines = text.split('\n')
        
        # Step 1: 去重预处理
        deduplicated_lines = self._deduplicate_lines(lines)
        
        # Step 2: 识别语义块
        blocks = []
        i = 0
        
        while i < len(deduplicated_lines):
            line = deduplicated_lines[i]
            line_lower = line.lower()
            
            # 错误堆栈块（Traceback 或连续的 File/Error 行）
            if 'traceback' in line_lower or ('error' in line_lower and ':' in line):
                block_lines = [line]
                j = i + 1
                # 收集完整的错误堆栈
                while j < len(deduplicated_lines):
                    next_line = deduplicated_lines[j]
                    # 缩进行、File行、或以空格开头的行都可能是堆栈的一部分
                    if (next_line.startswith(' ') or next_line.startswith('\t') or
                        'file ' in next_line.lower() or 'line ' in next_line.lower()):
                        block_lines.append(next_line)
                        j += 1
                    else:
                        break
                
                blocks.append({
                    'start': i,
                    'lines': block_lines,
                    'priority': 10,
                    'type': 'error'
                })
                i = j
                continue
            
            # 代码块（def/class/import 开头或持续缩进）
            if any(keyword in line for keyword in ['def ', 'class ', 'import ', 'from ']):
                block_lines = [line]
                j = i + 1
                # 收集代码块（连续缩进或相关代码行）
                while j < len(deduplicated_lines):
                    next_line = deduplicated_lines[j]
                    if next_line.startswith(' ') or next_line.startswith('\t'):
                        block_lines.append(next_line)
                        j += 1
                    else:
                        break
                
                blocks.append({
                    'start': i,
                    'lines': block_lines,
                    'priority': 8,
                    'type': 'code'
                })
                i = j
                continue
            
            # 命令行
            if any(line.strip().startswith(p) for p in ['PS>', '$', '>>>', 'python ', 'pip ', '.\\']):
                blocks.append({
                    'start': i,
                    'lines': [line],
                    'priority': 7,
                    'type': 'command'
                })
                i += 1
                continue
            
            # 文件路径行
            if '.py' in line or '.js' in line or ':\\' in line:
                blocks.append({
                    'start': i,
                    'lines': [line],
                    'priority': 6,
                    'type': 'file'
                })
                i += 1
                continue
            
            # 普通文本
            if line.strip():  # 跳过空行
                blocks.append({
                    'start': i,
                    'lines': [line],
                    'priority': 1,
                    'type': 'text'
                })
            
            i += 1
        
        # Step 3: 按优先级排序
        blocks.sort(key=lambda b: b['priority'], reverse=True)
        
        # Step 4: 贪心选择块（在预算内尽量多保留）
        selected_blocks = []
        current_length = 0
        
        for block in blocks:
            block_text = '\n'.join(block['lines'])
            block_len = len(block_text) + 1  # +1 for newline
            
            # 为块标记预留空间
            marker_len = 0
            if block['type'] in ['error', 'code']:
                marker_len = 20  # "[错误堆栈]\n" 或 "[代码片段]\n"
            
            if current_length + block_len + marker_len <= max_length:
                selected_blocks.append(block)
                current_length += block_len + marker_len
        
        # Step 5: 按原始顺序重排
        selected_blocks.sort(key=lambda b: b['start'])
        
        # Step 6: 生成最终文本（带标记）
        result_parts = []
        for block in selected_blocks:
            if block['type'] == 'error':
                result_parts.append('[错误堆栈]')
            elif block['type'] == 'code':
                result_parts.append('[代码片段]')
            
            result_parts.append('\n'.join(block['lines']))
        
        final_text = '\n'.join(result_parts)
        
        # 最终长度检查
        if len(final_text) > max_length:
            final_text = final_text[:max_length]
            # 在合适的位置截断（避免截断到单词中间）
            last_newline = final_text.rfind('\n')
            if last_newline > max_length * 0.9:
                final_text = final_text[:last_newline]
        
        return final_text
    
    def _deduplicate_lines(self, lines):
        """
        去掉连续重复的行
        
        例如：
        [INFO] message1
        [INFO] message2
        [INFO] message3
        ... (50 more [INFO] messages)
        
        会被合并为：
        [INFO] message1
        [INFO] message2
        [INFO] message3
        ... (50 duplicate lines omitted)
        
        Args:
            lines: 原始行列表
            
        Returns:
            去重后的行列表
        """
        if not lines:
            return lines
        
        deduped = []
        line_counts = {}  # 记录重复的行及其出现次数
        
        for line in lines:
            if not line.strip():
                # 保留空行
                deduped.append(line)
                continue
            
            # 提取行的"主体"用于检测重复
            # 例如 "[INFO] Loading..." 的主体是 "[INFO]"
            main_pattern = self._extract_line_pattern(line)
            
            if deduped and deduped[-1].strip():
                last_pattern = self._extract_line_pattern(deduped[-1])
                
                # 如果与上一行的模式相同（即使内容不同），记录重复
                if main_pattern == last_pattern and main_pattern:
                    # 这是一个重复的日志行
                    if last_pattern not in line_counts:
                        line_counts[last_pattern] = 1
                    line_counts[last_pattern] += 1
                    
                    # 如果重复超过阈值，就用省略号替代后续的重复行
                    if line_counts[last_pattern] == DEEPSEEK_DEDUP_THRESHOLD:
                        # 在达到阈值时添加省略号
                        deduped.append(f"... ({main_pattern} messages repeated)")
                    
                    # 跳过重复的行
                    continue
                else:
                    # 不是重复，重置计数
                    line_counts.clear()
            
            deduped.append(line)
        
        return deduped
    
    def _extract_line_pattern(self, line: str) -> str:
        """
        从行中提取"模式"用于检测重复
        
        使用 DEEPSEEK_DEDUP_PATTERNS 中的正则表达式来匹配已知的重复模式
        
        例如：
        "[INFO] Loading config" → "[INFO]"
        "[ERROR] Something failed" → "[ERROR]"
        "[DEBUG] Debug message" → "[DEBUG]"
        
        Args:
            line: 原始行文本
            
        Returns:
            提取的模式（如果无法提取则返回空字符串）
        """
        line = line.strip()
        if not line:
            return ""
        
        # 尝试匹配预定义的模式
        for pattern in DEEPSEEK_DEDUP_PATTERNS:
            match = re.search(pattern, line)
            if match:
                return match.group(0)
        
        # 如果没有匹配预定义的模式，回退到通用规则
        # 提取方括号内的内容，如 [INFO] [ERROR] 等
        if '[' in line and ']' in line:
            start = line.find('[')
            end = line.find(']', start)
            if start != -1 and end != -1:
                return line[start:end+1]
        
        # 提取行首的大写单词（如 ERROR WARNING DEBUG）
        words = line.split()
        if words and len(words[0]) > 2 and words[0].isupper():
            return words[0]
        
        return ""

    def handle_vision_response_stream(self, raw_content: str):
        """
        处理来自视觉模块（Gemini）的直接回复流
        
        这与 chat_stream 类似，但它不需要调用 LLM，而是直接解析现成的 LLM 输出
        并将其加入历史记录，推送到前端
        
        Args:
            raw_content: Gemini 返回的完整文本 (包含 ###JSON### 和正文)
            
        Yields:
            dict: 包含 type 和 data/content 的字典
        """
        print(f"⚡ [Agent] 处理视觉回复流...")
        print(f"   原始内容长度: {len(raw_content)} 字符")
        print(f"   原始内容预览: {raw_content[:450]}...")
        
        full_clean_content = ""
        
        # 处理 JSON 元数据
        if raw_content.strip().startswith("###JSON###"):
            lines = raw_content.split("\n", 1)
            header = lines[0].strip()
            actual_content = lines[1] if len(lines) > 1 else ""
            
            if header.startswith("###JSON###"):
                try:
                    import json
                    json_str = header.replace("###JSON###", "").strip()
                    
                    print(f"   提取的 JSON 字符串: {json_str}")
                    
                    # 检查 JSON 是否完整
                    if not json_str.endswith("}"):
                        print(f"⚠️ [Agent] JSON 不完整，尝试修复...")
                        # 如果响应被截断，尝试简单补全
                        # 检查是否有未闭合的引号
                        quote_count = json_str.count('"') - json_str.count('\\"')
                        if quote_count % 2 == 1:
                            # 有未闭合的引号，添加闭合引号和右括号
                            json_str += '", "motion": "Idle", "should_trigger": true}'
                        else:
                            # 没有未闭合引号，直接补全
                            json_str += ', "motion": "Idle", "should_trigger": true}'
                        print(f"   修复后: {json_str}")
                    
                    meta_data = json.loads(json_str)
                    
                    # 检查 trigger 标记
                    if meta_data.get("should_trigger") is False:
                        print("👁️ [Agent] should_trigger=False，停止输出")
                        return
                    
                    print(f"✅ [Agent] JSON 解析成功: {meta_data}")
                    yield {"type": "meta", "data": meta_data}
                    
                except json.JSONDecodeError as e:
                    print(f"❌ [Agent] 视觉 JSON 解析失败: {e}")
                    print(f"   失败的 JSON: {json_str}")
                    # JSON 解析失败，使用默认值
                    default_meta = {"expression": "smile", "motion": "Idle", "should_trigger": True}
                    print(f"   使用默认元数据: {default_meta}")
                    yield {"type": "meta", "data": default_meta}
                except Exception as e:
                    print(f"❌ [Agent] 其他错误: {e}")
                    import traceback
                    traceback.print_exc()
            
            # 输出正文
            full_clean_content = actual_content.strip()
            for char in actual_content:
                yield {"type": "text", "content": char}
        else:
            # 没有 JSON，全量输出
            full_clean_content = raw_content.strip()
            for char in raw_content:
                yield {"type": "text", "content": char}
        
        # ★★★ 关键：将 Gemini 的回复存入 DeepSeek 的历史记录 ★★★
        # 这样下次文字对话时，DeepSeek 知道刚才 Gemini 说了什么
        if full_clean_content:
            # 1. 存入短期上下文 (原代码)
            self.history.append(("user", "[系统事件: 屏幕截图已分析]"))
            self.history.append(("assistant", full_clean_content))
            
            # 2. ★新增：存入反思缓冲区 (让反思机制感知到这次视觉事件)
            # 我们构造一个伪造的 User 输入，说明这是视觉模块看到的
            vision_context = "[系统事件] 视觉模块检测到用户屏幕内容，并触发了主动回复。"
            self._add_to_buffer(vision_context, full_clean_content)
            
            print(f"✅ [Agent] 视觉交互已存入上下文及反思缓冲区")
        else:
            print(f"⚠️ [Agent] 没有提取到正文内容")

    def chat_stream(self, user_text: str):
        """
        流式对话生成器（支持工具调用）
        
        Args:
            user_text: 用户输入的文本
            
        Yields:
            dict: 包含 type 和 data/content/status 的字典
                  type="status": 状态信息 (thinking/speaking)
                  type="meta": 元数据 (表情、动作、记忆)
                  type="text": 文本内容
        """
        # 1. RAG 检索
        mem_str = "（暂无相关记忆）"
        if self.mem:
            print(f"🔍 正在记忆库中检索: {user_text}")
            retrieved = self.mem.search(user_text, top_k=8)
            if retrieved:
                mem_str = "\n".join([f"- {r['text']}" for r in retrieved])
                print(f"📚 检索到 {len(retrieved)} 条相关记忆:")
                for i, r in enumerate(retrieved, 1):
                    print(f"   [{i}] (分数:{r.get('score', 'N/A'):.2f}) {r['text'][:50]}...")
        
        # 2. 填入 Prompt
        system_prompt = self.system_prompt_template.replace("{long_term_memory}", mem_str)
                
        messages = [{"role": "system", "content": system_prompt}]
        for role, text in self.history:
            messages.append({"role": role, "content": text})
        messages.append({"role": "user", "content": user_text})

        # ---------------------------------------------------------
        # 第一轮：侦察模式 (Stream=False)
        # 目的：快速判断 LLM 是否想用工具，而不立刻向前端输出
        # ---------------------------------------------------------
        try:
            print("\n" + "=" * 70)
            print("🤔 Agent 正在思考 (第一轮侦察)...")
            print("=" * 70)
            first_response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=tool_manager.get_tool_schemas(),  # 注入工具定义
                stream=False  # 关键：不流式，一次性拿到结果好判断
            )
            
            msg = first_response.choices[0].message
            
            # 打印第一轮 LLM 的完整输出
            print(f"\n📝 第一轮 LLM 输出:")
            print(f"   内容: {msg.content if msg.content else '(无文本内容)'}")
            if msg.tool_calls:
                print(f"   工具调用数: {len(msg.tool_calls)}")
                for i, tool_call in enumerate(msg.tool_calls, 1):
                    print(f"   [工具 {i}] {tool_call.function.name}")
                    print(f"      参数: {tool_call.function.arguments}")
            
            # =================================================
            # 分支 A: LLM 想要调用工具 (Hit Tool)
            # =================================================
            if msg.tool_calls:
                print(f"\n🔧 检测到工具调用: {len(msg.tool_calls)} 个")
                
                # 通知前端：正在思考/查询资料
                yield {"type": "status", "status": "thinking"}
                
                # 1. 这一步是【隐形】的，我们把 LLM 的意图存入上下文，但不 yield 给前端
                messages.append(msg)
                
                # 2. 执行所有工具
                print("\n" + "-" * 70)
                print("🔨 执行工具...")
                print("-" * 70)
                for tool_call in msg.tool_calls:
                    func_name = tool_call.function.name
                    args = tool_call.function.arguments
                    
                    # 执行 Python 函数
                    tool_result = tool_manager.execute_tool(func_name, args)
                    
                    print(f"\n✅ 工具执行结果:")
                    print(f"   工具: {func_name}")
                    print(f"   参数: {args}")
                    print(f"   结果: {tool_result}")
                    
                    # 3. 将工具结果作为 'tool' 角色存入消息列表
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": func_name,
                        "content": tool_result
                    })
                
                # 4. 第二轮：生成最终回复 (可能还要调工具)
                # 这才是真正给用户看的内容
                print("\n" + "=" * 70)
                print("✅ 工具执行完毕，请求最终回复...")
                print("=" * 70)
                yield {"type": "status", "status": "speaking"}
                
                # ★ 第二轮也允许工具调用（有些情况下需要多步骤）
                second_response = self.client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    tools=tool_manager.get_tool_schemas(),  # 第二轮也允许工具调用
                    stream=False  # 先不流式，检查是否还要调工具
                )
                
                second_msg = second_response.choices[0].message
                
                # 检查第二轮是否还要调工具
                if second_msg.tool_calls:
                    print(f"\n🔧 第二轮还要调用工具: {len(second_msg.tool_calls)} 个")
                    
                    # 将第二轮的 assistant 消息加入
                    messages.append(second_msg)
                    
                    # 执行这些工具
                    for tool_call in second_msg.tool_calls:
                        func_name = tool_call.function.name
                        args = tool_call.function.arguments
                        
                        tool_result = tool_manager.execute_tool(func_name, args)
                        
                        print(f"  - {func_name}: {tool_result}")
                        
                        messages.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": func_name,
                            "content": tool_result
                        })
                    
                    # 第三轮：基于所有工具结果生成最终回复
                    print("\n✅ 所有工具执行完毕，生成最终回复...")
                    final_response = self.client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=messages,
                        stream=True  # 这次才开始流式
                    )
                    
                    stream_response = final_response
                else:
                    # 第二轮不需要工具，直接流式输出
                    print("\n📝 第二轮无需工具，开始流式输出...")
                    
                    # 需要手动流式化 second_msg 的内容
                    # 因为我们已经一次性拿到了完整回复
                    stream_response = None
                
                # ★★★ 只有在这里，才开始向前端 yield 数据 ★★★
                print("\n📝 最终 LLM 输出 (流式):")
                full_content = ""
                raw_full_content = ""  # 原始完整内容
                
                if stream_response:
                    # 有新的流式响应，正常处理
                    for chunk in self._process_stream_response(stream_response):
                        # 收集原始完整内容
                        if chunk.get("raw_char"):
                            raw_full_content += chunk["raw_char"]
                        
                        # 收集清洗后的内容
                        if chunk["type"] == "text":
                            full_content += chunk["content"]
                        yield chunk
                else:
                    # 没有新的响应，直接使用 second_msg 的内容
                    content = second_msg.content or ""
                    raw_full_content = content
                    
                    # 处理 JSON 元数据
                    if content.strip().startswith("###JSON###"):
                        lines = content.split("\n", 1)
                        header = lines[0].strip()
                        actual_content = lines[1] if len(lines) > 1 else ""
                        
                        if header.startswith("###JSON###"):
                            try:
                                import json
                                json_str = header.replace("###JSON###", "")
                                meta_data = json.loads(json_str)
                                yield {"type": "meta", "data": meta_data}
                                
                                # 处理记忆保存
                                saves = meta_data.get("memory_to_save", [])
                                if self.mem and saves:
                                    for item in saves:
                                        self.mem.add_memory(
                                            text=item.get("text"), 
                                            mtype="fact",
                                            key=item.get("key"), 
                                            value=item.get("value")
                                        )
                            except Exception as e:
                                print(f"❌ JSON 解析失败: {e}")
                        
                        # 输出正文
                        for char in actual_content:
                            yield {"type": "text", "content": char}
                        
                        full_content = actual_content
                    else:
                        # 没有 JSON，直接输出
                        for char in content:
                            yield {"type": "text", "content": char}
                        
                        full_content = content
                
                print(f"\n✨ 原始完整回复 (含JSON):")
                print(f"   {raw_full_content[:200]}..." if len(raw_full_content) > 200 else f"   {raw_full_content}")
                print(f"\n✨ 清洗后回复: {full_content}")
                print("=" * 70 + "\n")
                
                # 存历史 (User + Final Assistant)
                self.history.append(("user", user_text))
                self.history.append(("assistant", full_content))
                
                # === 新增：将对话存入缓冲区 ===
                self._add_to_buffer(user_text, full_content)

            # =================================================
            # 分支 B: 普通闲聊 (No Tool)
            # =================================================
            else:
                print("\n💬 普通闲聊模式 (不需要工具)")
                content = msg.content
                
                # 问题：我们手里拿的是完整的一整段话，但前端期待流式输出
                # 解决：手动模拟流式输出
                
                print(f"\n📝 LLM 输出: {content}")
                print("=" * 70 + "\n")
                
                # 先处理可能的 JSON 元数据
                if content and content.strip().startswith("###JSON###"):
                    lines = content.split("\n", 1)
                    header = lines[0].strip()
                    actual_content = lines[1] if len(lines) > 1 else ""
                    
                    if header.startswith("###JSON###"):
                        try:
                            import json
                            json_str = header.replace("###JSON###", "")
                            meta_data = json.loads(json_str)
                            yield {"type": "meta", "data": meta_data}
                            
                            # 处理记忆保存
                            saves = meta_data.get("memory_to_save", [])
                            if self.mem and saves:
                                for item in saves:
                                    self.mem.add_memory(
                                        text=item.get("text"), 
                                        mtype="fact",
                                        key=item.get("key"), 
                                        value=item.get("value")
                                    )
                        except Exception as e:
                            print(f"❌ JSON 解析失败: {e}")
                    
                    # 输出正文
                    for char in actual_content:
                        yield {"type": "text", "content": char}
                else:
                    # 没有 JSON，直接输出全部内容
                    for char in content:
                        yield {"type": "text", "content": char}
                
                # 存历史
                self.history.append(("user", user_text))
                self.history.append(("assistant", content))
                
                # === 新增：将对话存入缓冲区 ===
                self._add_to_buffer(user_text, content)

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            yield {"type": "text", "content": f"系统出错了: {e}"}

    def _process_stream_response(self, response, raw_content_collector=None):
        """
        处理流式响应（抽离出来的逻辑，供工具调用后复用）
        
        Args:
            response: OpenAI stream response
            raw_content_collector: 可选的回调函数，用于收集原始内容
            
        Yields:
            dict: 包含 type、content、raw_char 的字典
                  - type: "meta"、"text"
                  - content: 处理后的内容
                  - raw_char: 原始字符（如果有）
        """
        is_json_parsed = False
        buffer = ""
        first_text_chunk = True  # 用于跟踪JSON解析后的第一个文本块

        for chunk in response:
            if chunk.choices[0].delta.content:
                char = chunk.choices[0].delta.content
                buffer += char

                # 尝试解析第一行的 JSON 元数据
                if not is_json_parsed and "\n" in buffer:
                    parts = buffer.split("\n", 1)
                    header = parts[0].strip()
                    
                    if header.startswith("###JSON###"):
                        try:
                            import json
                            json_str = header.replace("###JSON###", "")
                            meta_data = json.loads(json_str)
                            yield {"type": "meta", "data": meta_data, "raw_char": header + "\n"}
                            
                            # 处理记忆保存
                            saves = meta_data.get("memory_to_save", [])
                            if self.mem and saves:
                                for item in saves:
                                    self.mem.add_memory(
                                        text=item.get("text"), 
                                        mtype="fact",
                                        key=item.get("key"), 
                                        value=item.get("value")
                                    )
                        except Exception as e:
                            print(f"❌ JSON 解析失败: {e}")
                    
                    # 标记 JSON 已解析，并重置 buffer
                    is_json_parsed = True
                    buffer = ""
                    
                    # 处理剩余文本（JSON 后面的文本）
                    remaining_text = parts[1] if len(parts) > 1 else ""
                    if remaining_text:
                        # 过滤掉开头可能多余的 "}" 字符
                        if remaining_text.startswith("}"):
                            remaining_text = remaining_text[1:]
                        
                        # 过滤掉前导空白
                        remaining_text = remaining_text.lstrip()
                        
                        # 输出处理后的文本
                        for text_char in remaining_text:
                            yield {"type": "text", "content": text_char, "raw_char": text_char}
                
                # 如果 JSON 已解析，直接处理新字符
                elif is_json_parsed:
                    # 对于第一个文本块，需要检查是否有多余的 "}"
                    if first_text_chunk:
                        first_text_chunk = False
                        text_to_process = char
                        
                        # 如果是 "}" 且后面是换行符，跳过它
                        if text_to_process.strip() == "}":
                            continue
                        
                        # 去除前导空白
                        text_to_process = text_to_process.lstrip()
                        
                        if text_to_process:
                            yield {"type": "text", "content": text_to_process, "raw_char": char}
                    else:
                        yield {"type": "text", "content": char, "raw_char": char}

    # ============================================================
    # 周期性反思机制 - Memory Reflection System
    # ============================================================
    
    def _add_to_buffer(self, user_text: str, ai_reply: str):
        """
        将对话添加到缓冲区，并检查是否触发反思
        
        Args:
            user_text: 用户输入
            ai_reply: AI 回复
        """
        import datetime
        # 获取当前时间，格式如：Mon 23:30 (星期几 + 时间)
        # 星期几对判断工作日/周末习惯很重要
        time_tag = datetime.datetime.now().strftime("%a %H:%M")
        
        # ★ 关键修改：在内容前隐式加入时间信息，供后台 LLM 分析
        self.dialogue_buffer.append({"role": "user", "content": f"[{time_tag}] {user_text}"})
        self.dialogue_buffer.append({"role": "assistant", "content": ai_reply})
        
        # 检查是否触发反思 (阈值检查)
        # *2 是因为一问一答算2条
        if len(self.dialogue_buffer) >= self.reflection_threshold * 2:
            print(f"🧠 [Reflection] 缓冲区已达阈值 ({len(self.dialogue_buffer)//2} 轮对话)")
            self._trigger_reflection()
    
    def _trigger_reflection(self):
        """
        触发反思机制：将缓冲区的数据快照发送给后台线程处理，
        然后立即清空缓冲区，以免阻塞主对话。
        """
        if not self.dialogue_buffer:
            print("⚠️ [Reflection] 缓冲区为空，跳过反思")
            return
        
        # 复制当前缓冲区的内容进行处理
        buffer_snapshot = list(self.dialogue_buffer)
        self.dialogue_buffer = []  # 立即清空，准备接纳下一轮
        
        print(f"🔄 [Reflection] 启动后台反思线程...")
        # 启动后台线程进行分析 (不卡顿界面)
        self.reflection_thread = threading.Thread(
            target=self._analyze_buffer, 
            args=(buffer_snapshot,), 
            daemon=False  # 非守护线程，close() 会等待其完成
        )
        self.reflection_thread.start()
    
    def _analyze_buffer(self, chat_history: List[Dict]):
        """
        【后台运行】深度分析一段完整的对话历史
        
        Args:
            chat_history: 对话历史列表，格式: [{"role": "user", "content": "..."}, ...]
        """
        print(f"🧠 [Deep Reflection] 正在分析最近的 {len(chat_history)//2} 轮对话...")
        
        # 将对话列表转为可读文本
        history_text = "\n".join([
            f"{msg['role'].upper()}: {msg['content']}" 
            for msg in chat_history
        ])
        
        # 构造反思 Prompt (简化版，详细指令已在 REFLECTION_SYSTEM_PROMPT 中)
        prompt = f"""请分析以下对话历史（注意时间戳），提炼用户的核心画像。

对话历史：
{history_text}

请按照系统指令的格式输出 JSON，包含 facts、psychology、behavior 和 summary 四个字段。
"""
        
        try:
            # 调用 DeepSeek 进行深度分析
            print(f"📡 [Deep Reflection] 调用 DeepSeek 进行反思分析...")
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=REFLECTION_TEMPERATURE,  # 从 config 读取
                max_tokens=REFLECTION_MAX_TOKENS      # 从 config 读取
            )
            
            reflection_result = response.choices[0].message.content.strip()
            
            print(f"📝 [Deep Reflection] LLM 返回结果:")
            print(f"=" * 70)
            print(reflection_result)
            print(f"=" * 70)
            
            # 尝试解析 JSON
            # 有时 LLM 会在 JSON 前后加一些说明文字，我们需要提取纯 JSON 部分
            json_start = reflection_result.find('{')
            json_end = reflection_result.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_str = reflection_result[json_start:json_end]
                data = json.loads(json_str)
                
                # 定义内部辅助函数：语义去重，避免存储重复记忆
                def save_if_unique(text, mtype, importance=0.7, threshold=0.105):
                    """
                    检查记忆是否已存在，只有足够新颖的内容才会保存
                    
                    Args:
                        text: 记忆文本
                        mtype: 记忆类型
                        importance: 重要性权重
                        threshold: 相似度阈值，超过此值视为重复（0.85 = 85%相似）
                    
                    Returns:
                        bool: True 表示已保存，False 表示跳过（重复）
                    """
                    if not self.mem:
                        return False
                    
                    # 先搜索一下有没有极其相似的记忆
                    existing = self.mem.search(text, top_k=1)
                    if existing and existing[0]['score'] > threshold:
                        print(f"   ♻️ 记忆已存在，跳过: {text[:30]}... (相似度: {existing[0]['score']:.2f})")
                        return False
                    
                    # 如果足够新颖，则保存
                    self.mem.add_memory(text=text, mtype=mtype, importance=importance)
                    return True
                
                # 1. 存入结构化事实 (Facts) - 会覆盖旧 Key
                facts = data.get("facts", [])
                if facts:
                    print(f"📌 [Deep Reflection] 提取到 {len(facts)} 个事实:")
                    for fact in facts:
                        fact_text = f"用户的{fact.get('key', 'unknown')}是 {fact.get('value', 'unknown')}"
                        self.mem.add_memory(
                            text=fact_text,
                            mtype="fact",
                            key=fact.get('key', ''),
                            value=fact.get('value', ''),
                            importance=0.9
                        )
                        print(f"   ✓ {fact_text}")
                
                # 2. 存入心理侧写 (Psychology) - 设为 insight (语义去重)
                insights = data.get("psychology", [])
                saved_insights = 0
                if insights:
                    print(f"🧠 [Deep Reflection] 处理 {len(insights)} 条心理洞察:")
                    for insight in insights:
                        full_text = f"用户心理侧写：{insight}"
                        if save_if_unique(full_text, "insight", importance=0.7, threshold=0.85):
                            print(f"   ✓ {insight}")
                            saved_insights += 1
                    if saved_insights > 0:
                        print(f"   💾 已保存 {saved_insights}/{len(insights)} 条新洞察")
                
                # 3. ★新增：Behavior (行为模式) - 语义去重
                behaviors = data.get("behavior", [])
                saved_behaviors = 0
                if behaviors:
                    print(f"📅 [Deep Reflection] 处理 {len(behaviors)} 条行为习惯:")
                    for b in behaviors:
                        full_text = f"用户行为习惯：{b}"
                        # 行为习惯去重阈值稍低(0.80)，允许记录细微差异
                        if save_if_unique(full_text, "behavior", importance=0.8, threshold=0.80):
                            print(f"   ✓ {b}")
                            saved_behaviors += 1
                    if saved_behaviors > 0:
                        print(f"   💾 已保存 {saved_behaviors}/{len(behaviors)} 条新习惯")
                
                # 4. (可选) 存入情景摘要，用于长期回忆 (语义去重)
                summary = data.get("summary", "")
                if summary:
                    full_text = f"对话摘要：{summary}"
                    # 摘要去重阈值较高(0.90)，避免存储相似的对话摘要
                    if save_if_unique(full_text, "episodic_summary", importance=0.3, threshold=0.90):
                        print(f"📖 [Deep Reflection] 情景摘要: {summary}")
                
                total_saved = len(facts) + saved_insights + saved_behaviors
                if total_saved == 0:
                    print("ℹ️ [Deep Reflection] 本次对话无新记忆（闲聊或重复内容）")
                else:
                    print(f"✅ [Deep Reflection] 反思完成，共保存 {total_saved} 条新记忆")
            else:
                print(f"❌ [Deep Reflection] 无法从响应中提取JSON")
                
        except json.JSONDecodeError as e:
            print(f"❌ [Deep Reflection] JSON 解析失败: {e}")
            print(f"   失败的内容: {reflection_result[:200]}")
        except Exception as e:
            print(f"❌ [Deep Reflection] 分析失败: {e}")
            import traceback
            traceback.print_exc()
    
    def close(self):
        """
        程序退出时调用，确保缓冲区里剩余的内容不丢失
        """
        # 如果缓冲区太短（少于4条消息 = 2轮对话），直接丢弃，不值得反思
        MIN_BUFFER_SIZE = 4  # 至少需要2轮完整对话
        
        if self.dialogue_buffer and len(self.dialogue_buffer) >= MIN_BUFFER_SIZE:
            print("💾 [Agent] 程序退出，正在保存剩余的对话记忆...")
            print(f"   缓冲区剩余 {len(self.dialogue_buffer)//2} 轮对话")
            self._trigger_reflection()
            # 等待反思线程完成（最多等待10秒）
            if self.reflection_thread and self.reflection_thread.is_alive():
                print("⏳ [Agent] 等待反思线程完成...")
                self.reflection_thread.join(timeout=10)
                if self.reflection_thread.is_alive():
                    print("⚠️ [Agent] 反思线程超时（10秒），强制退出")
                else:
                    print("✅ [Agent] 反思线程已完成")
        else:
            buffer_count = len(self.dialogue_buffer)
            if buffer_count == 0:
                print("ℹ️ [Agent] 程序退出，缓冲区为空，无需保存")
            else:
                print(f"ℹ️ [Agent] 程序退出，缓冲区内容过少 ({buffer_count} 条消息)，跳过反思")
