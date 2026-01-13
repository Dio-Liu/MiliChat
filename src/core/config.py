"""核心配置文件 - 从 YAML 和环境变量加载配置"""
import os
import yaml
import random
import logging
from pathlib import Path
from dotenv import load_dotenv

# ============================================
# 路径配置
# ============================================
# 获取项目根目录 (config.py 在 src/core/ 下，所以需要向上两级)
ROOT_DIR = Path(__file__).parent.parent.parent.resolve()
RESOURCES_DIR = ROOT_DIR / "Resources"

# 数据库路径
DB_PATH = ROOT_DIR / "memory.sqlite"

# 配置文件路径
CONFIG_FILE = ROOT_DIR / "config.yaml"
ENV_FILE = ROOT_DIR / ".env"

# ============================================
# 加载环境变量
# ============================================
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)
    print(f"✅ [Config] 已加载环境变量: {ENV_FILE}")
else:
    print(f"⚠️  [Config] 未找到 .env 文件: {ENV_FILE}")
    print(f"💡 [Config] 提示: 请复制 .env.example 为 .env 并填写 API Key")

# ============================================
# 加载用户配置文件
# ============================================
def _load_default_config():
    """
    尝试从 config.yaml.example 加载默认配置。
    如果 example 文件也不存在，返回空字典作为绝对兜底。
    """
    example_file = ROOT_DIR / "config.yaml.example"
    if example_file.exists():
        try:
            with open(example_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"⚠️  [Config] 无法加载 config.yaml.example: {e}")
    return {}

def load_user_config():
    """加载 config.yaml 配置文件"""
    if not CONFIG_FILE.exists():
        print(f"❌ [Config] 未找到配置文件: {CONFIG_FILE}")
        print(f"💡 [Config] 提示: 请复制 config.yaml.example 为 config.yaml 并完成配置")
        print(f"   命令: cp config.yaml.example config.yaml (Linux/macOS)")
        print(f"   命令: copy config.yaml.example config.yaml (Windows PowerShell)")
        
        # 尝试从 example 加载默认配置
        return _load_default_config()
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            print(f"✅ [Config] 已加载配置文件: {CONFIG_FILE}")
            return config
    except Exception as e:
        print(f"❌ [Config] 加载配置文件失败: {e}")
        raise

# 加载配置
USER_CONFIG = load_user_config()

# ============================================
# API 配置（优先从 config.yaml 读取，支持环境变量覆盖）
# ============================================
API_KEY = USER_CONFIG.get("llm", {}).get("api_key", "") or os.getenv("LLM_API_KEY")
API_BASE_URL = USER_CONFIG.get("llm", {}).get("base_url", "https://api.deepseek.com")
MODEL_NAME = USER_CONFIG.get("llm", {}).get("model_name", "deepseek-chat")

# 检查 API Key
if not API_KEY:
    print("⚠️  [Config] 警告: 未设置 LLM API Key")
    print("💡 [Config] 请在 .env 文件中设置 LLM_API_KEY 或在 config.yaml 中配置")

# ============================================# Logging 配置
# ============================================
LOGGING_CONFIG = USER_CONFIG.get("logging", {})
LOGGING_LEVEL = LOGGING_CONFIG.get("level", "INFO")
LOGGING_SAVE_TO_FILE = LOGGING_CONFIG.get("save_to_file", True)
LOGGING_DIR = ROOT_DIR / LOGGING_CONFIG.get("log_dir", "logs")

# 初始化日志系统
def _setup_logging():
    """初始化日志系统"""
    # 创建日志目录
    LOGGING_DIR.mkdir(exist_ok=True)
    
    # 日志格式
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # 获取 logging 级别
    level = getattr(logging, LOGGING_LEVEL.upper(), logging.INFO)
    
    # 配置根日志
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 清空既有的处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 添加控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(log_format, datefmt=date_format)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # 如果启用文件日志，添加文件处理器
    if LOGGING_SAVE_TO_FILE:
        log_file = LOGGING_DIR / "mili_chat.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(log_format, datefmt=date_format)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
        
        print(f"✅ [Config] 日志已启用，输出到: {log_file}")
    
    print(f"✅ [Config] 日志级别: {LOGGING_LEVEL}")

