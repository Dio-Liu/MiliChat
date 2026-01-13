"""语音输入模块 - 使用 SenseVoice (Sherpa-ONNX) + VAD 实现低延迟语音识别"""
import os
import time
import numpy as np
import sounddevice as sd
from PySide6.QtCore import QThread, Signal

from src.core.config import ROOT_DIR


class VoiceInputThread(QThread):
    """语音识别线程 - 使用 SenseVoice + Sherpa VAD（低延迟流式识别）"""
    
    # 信号
    recognized = Signal(str)  # 识别成功，发送文本
    error = Signal(str)  # 识别失败，发送错误信息
    listening = Signal()  # 开始监听
    
    # 类变量：单例加载模型（避免重复加载）
    _recognizer = None
    _vad = None
    _models_loaded = False
    
    def __init__(self):
        super().__init__()
        self.is_cancelled = False
        self.audio_buffer = []  # 音频缓冲区
        self.sample_rate = 16000  # 采样率
        
        # ★★★ 加载离线模型（仅首次加载） ★★★
        if not VoiceInputThread._models_loaded:
            self._load_models()
    
    @staticmethod
    def _load_models():
        """单例加载 SenseVoice 和 VAD 模型"""
        model_dir = os.path.join(ROOT_DIR, "model", "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17")
        model_file = os.path.join(model_dir, "model.int8.onnx")
        tokens_file = os.path.join(model_dir, "tokens.txt")
        
        if not os.path.exists(model_file):
            print(f"❌ [Voice] 未找到 SenseVoice 模型: {model_file}")
            print("❌ [Voice] 请确保已下载模型到 model/ 目录")
            print("❌ [Voice] 运行 'python setup_sherpa.py' 查看模型状态")
            VoiceInputThread._recognizer = None
            VoiceInputThread._vad = None
            VoiceInputThread._models_loaded = True
            return
        
        try:
            print(f"🔄 [Voice] 正在加载 SenseVoice + VAD 模型...")
            
            # 导入 sherpa_onnx
            import sherpa_onnx
            
            # 1. 加载 SenseVoice 识别器
            VoiceInputThread._recognizer = sherpa_onnx.offline_recognizer.OfflineRecognizer.from_sense_voice(
                model=model_file,
                tokens=tokens_file,
                language="auto",  # 自动检测语言（zh/en/ja/ko/yue）
                use_itn=True,     # 启用反向文本归一化
                num_threads=4,
                provider="cpu",
            )
            print(f"✅ [Voice] SenseVoice 模型加载成功")
            
            # 2. 加载 Silero VAD（Sherpa-ONNX 内置）
            vad_config = sherpa_onnx.VadModelConfig()
            vad_config.silero_vad.model = os.path.join(ROOT_DIR, "model", "silero_vad.onnx")
            vad_config.sample_rate = 16000
            vad_config.silero_vad.threshold = 0.5  # 语音检测阈值
            vad_config.silero_vad.min_silence_duration = 0.5  # 最短静音时长（秒）
            vad_config.silero_vad.min_speech_duration = 0.25  # 最短语音时长（秒）
            VoiceInputThread._vad = sherpa_onnx.VoiceActivityDetector(
                vad_config, 
                buffer_size_in_seconds=30  # 缓冲区大小（秒）
            )
            print(f"✅ [Voice] Silero VAD 模型加载成功")
            VoiceInputThread._models_loaded = True
            
        except Exception as e:
            print(f"❌ [Voice] 模型加载失败: {e}")
            import traceback
            traceback.print_exc()
            VoiceInputThread._recognizer = None
            VoiceInputThread._vad = None
            VoiceInputThread._models_loaded = True
    
    def run(self):
        """主线程：实时语音监听和识别"""
        if not VoiceInputThread._recognizer or not VoiceInputThread._vad:
            self.error.emit("❌ 语音模型未加载，请运行 setup_sherpa.py")
            return

        try:
            self.is_cancelled = False
            self.audio_buffer = []
            start_time = time.time()
            timeout = 10.0  # 超时时间（秒）
            has_speech = False  # 是否检测到语音
            
            self.listening.emit()
            print("🎤 [Voice] 正在监听 (流式 VAD 模式，低延迟)...")
            
            # 定义音频回调函数
            def audio_callback(indata, frames, time_info, status):
                if status:
                    print(f"⚠️  [Voice] 音频状态: {status}")
                
                if self.is_cancelled:
                    raise sd.CallbackStop()
                
                # 将音频数据转为 float32 并归一化
                samples = indata[:, 0].astype(np.float32)
                
                # 喂给 VAD 进行实时检测
                VoiceInputThread._vad.accept_waveform(samples)
                
                # 将音频数据加入缓冲区（用于识别）
                self.audio_buffer.append(samples)
            
            # 启动音频流
            with sd.InputStream(
                channels=1,
                samplerate=self.sample_rate,
                callback=audio_callback,
                blocksize=512,  # 每次回调处理 512 个采样点（约 32ms）
                dtype=np.float32
            ):
                while not self.is_cancelled:
                    # 检查是否超时
                    if time.time() - start_time > timeout:
                        if not has_speech:
                            self.error.emit("未检测到语音，请大声一点")
                            return
                        else:
                            # 有语音但超时，强制结束
                            break
                    
                    # 检查 VAD 是否检测到语音活动
                    if VoiceInputThread._vad.is_speech_detected():
                        has_speech = True
                    
                    # ★★★ 关键：检测是否有语音段在队列中 ★★★
                    if has_speech and not VoiceInputThread._vad.empty():
                        print("🔄 [Voice] VAD 检测到语音段，开始识别...")
                        break
                    
                    # 短暂休眠，避免 CPU 占用过高
                    time.sleep(0.05)  # 50ms
            
            # 检查是否被取消
            if self.is_cancelled:
                print("🛑 [Voice] 识别已取消")
                return
            
            # 如果没有检测到语音
            if not has_speech or len(self.audio_buffer) == 0:
                self.error.emit("未检测到有效语音")
                return
            
            # ★★★ 提取 VAD 检测到的语音段并识别 ★★★
            # VAD 会将检测到的语音段放入队列
            while not VoiceInputThread._vad.empty():
                segment = VoiceInputThread._vad.front
                samples = segment.samples
                VoiceInputThread._vad.pop()
                
                # 使用 SenseVoice 识别该段语音
                stream = VoiceInputThread._recognizer.create_stream()
                stream.accept_waveform(self.sample_rate, samples)
                VoiceInputThread._recognizer.decode_stream(stream)
                
                result = stream.result.text.strip()
                text = result.replace(" ", "")  # 移除空格
                
                if text:
                    print(f"✅ [Voice] 识别结果: {text}")
                    self.recognized.emit(text)
                    return
            
            # 如果 VAD 队列为空，使用完整音频缓冲区
            if len(self.audio_buffer) > 0:
                audio_data = np.concatenate(self.audio_buffer)
                stream = VoiceInputThread._recognizer.create_stream()
                stream.accept_waveform(self.sample_rate, audio_data)
                VoiceInputThread._recognizer.decode_stream(stream)
                
                result = stream.result.text.strip()
                text = result.replace(" ", "")  # 移除空格
                
                if text:
                    print(f"✅ [Voice] 识别结果: {text}")
                    self.recognized.emit(text)
                else:
                    self.error.emit("未检测到有效语音")
            else:
                self.error.emit("未检测到有效语音")
                
        except Exception as e:
            print(f"❌ [Voice] 语音识别错误: {e}")
            import traceback
            traceback.print_exc()
            self.error.emit("语音识别服务出错")
    
    def cancel(self):
        """取消识别"""
        self.is_cancelled = True
        print("🛑 [Voice] 用户取消识别")
