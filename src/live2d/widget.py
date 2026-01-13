"""Live2D Widget - 渲染组件"""
import os

import OpenGL.GL as gl
import live2d.v3 as live2d
from PySide6.QtCore import QTimerEvent
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from src.core.config import LIVE2D_MODEL_JSON
from src.core.signals import signal_bus
from src.live2d.motion import ExpressionMixer, BodyMotionEngine, GestureEngine


class Live2DWidget(QOpenGLWidget):
    """Live2D 渲染组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 400)
        self.model: live2d.LAppModel | None = None
        self.is_initialized = False
        
        # 口型同步变量
        self.current_mouth_value = 0.0
        
        # 引擎实例化
        self.expression_mixer = ExpressionMixer()
        self.body_motion_engine = BodyMotionEngine()
        self.gesture_engine = GestureEngine()

        # 动作状态标记 (防止重复触发 Idle)
        self.is_body_idling = True
        
        # ============================================
        # 连接信号总线
        # ============================================
        signal_bus.lip_sync_value.connect(self.set_lip_sync)
        signal_bus.agent_emotion_changed.connect(self.set_expression)
        signal_bus.agent_motion_triggered.connect(self._handle_motion_trigger)

    def initializeGL(self):
        """初始化 OpenGL 和 Live2D 模型"""
        live2d.glInit()
        self.model = live2d.LAppModel()
        
        model_path = LIVE2D_MODEL_JSON
        
        if os.path.exists(model_path):
            self.model.LoadModelJson(model_path)
            # 初始化完成后，先播放一次 Idle
            self.start_motion("Idle")
        else:
            print(f"❌ 模型文件未找到: {model_path}")
        
        self.model.Resize(self.width(), self.height())
        self.startTimer(int(1000 / 60))  # 60 FPS
        self.is_initialized = True

    def resizeGL(self, w, h):
        """窗口大小改变时调用"""
        if self.model:
            self.model.Resize(w, h)

    def paintGL(self):
        """绘制 Live2D 模型"""
        # 背景完全透明
        live2d.clearBuffer(0.0, 0.0, 0.0, 0.0)
        
        if self.model:
            # 1. 基础物理更新
            self.model.Update()
            
            # 2. 表情层
            self.expression_mixer.update_model(self.model)
            
            # ★★★ 自动归位逻辑 ★★★
            if self.expression_mixer.is_resetting and not self.is_body_idling:
                print("💤 互动结束，身体动作回归 Idle...")
                self.start_motion("Idle")
                self.is_body_idling = True

            # 3. 身体律动层
            self.body_motion_engine.update_model(self.model, self.current_mouth_value)
            
            # 4. 手势层
            self.gesture_engine.update_model(self.model, self.current_mouth_value)
            
            # 5. 口型层
            self.model.SetParameterValue("ParamA", self.current_mouth_value, 1.0)
            
            # 6. 绘制
            self.model.Draw()

    def timerEvent(self, event: QTimerEvent):
        """定时器事件 - 触发重绘"""
        self.update()

    def start_motion(self, motion_group: str, no: int = 0):
        """
        播放动作
        
        Args:
            motion_group: 动作组名 (Idle, TapBody, etc.)
            no: 动作编号
        """
        if self.model:
            self.model.StartMotion(motion_group, no, live2d.MotionPriority.FORCE)
            
            # 更新状态
            if motion_group == "Idle":
                self.is_body_idling = True
            else:
                self.is_body_idling = False
                self.expression_mixer.refresh_timer()

    def set_lip_sync(self, open_value: float):
        """
        设置口型同步值
        
        Args:
            open_value: 嘴巴张开程度 (0.0 - 1.0)
        """
        self.current_mouth_value = open_value
        if open_value > 0.1:
            self.expression_mixer.refresh_timer()

    def set_expression(self, expression_id: str):
        """
        切换表情
        
        Args:
            expression_id: 表情ID (smile, happy, sleepy, etc.)
        """
        self.expression_mixer.set_expression(expression_id)
    
    def _handle_motion_trigger(self, motion_name: str):
        """
        处理动作触发信号 (内部方法)
        
        Args:
            motion_name: 动作名称 (wave, nod, happy, etc.)
        """
        import random
        
        target_group = "Idle"
        index = 0
        cmd = motion_name.lower()
        
        if cmd in ["wave", "hello", "hi", "greet", "bye"]:
            target_group = "TapBody"
            index = 2
        elif cmd in ["happy", "excited", "laugh", "yes", "cheer"]:
            target_group = "TapBody"
            index = 0
        elif cmd in ["nod", "agree", "relax", "smile", "ok", "normal"]:
            target_group = "TapBody"
            index = 1
        elif cmd in ["magic", "dance", "perform", "surprise"]:
            target_group = "TapBody"
            index = random.choice([3, 4, 5])
        elif cmd in ["angry", "panic", "shocked"]:
            target_group = "TapBody"
            index = 0
        
        if target_group != "Idle":
            self.start_motion(target_group, index)
    
    def try_hit_test(self, widget_x: int, widget_y: int) -> bool:
        """
        像素级点击检测
        
        Args:
            widget_x: 相对于 Widget 左上角的 x 坐标
            widget_y: 相对于 Widget 左上角的 y 坐标
            
        Returns:
            True: 点击到了人物 (非透明像素)
            False: 点击到了透明区域
        """
        # 确保当前是 OpenGL 上下文
        self.makeCurrent()
        
        # 获取屏幕缩放比例 (处理高分屏)
        ratio = self.devicePixelRatio()
        
        # 坐标转换
        gl_x = int(widget_x * ratio)
        gl_y = int((self.height() - widget_y) * ratio)
        
        try:
            # 读取 1x1 像素的 RGBA 颜色值
            data = gl.glReadPixels(gl_x, gl_y, 1, 1, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE)
            
            # Alpha > 0 说明点击到了非透明的人物身体
            alpha = data[3]
            return alpha > 0
        except Exception as e:
            print(f"Hit test error: {e}")
            return False