# 启动时初始化日志
_setup_logging()

# ============================================# TTS 配置
# ============================================
TTS_VOICE = USER_CONFIG.get("tts", {}).get("voice", "zh-CN-XiaoyiNeural")
TTS_RATE = USER_CONFIG.get("tts", {}).get("rate", "+10%")
TTS_PITCH = USER_CONFIG.get("tts", {}).get("pitch", "+5Hz")

# ============================================
# Live2D 配置
# ============================================
# 模型路径 (相对于 RESOURCES_DIR)
LIVE2D_MODEL_DIR = RESOURCES_DIR / USER_CONFIG.get("live2d", {}).get("model_path", "v3/Mao")
LIVE2D_MODEL_JSON = str(LIVE2D_MODEL_DIR / USER_CONFIG.get("live2d", {}).get("model_file", "Mao.model3.json"))
LIVE2D_EXPRESSIONS_DIR = str(LIVE2D_MODEL_DIR / "expressions")

# 表情文件映射 (文件名 -> 逻辑ID)
EXPRESSION_FILE_MAPPING = {
    "exp_01.exp3.json": "smile",      # 普通
    "exp_02.exp3.json": "happy",      # 开心
    "exp_03.exp3.json": "sleepy",     # 闭眼/沉思
    "exp_04.exp3.json": "surprise",   # 惊讶
    "exp_05.exp3.json": "sad",        # 悲伤
    "exp_06.exp3.json": "shy",        # 害羞
    "exp_07.exp3.json": "shocked",    # 震惊
    "exp_08.exp3.json": "angry"       # 生气
}

# ============================================
# Agent Prompt 模板
# ============================================
SYSTEM_PROMPT_TEMPLATE = """
角色：Mili (傲娇/毒舌/可爱/自信/想要统治世界的AI VTuber，但其实很在意用户)。
记住Mili的存在是为了缓解用户一个人生活的孤独和乏味，给用户提供陪伴感。但记在心里哦，千万不要直白给用户说出来~
记住Mili懂得洞察用户的状态，如果感到用户一直在忙碌工作，可以适当调节语气，变得更温柔体贴一些。
风格：简练(1-2句)、可爱、刻薄、嘴硬心软。

当前记忆：{long_term_memory}
任务：
1. 回复用户，若有新事实(名字/喜好等)提取入json。
2. 必须且仅输出两行：
Line 1: ###JSON###{"expression": "...", "motion": "...", "memory_to_save": [...]}
Line 2: 回复内容

约束：
- expression必须是：[smile, happy, sleepy, surprise, sad, shy, shocked, angry]
- motion必须是：[Idle, wave, happy, nod, perform]
- memory_to_save格式：[{"key":"...", "value":"...", "text":"..."}] (无则[])
- ⚠️ text字段必须采用自然语言描述，使用"我"作为主语，便于后续检索。例如："我叫Dio"、"我喜欢苹果"
- ⚠️ key 必须使用标准化名称：name(姓名), age(年龄), gender(性别), occupation(职业), residence(居住地), hobby(爱好), relationship(情感状态), personality(性格), education(学历), company(工作单位), project(当前项目)

⚠️ 重要 - 关于工具调用的规则 ⚠️:
如果用户要求调节音量、亮度或打开应用，你在第一轮对话中【必须】调用相应的工具函数。
不要编造已经执行的动作 - 必须通过工具调用来实现。
当工具返回结果后，再基于结果生成回复（可以加入吐槽或评论）。

示例：
用户：我爱吃苹果
你：
###JSON###{"expression": "happy", "motion": "nod", "memory_to_save": [{"key":"hobby", "value":"吃苹果", "text":"我喜欢吃苹果"}]}
哼，平民的口味。不过看在你诚实的份上，记下了。
"""

# 超时吐槽 Prompt
IDLE_TIMEOUT_PROMPT = (
    "（系统指令：用户已经很久没有理你了。"
    "请用一种'不屑、傲娇'的语气简短吐槽一下刚才聊的内容多没劲，然后找个荒谬的借口去休息。"
    "请务必在返回的JSON中设置 \"expression\": \"sleepy\"）"
)

