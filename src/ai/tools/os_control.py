"""系统控制工具集 - 调节音量、亮度、启动应用"""
import os
import platform
import subprocess
import screen_brightness_control as sbc
from src.ai.tools_manager import tool_manager
from src.core.config import get_app_path, get_all_app_names

# 检测操作系统
SYSTEM_OS = platform.system()  # 'Windows', 'Linux', 'Darwin' (macOS)

# --- 音量控制依赖 (Windows) ---
if SYSTEM_OS == "Windows":
    try:
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        PYCAW_AVAILABLE = True
    except ImportError:
        print("⚠️ Pycaw not found, volume control may fail on Windows.")
        PYCAW_AVAILABLE = False
else:
    PYCAW_AVAILABLE = False


# ==========================================
# 工具 1: 系统音量控制
# ==========================================
@tool_manager.register(
    "set_system_volume", 
    "调整电脑系统音量。参数 value 是 0-100 的整数。如果用户说'声音大点'、'调大音量'、'小声点'等，请基于当前推测一个合理的数值。"
)
def set_system_volume(value: str):
    """
    调整系统音量
    
    Args:
        value: 音量值，0-100 的整数（可能包含 % 符号）
    
    Returns:
        dict: 包含状态和消息的字典
    """
    if SYSTEM_OS == "Windows":
        if not PYCAW_AVAILABLE:
            return {"status": "error", "msg": "音量控制库未安装 (需要 pycaw)"}
        
        try:
            # 1. 数据清洗 (LLM 有时会传 "50%" 或 "50")
            vol_int = int(str(value).replace("%", "").strip())
            vol_int = max(0, min(100, vol_int))  # 限制在 0-100
            
            # 2. 调用 Windows API
            devices = AudioUtilities.GetSpeakers()
            volume = devices.EndpointVolume
            
            # Pycaw 使用 Scalar (0.0 - 1.0)
            volume.SetMasterVolumeLevelScalar(vol_int / 100.0, None)
            
            return {"status": "success", "msg": f"系统音量已调整为 {vol_int}%"}
        except Exception as e:
            return {"status": "error", "msg": f"调节音量失败: {str(e)}"}
    
    elif SYSTEM_OS == "Darwin":  # macOS
        try:
            vol_int = int(str(value).replace("%", "").strip())
            vol_int = max(0, min(100, vol_int))
            os.system(f"osascript -e 'set volume output volume {vol_int}'")
            return {"status": "success", "msg": f"系统音量已调整为 {vol_int}%"}
        except Exception as e:
            return {"status": "error", "msg": f"调节音量失败: {str(e)}"}
    
    else:
        return {"status": "error", "msg": f"暂不支持 {SYSTEM_OS} 系统的音量调节"}


# ==========================================
# 工具 2: 屏幕亮度控制
# ==========================================
@tool_manager.register(
    "set_screen_brightness", 
    "调整主显示器的屏幕亮度。参数 value 是 0-100 的整数。当用户说'调亮一点'、'屏幕太暗了'、'降低亮度'等时使用。"
)
def set_screen_brightness(value: str):
    """
    调整屏幕亮度
    
    Args:
        value: 亮度值，0-100 的整数（可能包含 % 符号）
    
    Returns:
        dict: 包含状态和消息的字典
    """
    try:
        val_int = int(str(value).replace("%", "").strip())
        val_int = max(0, min(100, val_int))  # 限制在 0-100
        
        # 这一步可能会有延迟，但对于亮度来说可以接受
        sbc.set_brightness(val_int)
        
        return {"status": "success", "msg": f"屏幕亮度已调整为 {val_int}%"}
    except Exception as e:
        return {"status": "error", "msg": f"调节亮度失败: {str(e)}"}


# ==========================================
# 工具 3: 应用启动器
# ==========================================
@tool_manager.register(
    "open_application", 
    "打开指定的应用程序。参数 app_name 是应用的名称（如 music, chrome, notepad, calculator, wechat 等）。当用户说'打开某某软件'、'启动某某'、'帮我开一下某某'时使用。"
)
def open_application(app_name: str):
    """
    启动指定应用程序
    
    Args:
        app_name: 应用程序名称
    
    Returns:
        dict: 包含状态和消息的字典
    """
    key = app_name.lower().strip()
    
    # 1. 从配置文件获取路径
    target_path = get_app_path(key)
    
    # 2. 如果没找到，尝试模糊匹配
    if not target_path:
        all_apps = get_all_app_names()
        for app in all_apps:
            if key in app or app in key:
                target_path = get_app_path(app)
                break
    
    if target_path:
        try:
            # 对于系统自带程序（如 calc.exe, notepad.exe），直接启动
            # 对于完整路径，检查文件是否存在
            if target_path.endswith(".exe") and not os.path.isabs(target_path):
                # 系统程序，直接启动
                subprocess.Popen(target_path, shell=True)
                return {"status": "success", "msg": f"正在为您启动 {app_name}..."}
            elif os.path.exists(target_path):
                # 完整路径且文件存在
                subprocess.Popen(target_path, shell=True)
                return {"status": "success", "msg": f"正在为您启动 {app_name}..."}
            else:
                return {"status": "error", "msg": f"找不到应用程序: {target_path}"}
        except Exception as e:
            return {"status": "error", "msg": f"启动失败: {str(e)}"}
    else:
        all_apps = get_all_app_names()
        return {
            "status": "error", 
            "msg": f"抱歉，我还没学会怎么打开 '{app_name}'。\n支持的应用: {', '.join(all_apps[:10])}...\n请在 config.yaml 中配置应用路径。"
        }


# ==========================================
# 工具 4: 获取当前音量 (可选)
# ==========================================
@tool_manager.register(
    "get_system_volume",
    "获取当前系统音量。当用户询问'现在音量多少'、'音量是几'等问题时使用。"
)
def get_system_volume():
    """
    获取当前系统音量
    
    Returns:
        dict: 包含状态和音量值的字典
    """
    if SYSTEM_OS == "Windows":
        if not PYCAW_AVAILABLE:
            return {"status": "error", "msg": "音量控制库未安装"}
        
        try:
            devices = AudioUtilities.GetSpeakers()
            volume = devices.EndpointVolume
            
            current_volume = int(volume.GetMasterVolumeLevelScalar() * 100)
            return {"status": "success", "msg": f"当前系统音量是 {current_volume}%", "volume": current_volume}
        except Exception as e:
            return {"status": "error", "msg": f"获取音量失败: {str(e)}"}
    
    else:
        return {"status": "error", "msg": f"暂不支持 {SYSTEM_OS} 系统的音量查询"}


# ==========================================
# 工具 5: 获取当前亮度 (可选)
# ==========================================
@tool_manager.register(
    "get_screen_brightness",
    "获取当前屏幕亮度。当用户询问'现在亮度多少'、'屏幕亮度是几'等问题时使用。"
)
def get_screen_brightness():
    """
    获取当前屏幕亮度
    
    Returns:
        dict: 包含状态和亮度值的字典
    """
    try:
        current_brightness = sbc.get_brightness()
        # sbc.get_brightness() 可能返回列表（多显示器）或整数
        if isinstance(current_brightness, list) and current_brightness:
            current_brightness = current_brightness[0]
        
        return {"status": "success", "msg": f"当前屏幕亮度是 {current_brightness}%", "brightness": current_brightness}
    except Exception as e:
        return {"status": "error", "msg": f"获取亮度失败: {str(e)}"}
