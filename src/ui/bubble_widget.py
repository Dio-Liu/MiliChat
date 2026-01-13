"""漫画风格气泡组件 - 用于显示视觉吐槽文字"""
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QPainterPath, QColor, QFont, QPen, QBrush
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QGraphicsDropShadowEffect


class ComicBubble(QWidget):
    """漫画风格的对话气泡"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 窗口属性：无边框、透明背景、置顶、不接受鼠标点击(穿透)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True) 

        # 状态：尖角方向
        self.direction = "left"  # "left"=尖角朝左(气泡在右), "right"=尖角朝右(气泡在左)

        # 样式配置
        self.border_color = QColor("#333333")  # 深灰/黑边框
        self.bg_color = QColor("#FFFFFF")      # 白底
        self.text_color = QColor("#000000")
        self.stroke_width = 3
        
        # 内部文本控件
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setStyleSheet(f"color: {self.text_color.name()}; background: transparent;")
        
        # 字体设置
        font = QFont("Microsoft YaHei", 10)  # 稍微调小适配
        font.setBold(True)
        self.label.setFont(font)

        # 布局（根据方向动态调整边距）
        self.layout = QVBoxLayout(self)
        self.update_layout_margins()  # 根据方向初始化边距
        self.layout.addWidget(self.label)

        # 自动消失定时器
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.fade_out)
        
        # 阴影效果（可选，增加立体感）
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(2, 4)
        self.setGraphicsEffect(shadow)

    def set_direction(self, direction):
        """设置气泡方向：'left' 或 'right'"""
        if self.direction != direction:
            self.direction = direction
            self.update_layout_margins()
            self.update()  # 触发重绘

    def moveEvent(self, event):
        """
        当气泡被移动时触发。
        确保每次移动后，都强制重新绘制，使得箭头方向正确反映当前位置。
        这解决了"初始箭头方向错误"的问题：
        - 气泡创建时在 (0,0)，箭头可能根据错误的初始位置判断
        - moveEvent 确保移动到正确位置后，立即重新绘制，箭头方向得到更新
        """
        super().moveEvent(event)
        # 强制刷新显示，触发 paintEvent 重新绘制
        self.update()

    def update_layout_margins(self):
        """根据尖角方向调整文字的边距，避免文字压到尖角"""
        # (左, 上, 右, 下)
        if self.direction == "left":
            # 尖角在左下，所以左边距和下边距要留空
            self.layout.setContentsMargins(25, 15, 15, 25)
        else:
            # 尖角在右下，所以右边距和下边距要留空
            self.layout.setContentsMargins(15, 15, 25, 25)

    def prepare_message(self, text):
        """准备文字并调整大小，但不显示（供外部定位计算用）
        
        自动根据文字内容调整气泡大小，同时限制最大和最小尺寸
        """
        self.label.setText(text)
        
        # 先设置临时宽度来计算文字的实际高度
        # 从最大宽度开始，逐步减小，找到最适合的宽度
        max_width = 350
        min_width = 120
        
        # 尝试最大宽度，看看高度是否合理
        self.setFixedWidth(max_width)
        self.adjustSize()
        
        current_height = self.height()
        max_height = 300  # 气泡最大高度限制
        
        # 如果高度超过最大限制，逐步减少宽度来增加行数（压缩高度）
        if current_height > max_height:
            # 从较小的宽度开始尝试，找到高度在合理范围内的宽度
            for trial_width in range(max_width - 50, min_width - 1, -20):
                self.setFixedWidth(trial_width)
                self.adjustSize()
                if self.height() <= max_height:
                    break
        
        # 根据实际内容调整宽度：如果文字很少，不需要那么宽
        if len(text) < 20:
            # 短文本：宽度按字符数计算
            self.setFixedWidth(min(max_width, max(min_width, len(text) * 15)))
        else:
            # 长文本：保持当前宽度（已在上面的循环中优化过）
            pass
        
        self.adjustSize()  # 最后再调整一次确保高度正确

    def show_message(self, duration=10000):
        """显示气泡（调用前请确保已调用 prepare_message 和 move）
        
        Args:
            duration: 显示时长(毫秒)，默认5秒
        """
        self.setWindowOpacity(1.0)
        self.show()
        self.hide_timer.start(duration)

    def fade_out(self):
        """(简单版) 直接隐藏，也可以做透明度动画"""
        self.hide()

    def paintEvent(self, event):
        """绘制漫画风格气泡"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        triangle_h = 15  # 尖角高度
        triangle_w = 15  # 尖角宽度
        offset = 5       # 边框偏移量

        # 定义气泡主体区域 (减去下方尖角的高度)
        bubble_rect = QRectF(offset, offset, w - 2*offset, h - triangle_h - 2*offset)

        path = QPainterPath()
        path.addRoundedRect(bubble_rect, 10, 10)

        # 绘制尖角 - 根据方向动态调整
        base_y = bubble_rect.bottom()  # 尖角基准Y坐标 (气泡底部)
        
        if self.direction == "left":
            # 尖角指向左下 (人物在气泡左侧，气泡在人物右侧)
            tail_x = offset + 20
            
            path.moveTo(tail_x + triangle_w, base_y)     # 右基点
            path.lineTo(tail_x, h - offset)              # 尖端 (指向左下)
            path.lineTo(tail_x, base_y - 5)              # 左基点(稍微往上融合)
            
        else:  # direction == "right"
            # 尖角指向右下 (人物在气泡右侧，气泡在人物左侧)
            tail_x = w - offset - 20
            
            path.moveTo(tail_x - triangle_w, base_y)     # 左基点
            path.lineTo(tail_x, h - offset)              # 尖端 (指向右下)
            path.lineTo(tail_x, base_y - 5)              # 右基点
        
        # 绘制
        path_outline = path.simplified()
        painter.setPen(QPen(self.border_color, self.stroke_width))
        painter.setBrush(QBrush(self.bg_color))
        painter.drawPath(path_outline)