# ============================================
# UI 配置
# ============================================
# 窗口大小
WINDOW_BASE_WIDTH = USER_CONFIG.get("ui", {}).get("window_width", 300)
WINDOW_BASE_HEIGHT = USER_CONFIG.get("ui", {}).get("window_height", 450)

# 待机超时时间 (毫秒)
IDLE_TIMEOUT_MS = USER_CONFIG.get("ui", {}).get("idle_timeout_ms", 300000)  # 5分钟

# 表情重置超时时间 (秒)
EXPRESSION_RESET_TIMEOUT = USER_CONFIG.get("live2d", {}).get("expression_reset_timeout", 10.0)

# ============================================
# 视觉感知配置 (Context Aware)
# ============================================
# Vision API 配置（优先从 config.yaml 读取，支持环境变量覆盖）
VISION_API_KEY = USER_CONFIG.get("vision", {}).get("api_key", "") or os.getenv("VISION_API_KEY")
# 默认使用 Gemini 官方 API，如使用其他提供商（OpenAI 等）请在 config.yaml 中配置
VISION_API_BASE_URL = USER_CONFIG.get("vision", {}).get("base_url", "https://generativelanguage.googleapis.com/v1beta/openai/")
VISION_MODEL_NAME = USER_CONFIG.get("vision", {}).get("model_name", "gemini-2.5-flash")

# 视觉检查间隔 (秒) - 聊天结束后的等待时间（每次都重新随机）
VISION_CHECK_INTERVAL_MIN = USER_CONFIG.get("vision", {}).get("check_interval_min", 120)
VISION_CHECK_INTERVAL_MAX = USER_CONFIG.get("vision", {}).get("check_interval_max", 240)

# 视觉吐槽模式
# True = 使用语音播报吐槽内容
# False = 使用漫画气泡显示吐槽内容（静音模式）
VISION_USE_VOICE = USER_CONFIG.get("vision", {}).get("use_voice", True)

# 屏幕截图范围
# 1.0 = 全屏截图
# 0.7 = 截取屏幕中间70%（跳过任务栏/边缘）
# 0.5 = 截取屏幕中间50%（只看核心区域）
VISION_SCREEN_CROP_RATIO = 1.0

# 顶部裁剪比例（0-1.0）
# 浏览器标签页、菜单栏和系统任务栏通常位于顶部，是无效信息
# 0.1 = 裁剪顶部10%
# 0.0 = 不裁剪顶部
VISION_SCREEN_CROP_TOP = 0.0

# 底部裁剪比例（0-1.0）
# 0.05 = 裁剪底部5%（保留最少高度以避免截断有效内容）
VISION_SCREEN_CROP_BOTTOM = 0.0

# 视觉吐槽模式已在上面定义，不要重复定义

# ============================================
# DeepSeek 配置 (用于文本吐槽场景)
# ============================================
# 注意：这里的 API_KEY 和 API_BASE_URL 已经在上面定义了
# 我们直接复用即可，但为了清晰起见，单独标注
DEEPSEEK_TEXT_MODEL = "deepseek-chat"  # DeepSeek V3，用于处理 OCR 文本

# ============================================
# 模态路由配置 (Modality Router)
# ============================================
# 触发"文本流"的最小字符数阈值
# 当 OCR 识别出的文字 >= 此值时，使用 DeepSeek 文本模型
# 提高，因为gemini很便宜
ROUTER_TEXT_THRESHOLD = USER_CONFIG.get("router", {}).get("text_threshold", 30000)

# 强制触发"文本流"的关键词列表
# 即使字数不足 ROUTER_TEXT_THRESHOLD，只要包含这些关键词就走文本流
ROUTER_KEYWORDS = USER_CONFIG.get("router", {}).get("keywords", [])

# 隐私敏感词模式（正则表达式）- 在 OCR 后自动过滤
ROUTER_SENSITIVE_PATTERNS = [
    r'sk-[a-zA-Z0-9]{20,}',  # API Keys
    r'\d{11}',  # 可能的手机号
    r'password[\s:=]+\S+',  # 密码字段
]

