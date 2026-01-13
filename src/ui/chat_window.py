"""聊天窗口 - UI 交互组件"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, 
    QLineEdit, QPushButton, QFrame, QApplication, QMessageBox
)

from src.core.config import IDLE_TIMEOUT_MS, IDLE_TIMEOUT_PROMPT, VISION_USE_VOICE
from src.core.signals import signal_bus
from src.ai import DeepSeekAgent
from src.audio import AudioSystem
from src.audio.voice_input import VoiceInputThread  # ★ 新增：语音识别
from src.ai.vision import VisionThread  # ★ 新增：视觉线程


class ChatWindow(QWidget):
    """聊天窗口"""
    
    def __init__(self, live2d_widget):
        super().__init__()
        self.l2d = live2d_widget
        self.resize(320, 200)
        
        # 初始化 AI Agent 和音频系统
        self.agent = DeepSeekAgent()
        self.audio_system = AudioSystem()
        
        # ★ 初始化语音识别
        self.voice_thread = None
        self.is_recording = False
        
        # ★ 初始化视觉线程（传入 agent 引用）
        self.vision_thread = VisionThread(agent_ref=self.agent)
        self.vision_thread.vision_reaction.connect(self.on_vision_reaction)
        self.vision_thread.start()
        print("👁️ 视觉感知系统已启动 (双大脑模式)")
        
        # 初始化 UI
        self.init_ui()
        
        # 待机定时器
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(IDLE_TIMEOUT_MS)
        self.idle_timer.timeout.connect(self.on_idle_timeout)
        self.idle_timer.start()

    def init_ui(self):
        """初始化界面"""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        # 主容器
        self.main_container = QFrame(self)
        self.main_container.setObjectName("mainContainer")
        
        main_layout = QVBoxLayout(self.main_container)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        # 聊天记录区
        self.chat_log = QPlainTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setPlaceholderText("Mili 正在聆听...")
        self.chat_log.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.chat_log.setStyleSheet("""
            QPlainTextEdit {
                background: transparent;
                color: white;
                border: none;
                font-size: 13px;
                font-family: "Microsoft YaHei", sans-serif;
                line-height: 1.6;
                padding-right: 30px;
                padding-top: 5px;
            }
        """)
        
        # 关闭按钮 (保持不变)
        self.close_chat_btn = QPushButton("×", self.main_container)
        self.close_chat_btn.setFixedSize(24, 24)
        self.close_chat_btn.setCursor(Qt.PointingHandCursor)
        self.close_chat_btn.clicked.connect(self.hide)
        self.close_chat_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: rgba(255, 255, 255, 0.6);
                border: none;
                border-radius: 12px;
                font-family: Arial;
                font-size: 16px;
                font-weight: bold;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background: rgba(255, 60, 60, 0.8);
                color: white;
            }
        """)

        # 清空按钮 (样式与关闭按钮一致)
        self.clear_btn = QPushButton("🗑️", self.main_container)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setFixedSize(24, 24)
        self.clear_btn.setToolTip("清空聊天记录")
        self.clear_btn.clicked.connect(self.on_clear_chat)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: rgba(255, 255, 255, 0.6);
                border: none;
                border-radius: 12px;
                font-size: 12px;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background: rgba(255, 60, 60, 0.8);
                color: white;
            }
        """)
        
        # 输入区
        self.input_wrapper = QFrame()
        self.input_wrapper.setFixedHeight(46)
        self.input_wrapper.setObjectName("inputWrapper")
        
        wrapper_layout = QHBoxLayout(self.input_wrapper)
        wrapper_layout.setContentsMargins(15, 5, 5, 5)
        wrapper_layout.setSpacing(5)
        
        # 输入框
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type something...")
        self.input_field.returnPressed.connect(self.on_send)
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: #2c3e50;
                font-weight: bold;
                border: none;
                font-size: 13px;
            }
        """)
        
        # 语音输入按钮 (背景透明)
        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setCursor(Qt.PointingHandCursor)
        self.mic_btn.setFixedSize(30, 30)
        self.mic_btn.setToolTip("语音输入")
        self.mic_btn.clicked.connect(self.on_voice_input)
        self.mic_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888;
                border: none;
                border-radius: 15px;
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(0, 0, 0, 0.05);
                color: #667eea;
            }
        """)
        
        # 发送按钮
        self.send_btn = QPushButton("➤")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setFixedSize(36, 36)
        self.send_btn.clicked.connect(self.on_send)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border: none;
                border-radius: 18px;
                font-size: 14px;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #5568d3, stop:1 #63428b);
            }
        """)
        
        # 调整添加顺序：输入框 -> 麦克风 -> 发送
        wrapper_layout.addWidget(self.input_field)
        wrapper_layout.addWidget(self.mic_btn)
        wrapper_layout.addWidget(self.send_btn)
        
        # 组装
        main_layout.addWidget(self.chat_log)
        main_layout.addWidget(self.input_wrapper)
        
        # 窗口主布局
        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.addWidget(self.main_container)
        
        # 样式
        self.main_container.setStyleSheet("""
            #mainContainer {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(102, 126, 234, 0.95), 
                    stop:1 rgba(118, 75, 162, 0.95));
                border-radius: 24px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            #inputWrapper {
                background: rgba(255, 255, 255, 0.9);
                border-radius: 23px;
                border: 2px solid rgba(255, 255, 255, 0.5);
            }
        """)

    def resizeEvent(self, event):
        """重写大小改变事件 - 定位右上角悬浮按钮"""
        super().resizeEvent(event)
        if hasattr(self, 'close_chat_btn') and hasattr(self, 'main_container'):
            margin = 15
            
            # 1. 定位关闭按钮 (最右侧)
            close_w = self.close_chat_btn.width()
            close_x = self.main_container.width() - close_w - margin
            close_y = margin
            
            self.close_chat_btn.move(close_x, close_y)
            self.close_chat_btn.raise_()
            
            # 2. 定位清空按钮 (在关闭按钮左侧)
            if hasattr(self, 'clear_btn'):
                clear_w = self.clear_btn.width()
                spacing = 8  # 按钮之间的间距
                
                clear_x = close_x - clear_w - spacing
                clear_y = margin
                
                self.clear_btn.move(clear_x, clear_y)
                self.clear_btn.raise_()

    def reset_idle_timer(self, is_chat_activity=False):
        """重置待机计时器
        
        Args:
            is_chat_activity: 是否是真正的聊天活动（用户发送消息或收到回复）
                             如果为 True，会通知视觉线程重置检查计时器
        """
        if self.idle_timer.isActive():
            self.idle_timer.stop()
        self.idle_timer.start()
        
        # ★ 只有真正的聊天活动才通知视觉线程
        if is_chat_activity and hasattr(self, 'vision_thread') and self.vision_thread:
            self.vision_thread.on_chat_detected()
        
        # 有互动时解锁表情
        if hasattr(self.l2d, 'expression_mixer'):
            self.l2d.expression_mixer.lock_expression(False)

    def on_idle_timeout(self):
        """待机超时处理"""
        print("💤 触发待机超时逻辑...")
        self.idle_timer.stop()

        has_history = len(self.agent.history) > 0

        if not has_history:
            # 没有聊天记录 - 直接睡觉
            text = "哎呀，闲死本女王了。我要睡觉咯。"
            
            self.chat_log.appendPlainText(f"\n✨ Mili:\n{text}")
            self.chat_log.moveCursor(QTextCursor.End)
            
            # 切换到 sleepy 表情并锁定
            signal_bus.agent_emotion_changed.emit("sleepy")
            self.l2d.expression_mixer.lock_expression(True)
            self.audio_system.add_sentence(text, "idle")
            
        else:
            # 有聊天记录 - 吐槽
            self.handle_stream_response(IDLE_TIMEOUT_PROMPT, is_internal_trigger=True)

    def append_user(self, text: str):
        """添加用户消息到聊天记录"""
        self.chat_log.appendPlainText(f"\n👉 {text}")
        self.chat_log.moveCursor(QTextCursor.End)

    # ==========================================
    # ★★★ 新增：语音输入功能 ★★★
    # ==========================================
    def on_voice_input(self):
        """语音输入按钮点击"""
        if self.is_recording:
            # 正在录音，点击取消
            self.stop_voice_input()
            return
        
        # 开始录音
        self.is_recording = True
        self.mic_btn.setText("⏹")
        self.mic_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 100, 100, 0.5);
                color: #ff4444;
                border: none;
                border-radius: 18px;
                font-size: 16px;
                animation: pulse 1.5s infinite;
            }
        """)
        self.input_field.setPlaceholderText("🎤 正在监听...")
        
        # 创建并启动语音识别线程
        self.voice_thread = VoiceInputThread()
        self.voice_thread.recognized.connect(self.on_voice_recognized)
        self.voice_thread.error.connect(self.on_voice_error)
        self.voice_thread.finished.connect(self.on_voice_finished)
        self.voice_thread.start()
    
    def stop_voice_input(self):
        """停止语音输入"""
        if self.voice_thread and self.voice_thread.isRunning():
            self.voice_thread.cancel()
            self.voice_thread.quit()
            self.voice_thread.wait()
        
        self.is_recording = False
        self.restore_mic_button()
    
    def on_voice_recognized(self, text: str):
        """语音识别成功"""
        print(f"✅ 识别到: {text}")
        self.input_field.setText(text)
        self.input_field.setFocus()
        
        # 自动发送
        self.on_send()
    
    def on_voice_error(self, error_msg: str):
        """语音识别失败"""
        print(f"❌ 识别失败: {error_msg}")
        self.input_field.setPlaceholderText(f"❌ {error_msg}")
        QTimer.singleShot(3000, lambda: self.input_field.setPlaceholderText("Type something..."))
    
    def on_voice_finished(self):
        """语音识别线程结束"""
        self.is_recording = False
        self.restore_mic_button()
    
    def restore_mic_button(self):
        """恢复麦克风按钮状态"""
        self.mic_btn.setText("🎤")
        self.mic_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888;
                border: none;
                border-radius: 15px;
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(0, 0, 0, 0.05);
                color: #667eea;
            }
        """)
        self.input_field.setPlaceholderText("Type something...")
    
    # ==========================================
    # ★★★ 视觉触发功能 ★★★
    # ==========================================
    def trigger_vision_analysis(self):
        """主动触发视觉分析（用户说"看下屏幕"等关键词时）"""
        try:
            # 获取当前历史和记忆
            current_history = list(self.agent.history)
            long_term_memory = self.agent.get_formatted_memory()
            
            # 直接调用 vision sensor 分析（复用原有代码）
            raw_response, model_used = self.vision_thread.sensor.analyze(
                history=current_history,
                long_term_memory=long_term_memory
            )
            
            # 重置视觉检测计时器（关键！避免60秒后重复触发）
            import time
            self.vision_thread.last_scan_time = time.time()
            self.vision_thread.last_chat_time = time.time()
            print("⏰ [Chat] 已重置视觉检测计时器")
            
            if raw_response:
                # 检查是否触发
                if '"should_trigger": false' in raw_response or '"should_trigger":false' in raw_response:
                    print(f"👁️ [Chat] {model_used} 分析完成，但当前内容不值得评论")
                    self.chat_log.appendPlainText("\n✨ Mili:\n嗯...没什么好说的。")
                else:
                    print(f"👁️ [Chat] {model_used} 分析完成，触发回复")
                    # 直接 emit 信号显示（复用原有的视觉回复处理）
                    self.vision_thread.vision_reaction.emit(raw_response)
            else:
                print("❌ [Chat] 视觉分析失败")
                self.chat_log.appendPlainText("\n✨ Mili:\n哎呀，我看不到屏幕...")
        
        except Exception as e:
            print(f"❌ [Chat] 视觉触发失败: {e}")
            import traceback
            traceback.print_exc()
            self.chat_log.appendPlainText("\n✨ Mili:\n出错了...看不了。")
    
    # ==========================================
    # ★★★ 新增：清空聊天记录 ★★★
    # ==========================================
    def on_clear_chat(self):
        """清空聊天记录"""
        # 弹出确认对话框
        reply = QMessageBox.question(
            self, 
            '清空聊天', 
            '确定要清空当前聊天记录吗？\n（不会删除记忆数据库）',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 清空聊天显示
            self.chat_log.clear()
            self.chat_log.setPlaceholderText("Mili 正在聆听...")
            
            # 清空 Agent 历史记录
            self.agent.history.clear()
            
            print("🗑️ 聊天记录已清空")
            
            # 可选：让 Mili 说一句话
            self.chat_log.appendPlainText("\n✨ Mili:\n哼，重新开始吧~")
            self.chat_log.moveCursor(QTextCursor.End)

    def on_send(self):
        """发送按钮点击事件"""
        text = self.input_field.text().strip()
        if not text:
            return
        
        # 重置待机计时器（用户发送消息，算作真正的聊天活动）
        self.reset_idle_timer(is_chat_activity=True)
        
        self.input_field.clear()
        self.append_user(text)
        QApplication.processEvents()
        
        # ★★★ 检测是否是视觉触发关键词 ★★★
        vision_keywords = ["看下屏幕", "看看", "看看我", "看一下", "看下", "截个图", "帮我看看", "你看看"]
        if any(keyword in text for keyword in vision_keywords):
            print(f"\n👁️ [Chat] 检测到视觉触发关键词，直接调用 Gemini 分析...")
            self.trigger_vision_analysis()
            return
        
        # 正常的文字对话
        self.handle_stream_response(text)

    def handle_stream_response(self, text: str, is_internal_trigger: bool = False):
        """
        处理流式响应
        
        Args:
            text: 发送给 AI 的文本
            is_internal_trigger: 是否是内部触发 (如超时)
        """
        punctuations = set(['。', '~', '！', '？', '!', '?', '\n', '…', '……'])
        self.chat_log.appendPlainText("\n✨ Mili:")
        self.chat_log.moveCursor(QTextCursor.End)
        
        current_sentence_buffer = ""
        full_response_log = ""
        pending_motion = None

        try:
            stream_generator = self.agent.chat_stream(text)
            for chunk in stream_generator:
                # 处理状态信息
                if chunk["type"] == "status":
                    status = chunk["status"]
                    if status == "thinking":
                        # Agent 正在思考/调用工具
                        self.chat_log.insertPlainText("(正在查询...)")
                        self.chat_log.moveCursor(QTextCursor.End)
                        QApplication.processEvents()
                        # 可以让 Live2D 做一个思考的表情
                        if hasattr(self.l2d, 'expression_mixer'):
                            signal_bus.agent_emotion_changed.emit("sleepy")
                    elif status == "speaking":
                        # Agent 准备开始说话，清除"正在查询"的提示
                        # 移除最后添加的"(正在查询...)"文本
                        cursor = self.chat_log.textCursor()
                        cursor.movePosition(QTextCursor.End)
                        for _ in range(10):  # 删除 "(正在查询...)"
                            cursor.deletePreviousChar()
                        self.chat_log.setTextCursor(cursor)
                        QApplication.processEvents()
                
                elif chunk["type"] == "meta":
                    meta = chunk["data"]
                    expr_id = meta.get("expression", "smile")
                    if isinstance(expr_id, dict):
                        expr_id = "smile"
                    
                    # 通过信号总线发送表情改变
                    signal_bus.agent_emotion_changed.emit(expr_id)
                    
                    # 如果切换到 sleepy，锁定表情
                    if expr_id == "sleepy":
                        self.l2d.expression_mixer.lock_expression(True)
                    
                    pending_motion = meta.get("motion", "idle")

                elif chunk["type"] == "text":
                    char = chunk["content"]
                    if full_response_log == "" and char in ['}', '\n', ' ']:
                        continue
                        
                    self.chat_log.insertPlainText(char)
                    self.chat_log.moveCursor(QTextCursor.End)
                    QApplication.processEvents()
                    
                    current_sentence_buffer += char
                    full_response_log += char
                    
                    if char in punctuations:
                        clean_text = current_sentence_buffer.strip()
                        if len(clean_text) > 1 or char in ['！', '？', '。', '\n']:
                            self.audio_system.add_sentence(clean_text, pending_motion)
                            pending_motion = None
                            current_sentence_buffer = ""

            # 处理剩余文本
            if current_sentence_buffer.strip():
                self.audio_system.add_sentence(current_sentence_buffer.strip(), pending_motion)

        except Exception as e:
            print(f"Stream Error: {e}")
            import traceback
            traceback.print_exc()
            self.chat_log.appendPlainText(f"\n[Error] {e}")
    
    # ==========================================
    # ★★★ 视觉触发处理（双大脑模式）★★★
    # ==========================================
    def on_vision_reaction(self, raw_text: str):
        """
        当视觉模块（Gemini）生成回复时调用
        
        Args:
            raw_text: Gemini 返回的完整文本 (包含 ###JSON### 和正文)
        """
        print(f"⚡ [UI] 收到视觉回复: {raw_text[:50]}...")
        
        # 在聊天记录中显示提示
        self.chat_log.appendPlainText("\n(Mili 瞥了一眼你的屏幕...)")
        self.chat_log.moveCursor(QTextCursor.End)
        
        # 显示 Mili 的回复标记
        self.chat_log.appendPlainText("\n✨ Mili:")
        self.chat_log.moveCursor(QTextCursor.End)
        
        # 使用 agent 的视觉回复处理流
        punctuations = set(['。', '~', '！', '？', '!', '?', '\n', '…', '……'])
        current_sentence_buffer = ""
        pending_motion = None
        full_text = ""  # 用于气泡模式下收集完整文本
        
        try:
            stream_generator = self.agent.handle_vision_response_stream(raw_text)
            
            for chunk in stream_generator:
                if chunk["type"] == "meta":
                    meta = chunk["data"]
                    expr_id = meta.get("expression", "smile")
                    if isinstance(expr_id, dict):
                        expr_id = "smile"
                    
                    # 通过信号总线发送表情改变
                    signal_bus.agent_emotion_changed.emit(expr_id)
                    
                    # 如果切换到 sleepy，锁定表情
                    if expr_id == "sleepy":
                        self.l2d.expression_mixer.lock_expression(True)
                    
                    pending_motion = meta.get("motion", "idle")
                
                elif chunk["type"] == "text":
                    char = chunk["content"]
                    
                    self.chat_log.insertPlainText(char)
                    self.chat_log.moveCursor(QTextCursor.End)
                    QApplication.processEvents()
                    
                    current_sentence_buffer += char
                    full_text += char  # 收集完整文本
                    
                    # 语音模式：按句子播放
                    if VISION_USE_VOICE:
                        if char in punctuations:
                            clean_text = current_sentence_buffer.strip()
                            if len(clean_text) > 1 or char in ['！', '？', '。', '\n']:
                                self.audio_system.add_sentence(clean_text, pending_motion)
                                pending_motion = None
                                current_sentence_buffer = ""
            
            # 语音模式：处理剩余文本
            if VISION_USE_VOICE:
                if current_sentence_buffer.strip():
                    self.audio_system.add_sentence(current_sentence_buffer.strip(), pending_motion)
            else:
                # 气泡模式：播完整文本
                clean_full_text = full_text.strip()
                if clean_full_text:
                    # 通过信号发送气泡消息
                    signal_bus.show_bubble_message.emit(clean_full_text)
                    
                    # 如果有动作，触发动作
                    if pending_motion:
                        signal_bus.agent_motion_triggered.emit(pending_motion)
        
        except Exception as e:
            print(f"❌ [UI] 视觉回复处理错误: {e}")
            import traceback
            traceback.print_exc()
        
        # 重置待机计时器（收到回复，算作真正的聊天活动）
        self.reset_idle_timer(is_chat_activity=True)
    
    def closeEvent(self, event):
        """窗口关闭时停止视觉线程和语音识别"""
        if hasattr(self, 'vision_thread') and self.vision_thread:
            print("👁️ 正在停止视觉感知系统...")
            self.vision_thread.stop()
        
        # 停止语音识别
        if self.is_recording and self.voice_thread:
            self.voice_thread.cancel()
            self.voice_thread.quit()
            self.voice_thread.wait()
        
        event.accept()
