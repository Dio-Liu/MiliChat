"""主窗口 - 桌面宠物容器"""
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QSlider, QPushButton, QFrame, QApplication
)

from src.core.config import WINDOW_BASE_WIDTH, WINDOW_BASE_HEIGHT
from src.core.signals import signal_bus
from src.live2d import Live2DWidget
from src.ui.chat_window import ChatWindow
from src.ui.bubble_widget import ComicBubble


class DesktopPetWindow(QWidget):
    """桌面宠物主窗口"""
    
    def __init__(self):
        super().__init__()
        
        # 窗口属性设置
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        
        # 设置窗口大小
        self.base_width = WINDOW_BASE_WIDTH
        self.base_height = WINDOW_BASE_HEIGHT
        self.resize(self.base_width, self.base_height)
        
        # 初始化布局
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        
        # Live2D 组件
        self.live2d_view = Live2DWidget()
        self.live2d_view.setMouseTracking(True)
        self.live2d_view.setFixedSize(self.base_width, self.base_height)
        
        layout.addWidget(self.live2d_view)
        
        # 创建悬浮控制栏
        self.control_bar = self.create_control_bar()
        self.control_bar.hide()
        
        self.setLayout(layout)
        
        # 初始化聊天窗口
        self.chat_win = ChatWindow(self.live2d_view)
        
        # 初始化漫画气泡（独立窗口，防止被裁切）
        self.bubble = ComicBubble(None)
        
        # 连接气泡信号
        signal_bus.show_bubble_message.connect(self.on_show_bubble)
        
        # 拖拽状态变量
        self.is_dragging = False
        self.drag_start_pos: QPoint | None = None
        
        # 气泡方向缓存，避免重复日志
        self._last_bubble_direction = None
        
        # 当前缩放比例
        self.current_scale = 1.0
    
    def create_control_bar(self) -> QFrame:
        """创建悬浮控制栏"""
        control_bar = QFrame(self)
        control_bar.setObjectName("controlBar")
        control_bar.setFixedHeight(36)
        
        layout = QHBoxLayout(control_bar)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)
        
        # Size 标签
        size_label = QLabel("🔍")
        size_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 14px;
                background: transparent;
                margin-top: 2px;
            }
        """)
        
        # Size 滑块
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setMinimum(50)
        self.size_slider.setMaximum(200)
        self.size_slider.setValue(100)
        self.size_slider.setFixedWidth(90)
        self.size_slider.valueChanged.connect(self.on_size_changed)
        self.size_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background: rgba(255, 255, 255, 0.3);
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: white;
                border: 1px solid #667eea;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #667eea;
            }
        """)
        
        # 透明度标签
        opacity_label = QLabel("💫")
        opacity_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 14px;
                background: transparent;
                margin-top: 2px;
            }
        """)
        
        # 透明度滑块
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setMinimum(30)
        self.opacity_slider.setMaximum(100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setFixedWidth(60)
        self.opacity_slider.valueChanged.connect(self.on_opacity_changed)
        self.opacity_slider.setStyleSheet(self.size_slider.styleSheet())
        
        # 关闭按钮
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.clicked.connect(self.close_app)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 59, 48, 0.9);
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 12px;
                font-weight: bold;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background: rgba(255, 59, 48, 1);
            }
        """)
        
        layout.addWidget(size_label)
        layout.addWidget(self.size_slider)
        layout.addWidget(opacity_label)
        layout.addWidget(self.opacity_slider)
        layout.addStretch()
        layout.addWidget(close_btn)
        
        # 整体容器样式
        control_bar.setStyleSheet("""
            #controlBar {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(102, 126, 234, 0.92), 
                    stop:1 rgba(118, 75, 162, 0.92));
                border-radius: 18px;
                border: 1px solid rgba(255, 255, 255, 0.3);
            }
        """)
        
        return control_bar
    
    def on_size_changed(self, value: int):
        """调整人物大小"""
        self.current_scale = value / 100.0
        
        # 计算人物大小
        model_w = int(self.base_width * self.current_scale)
        model_h = int(self.base_height * self.current_scale)
        
        # 设置 Live2D 组件大小
        self.live2d_view.setFixedSize(model_w, model_h)
        
        # 计算窗口大小
        bar_width = self.control_bar.width() if self.control_bar.isVisible() else 360
        min_window_w = bar_width + 20
        
        final_window_w = max(model_w, min_window_w)
        final_window_h = max(model_h, 80)
        
        self.resize(final_window_w, final_window_h)
        
        # 重新定位控制栏
        if self.control_bar.isVisible():
            new_bar_x = (final_window_w - self.control_bar.width()) // 2
            self.control_bar.move(new_bar_x, 20)
    
    def on_opacity_changed(self, value: int):
        """调整透明度"""
        self.setWindowOpacity(value / 100.0)
    
    def close_app(self):
        """关闭应用程序"""
        QApplication.quit()
    
    def update_chat_position(self):
        """根据人物位置自适应计算聊天框位置"""
        if not self.chat_win.isVisible():
            return

        pet_geo = self.geometry()
        chat_geo = self.chat_win.geometry()
        screen = self.screen().availableGeometry()
        
        spacing = 15

        # 垂直居中对齐
        target_y = pet_geo.top() + (pet_geo.height() - chat_geo.height()) // 2

        # 边界检查
        if target_y < screen.top() + spacing:
            target_y = screen.top() + spacing
        elif target_y + chat_geo.height() > screen.bottom() - spacing:
            target_y = screen.bottom() - chat_geo.height() - spacing

        # 水平位置 (优先右侧)
        target_x = pet_geo.right() + spacing
        
        if target_x + chat_geo.width() > screen.right():
            target_x = pet_geo.left() - chat_geo.width() - spacing
            
            if target_x < screen.left():
                target_x = screen.left() + spacing

        self.chat_win.move(target_x, target_y)
    
    def enterEvent(self, event):
        """鼠标进入窗口区域"""
        self.show_control_bar()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """鼠标离开窗口区域"""
        self.hide_control_bar()
        super().leaveEvent(event)
    
    def show_control_bar(self):
        """显示控制栏"""
        self.control_bar.show()
        self.control_bar.adjustSize()
        
        bar_width = self.control_bar.width()
        bar_x = (self.width() - bar_width) // 2
        
        self.control_bar.move(bar_x, 20)
        self.control_bar.raise_()
    
    def hide_control_bar(self):
        """隐藏控制栏"""
        self.control_bar.hide()
    
    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下事件"""
        if event.button() == Qt.LeftButton:
            # 重置待机计时器（拖拽不算聊天活动）
            self.chat_win.reset_idle_timer(is_chat_activity=False)
            
            # 获取点击位置
            local_pos = event.position().toPoint()
            
            # 转换到 Live2D 坐标
            l2d_geometry = self.live2d_view.geometry()
            l2d_offset_x = l2d_geometry.x()
            l2d_offset_y = l2d_geometry.y()
            
            l2d_x = local_pos.x() - l2d_offset_x
            l2d_y = local_pos.y() - l2d_offset_y
            
            # 像素检测
            if self.live2d_view.try_hit_test(l2d_x, l2d_y):
                self.is_dragging = True
                self.drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                print("🖱️ 捕获人物，开始拖拽")
            else:
                print("💨 点到了空气")
        
        elif event.button() == Qt.RightButton:
            # 重置待机计时器（右键切换窗口不算聊天活动）
            self.chat_win.reset_idle_timer(is_chat_activity=False)
            
            # 显示/隐藏聊天窗口
            if self.chat_win.isVisible():
                self.chat_win.hide()
            else:
                self.chat_win.show()
                self.update_chat_position()
                self.chat_win.raise_()
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动事件"""
        if self.is_dragging and (event.buttons() & Qt.LeftButton):
            new_pos = event.globalPosition().toPoint() - self.drag_start_pos
            self.move(new_pos)
            
            # 如果聊天窗开着，让它跟着移动
            if self.chat_win.isVisible():
                self.update_chat_position()
            
            # 如果气泡显示着，让它跟着移动
            self.update_bubble_position()
                
            event.accept()
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放事件"""
        self.is_dragging = False
    
    def moveEvent(self, event):
        """窗口移动事件 - 让气泡跟随"""
        super().moveEvent(event)
        # 如果气泡正在显示且不在拖拽中，更新位置
        # (拖拽时已在mouseMoveEvent中处理，避免重复)
        if self.bubble.isVisible() and not self.is_dragging:
            self.update_bubble_position()
    
    def on_show_bubble(self, text: str):
        """显示漫画气泡 - 入口函数
        
        Args:
            text: 要显示的文本
        """
        # 1. 先让气泡准备文字并自适应大小（此时气泡大小已确定，但位置还没定，也没显示）
        self.bubble.prepare_message(text)
        
        # 2. 根据气泡当前的大小，计算它应该在哪里（包括边界检测和翻转逻辑）
        self.update_bubble_position()
        
        # 3. 一切就绪，显示出来
        self.bubble.show_message()
    
    def update_bubble_position(self):
        """智能计算气泡位置（防出界 + 自动翻转）"""
        # 如果气泡不可见，无需更新位置
        if not self.bubble.isVisible():
            return
        
        pet_geo = self.geometry()
        screen = self.screen().availableGeometry()  # 获取当前屏幕尺寸
        
        bubble_w = self.bubble.width()
        bubble_h = self.bubble.height()
        
        # 策略 A: 默认放在人物右侧靠近处 (气泡尖角朝左)
        # 气泡左边 = 人物右边 - 一点重叠(55px，更靠近人物)
        target_x = pet_geo.right() - 55
        # 气泡底部 = 人物头部位置下方 (偏移80px，更接近肩膀高度)
        target_y = pet_geo.top() - bubble_h + 80
        
        # --- 边界检测逻辑 ---
        
        # 检测 1: 右侧是否出界？
        if target_x + bubble_w > screen.right():
            # [右侧空间不足] -> 切换到人物左侧 (气泡尖角朝右)
            if self._last_bubble_direction != "right":
                print("🧱 气泡触碰右边界，翻转到左侧")
                self._last_bubble_direction = "right"
            
            # 气泡右边 = 人物左边 + 一点重叠(55px，拉近距离)
            target_x = pet_geo.left() - bubble_w + 55
            
            # 告诉气泡组件：你的尖角应该朝右
            self.bubble.set_direction("right")
        else:
            # [右侧空间充足] -> 保持在右侧
            if self._last_bubble_direction != "left":
                self._last_bubble_direction = "left"
            # 告诉气泡组件：你的尖角应该朝左
            self.bubble.set_direction("left")
            
        # 检测 2: 顶部是否出界？
        if target_y < screen.top():
            # 如果气泡跑出屏幕上边缘，就往下挪一点
            target_y = screen.top() + 10
            
        # 执行移动
        self.bubble.move(int(target_x), int(target_y))
    
    def closeEvent(self, event):
        """窗口关闭事件 - 确保保存剩余的对话记忆"""
        print("\n" + "=" * 60)
        print("👋 [MainWindow] 程序即将退出...")
        print("=" * 60)
        
        # 关闭气泡
        if hasattr(self, 'bubble'):
            self.bubble.close()
        
        # 调用 agent 的 close 方法保存剩余的对话记忆
        try:
            if hasattr(self, 'chat_win') and hasattr(self.chat_win, 'agent'):
                self.chat_win.agent.close()
        except Exception as e:
            print(f"❌ [MainWindow] 关闭 Agent 时出错: {e}")
        
        # 关闭聊天窗口
        if hasattr(self, 'chat_win'):
            self.chat_win.close()
        
        print("✅ [MainWindow] 程序退出完成")
        event.accept()