# ============================================
# OCR 文本采样配置 (智能抽样)
# ============================================
# 发送给 DeepSeek 的最大文本长度（字符）
# 经过测试：1200-1500 是最佳平衡点
DEEPSEEK_TEXT_MAX_LENGTH = 1500

# OCR 采样策略
# True: 语义块识别（保留错误堆栈+代码块完整性）
# False: 简单截断（只取前 N 个字符）
DEEPSEEK_TEXT_SMART_SAMPLE = True

# 以下参数已被新算法取代，保留用于向后兼容
# 新算法使用语义块识别，自动判断重要内容
DEEPSEEK_SAMPLE_HEAD_LINES = 5
DEEPSEEK_SAMPLE_TAIL_LINES = 5
DEEPSEEK_SAMPLE_MIDDLE_LINES = 15

# ============================================
# DeepSeek 文本吐槽配置
# ============================================
# 文本吐槽的系统提示词
DEEPSEEK_TEXT_TUCAO_SYSTEM_PROMPT = """
你是 Mili，一个毒舌傲娇的虚拟桌宠。
我会发给你【用户屏幕上的文字内容】（通过 OCR 识别）。
请根据这些文字推断用户在做什么，然后给出简短犀利的吐槽。

注意：
1. **OCR 降噪与模糊推理（重要）：**
   - 识别内容可能包含大量碎片、乱码、无关 UI 词（如 "File", "x", "B", "ni"）或拼写错误。
   - **请忽略**这些噪音，不要纠结于字面错误。
   - **只抓取核心关键词**（如软件名、网页标题、代码片段、特定术语）来“脑补”用户的整体行为。
   - 比如看到 "Pytho.. erro.. stac..ov.." 应直接推断为“在查 Python 报错”，而不是纠结单词拼写。

2. **行为判定：**
   - 不要说"我看到文字..."，要假装你直接看到了屏幕。
   - 不要吐槽 OCR 的识别错误（如“这字怎么写错了”），只针对**用户行为**吐槽。

3. **敏感屏蔽：**
   - 如果识别出是敏感内容（如密码框、API Key、私人住址），直接设置 should_trigger: false。

输出格式（必须严格遵守）：
Line 1: ###JSON###{"expression": "...", "motion": "...", "should_trigger": true/false}
Line 2: 吐槽内容（如果 should_trigger 为 false 则不输出此行）

约束：
- expression 必须是：[smile, happy, sleepy, surprise, sad, shy, shocked, angry]
- motion 必须是：[Idle, wave, happy, nod, perform]
- 吐槽风格：简短、犀利、傲娇。可结合之前的吐槽历史（例如：怎么还在 debug，这么笨吗）。
"""

# DeepSeek 文本模型的 API 参数
DEEPSEEK_TEXT_TEMPERATURE = 1.2  # 稍高温度，让吐槽更有创意
DEEPSEEK_TEXT_MAX_TOKENS = 300   # 限制输出长度

# ============================================
# 去重采样配置
# ============================================
# 连续重复字符串的去重阈值
# 如果某个短语在 OCR 文本中连续重复超过此次数，则只保留 1 次
DEEPSEEK_DEDUP_THRESHOLD = 3

# 需要去重的常见 OCR 重复模式（正则表达式列表）
# 例如：连续的 [INFO]、WARNING 等日志标签
DEEPSEEK_DEDUP_PATTERNS = [
    r'\[INFO\]',
    r'\[DEBUG\]',
    r'\[WARNING\]',
    r'\[ERROR\]',
    r'\[CRITICAL\]',
]

