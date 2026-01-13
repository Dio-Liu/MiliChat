"""全局信号总线 - 解决组件间通信的关键"""
from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    """
    全局信号总线，用于组件间的解耦通信。
    
    各组件通过信号通信，而不是直接持有对方的引用，实现松耦合架构。
    """
    
    # ============================================
    # AI -> Live2D / Audio
    # ============================================
    agent_emotion_changed = Signal(str)      # 表情改变 (smile, sleepy, happy, etc.)
    agent_motion_triggered = Signal(str)     # 动作触发 (wave, nod, happy, etc.)
    
    # ============================================
    # Audio -> Live2D
    # ============================================
    lip_sync_value = Signal(float)           # 口型同步值 (0.0 - 1.0)
    
    # ============================================
    # UI -> AI
    # ============================================
    user_input_received = Signal(str)        # 用户发送了消息
    
    # ============================================
    # 其他控制信号
    # ============================================
    idle_timer_reset = Signal()              # 重置待机计时器
    
    # ============================================
    # UI 视觉反馈
    # ============================================
    show_bubble_message = Signal(str)        # 显示漫画气泡消息


# 全局单例实例
signal_bus = SignalBus()