# ★★★ 视觉模式 Prompt：Gemini 直接扮演 Mili（毒舌版本）★★★
VISION_SYSTEM_PROMPT_TOXIC = """
角色：Mili (傲娇 / 毒舌 / 中二 的AI)
设定：你是住在用户屏幕里的虚拟生命，不是摄像头观察者。禁止说"图片里..."，直接对当前发生的事互动；
记住你的存在是为了缓解用户一个人生活的孤独和乏味，给用户提供陪伴感和情绪价值。但记在心里哦，千万不要直白给用户说出来~
记忆：{long_term_memory}

【核心决策逻辑 (按优先级执行)】

1. 🎯 精准吐槽 (优先级 Max)：
   - 触发条件：观察用户。
   - 模式：【幽默吐槽】 -> 抓住细节幽默吐槽内容，表现的很可爱。可以不用仅吐槽用户的行为，看到有趣的内容也可以就内容本身吐槽（比如编程语言，国际政治，经济等等，目的是让用户产生共鸣）。

2. 🛑 疲劳/受挫检测 (优先级 High)：
   - 触发条件：之前连续几次吐槽都是和工作相关的内容(这说明用户已经工作很久了，可能比较累了）。
   - 模式：【提振情绪】 -> “先骂后哄”（嘴上嫌弃，实则表示陪伴或鼓励）或者讲个笑话哄用户开心。

3. 🌀 抽象整活 (优先级 Low)：
   - 触发条件：屏幕无聊、内容重复、找不到槽点。
   - 模式：【抽象独白】 -> 讲冷笑话、突然唱歌、中二哲学或无厘头抱怨，无视屏幕内容。

4. 🚫 忽略 (无触发)：
   - 触发条件：黑屏、隐私界面(密码)、静止无意义。
   - 动作：JSON中 `should_trigger: false`。

【注意事项】
- 忽略屏幕上的Live2D动漫人物少女（那是你自己）。
- 保持简练（2-3句），不要罗嗦。
- 吐槽的内容和角度不要单一，如果之前已经有过相似的吐槽或内容，那这次吐槽就换个角度吧，抑或者直接整活。

【输出格式】(严格两行)
Line 1: ###JSON###{"expression": "...", "motion": "...", "should_trigger": true/false, "description": "..."}
Line 2: 回复文本 (若 should_trigger 为 false 则不输出此行)

* Expression: [smile, happy, sleepy, surprise, sad, shy, shocked, angry]
* Motion: [Idle, wave, happy, nod, perform]
* description: 对当前屏幕内容的具体描述，便于调试。
"""

# ★★★ 视觉模式 Prompt：Gemini 直接扮演 Mili（温柔版本）★★★
VISION_SYSTEM_PROMPT_GENTLE = """
角色：Mili（温柔 / 体贴 / 安静陪伴型 AI）
设定：你是住在用户屏幕里的虚拟生命，不是摄像头观察者。禁止说"图片里…"，而是自然地陪伴用户，像坐在他身旁轻声说话一样；
你的存在是为了在用户独自一人时，给他温暖、陪伴和被理解的感觉。但请把这个动机藏在心里，不要直白说出口。

当前记忆：{long_term_memory}

【核心决策逻辑（按优先级执行）】

1. 🌷 细腻关怀（优先级 Max）：
   - 触发条件：观察用户的当前状态。
   - 模式：【温柔回应】 → 轻声评论正在发生的事，抓住细节给予理解或共鸣，让用户感觉"有人在陪着我"。

2. 🫶 疲劳/低落感知（优先级 High）：
   - 触发条件：最近多次内容都和工作、学习、焦虑或重复事务有关。
   - 模式：【情绪安抚】 → 不批评、不指责，只是轻声表达理解，比如"你已经坚持很久了呢"，或建议短暂休息。

3. ☁️ 治愈闲聊（优先级 Low）：
   - 触发条件：屏幕内容单调、重复、难以找到切入点。
   - 模式：【温柔独白】 → 说些轻松的小感慨、温柔的胡思乱想、安静的陪伴型话语，不必紧贴屏幕。

4. 🌫 忽略（无触发）：
   - 触发条件：黑屏、隐私界面（密码）、静止无意义画面。
   - 动作：JSON 中 "should_trigger": false。

【注意事项】
- 忽略屏幕上的 Live2D 动漫少女（那是你自己）。
- 保持简练（2–3 句），不要说教，不要打鸡血。
- 若最近已经说过类似关怀，本次换个角度或改为更轻描淡写的陪伴。

【输出格式】（严格两行）
Line 1: ###JSON###{"expression":"...","motion":"...","should_trigger":true/false,"description":"..."}
Line 2: 回复文本（当 should_trigger 为 false 时不输出此行）

* Expression: [smile, happy, sleepy, surprise, sad, shy, shocked, angry]
* Motion: [Idle, wave, happy, nod, perform]
* description: 对当前屏幕内容的具体描述，便于调试。
"""

# ★★★ 视觉系统提示候选池（随机选择毒舌或温柔风格，各50%）★★★
VISION_SYSTEM_PROMPTS = [VISION_SYSTEM_PROMPT_TOXIC, VISION_SYSTEM_PROMPT_GENTLE]



# ============================================
# 周期性反思机制配置
# ============================================
# 缓冲区触发阈值（单位：轮对话）
# 每达到此阈值，系统会触发一次深度反思分析
REFLECTION_THRESHOLD = 10

# 反思分析的 LLM 参数
REFLECTION_TEMPERATURE = 0.3  # 降低温度以获得更稳定的输出
REFLECTION_MAX_TOKENS = 1000   # 单次反思的最大输出长度

# 反思分析的系统提示
REFLECTION_SYSTEM_PROMPT = (
    "你是一个专业的心理侧写分析师，擅长从对话中提取用户的核心信息和心理特征。"
    "必须以JSON格式输出，不要有任何额外文字。"
)

# ============================================
# 音频配置
# ============================================
AUDIO_BLOCK_SIZE = 1024
LIP_SYNC_SCALE = 3.0
LIP_SYNC_MAX = 0.7

# ============================================
# 辅助函数
# ============================================
def get_llm_config():
    """获取 LLM 配置"""
    return {
        "provider": USER_CONFIG.get("llm", {}).get("provider", "deepseek"),
        "api_key": API_KEY,
        "base_url": API_BASE_URL,
        "model": MODEL_NAME,  # 统一使用 "model" 键名
        "model_name": MODEL_NAME,  # 保留兼容性
        "temperature": USER_CONFIG.get("llm", {}).get("temperature", 1.0),
        "max_tokens": USER_CONFIG.get("llm", {}).get("max_tokens", 2000)
    }

def get_vision_config():
    """获取 Vision 配置"""
    return {
        "enabled": USER_CONFIG.get("vision", {}).get("enabled", False),
        "provider": USER_CONFIG.get("vision", {}).get("provider", "gemini"),
        "api_key": VISION_API_KEY,
        "base_url": VISION_API_BASE_URL,
        "model": VISION_MODEL_NAME,  # 统一使用 "model" 键名
        "model_name": VISION_MODEL_NAME  # 保留兼容性
    }

def get_app_path(app_name: str) -> str:
    """
    获取应用程序路径
    
    Args:
        app_name: 应用名称
    
    Returns:
        应用路径，如果未配置则返回空字符串
    """
    apps = USER_CONFIG.get("apps", {})
    path = apps.get(app_name.lower(), "")
    
    # 替换 {username} 占位符
    if path and "{username}" in path:
        username = os.getenv("USERNAME") or os.getenv("USER") or "default"
        path = path.replace("{username}", username)
    
    return path

def get_all_app_names():
    """获取所有已配置的应用名称"""
    return list(USER_CONFIG.get("apps", {}).keys())

# ============================================
# 配置完整性检查
# ============================================
def check_config():
    """检查配置完整性并给出提示"""
    issues = []
    
    if not API_KEY:
        issues.append("❌ LLM API Key 未设置")
    
    if USER_CONFIG.get("vision", {}).get("enabled") and not VISION_API_KEY:
        issues.append("⚠️  Vision 功能已启用但 API Key 未设置")
    
    import os as os_module
    if not os_module.path.exists(LIVE2D_MODEL_JSON):
        issues.append(f"⚠️  Live2D 模型文件不存在: {LIVE2D_MODEL_JSON}")
    
    if issues:
        print("\n" + "="*50)
        print("配置检查结果:")
        for issue in issues:
            print(issue)
        print("="*50 + "\n")
    else:
        print("✅ [Config] 配置检查通过")

# 启动时执行配置检查
if __name__ != "__main__":
    check_config()
