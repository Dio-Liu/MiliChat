"""音频系统 - TTS 生成和播放"""
import asyncio
import os
import queue
import tempfile
import threading

import edge_tts
import numpy as np
import sounddevice as sd
import soundfile as sf
from PySide6.QtCore import QObject

from src.core.config import (
    TTS_VOICE, TTS_RATE, TTS_PITCH,
    AUDIO_BLOCK_SIZE, LIP_SYNC_SCALE, LIP_SYNC_MAX
)
from src.core.signals import signal_bus


class AudioSystem(QObject):
    """
    音频系统 - 双线程架构
    - 生成线程：异步生成 TTS 音频文件
    - 播放线程：播放音频并发送口型同步信号
    """
    
    def __init__(self):
        super().__init__()
        
        # TTS 配置
        self.voice = TTS_VOICE
        self.rate = TTS_RATE
        self.pitch = TTS_PITCH
        
        # 两个队列
        self.text_queue = queue.Queue()       # 存放待生成的 (文本, 动作)
        self.audio_file_queue = queue.Queue() # 存放已生成的 (音频路径, 动作)
        
        self.is_running = True

        # 启动生成线程
        self.gen_thread = threading.Thread(target=self._generation_loop, daemon=True)
        self.gen_thread.start()

        # 启动播放线程
        self.play_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.play_thread.start()

    def add_sentence(self, text: str, motion_name: str = None):
        """
        添加句子和对应的动作到生成队列
        
        Args:
            text: 要转换为语音的文本
            motion_name: 对应的动作名称 (wave, nod, happy, etc.)
        """
        if text.strip():
            self.text_queue.put((text, motion_name))

    def stop(self):
        """停止音频系统"""
        self.is_running = False

    # ============================================
    # 线程 1: 生成音频
    # ============================================
    def _generation_loop(self):
        """生成线程 - 持续从文本队列中取出并生成音频"""
        while self.is_running:
            try:
                # 解包：取出 (文字, 动作)
                text, motion = self.text_queue.get(timeout=1)
                
                # 生成音频 (耗时操作)
                audio_path = self._generate_tts_sync(text)
                
                if audio_path:
                    # 生成完成，传给播放队列
                    self.audio_file_queue.put((audio_path, motion))
                
                self.text_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ 生成错误: {e}")

    # ============================================
    # 线程 2: 播放音频
    # ============================================
    def _playback_loop(self):
        """播放线程 - 持续从音频队列中取出并播放"""
        while self.is_running:
            try:
                # 解包：取出 (路径, 动作)
                audio_path, motion = self.audio_file_queue.get(timeout=1)
                
                # ★★★ 播放前触发动作信号 ★★★
                if motion and motion != "idle":
                    print(f"⚡ 播放线程触发动作: {motion}")
                    signal_bus.agent_motion_triggered.emit(motion)

                # 播放音频并发送口型同步信号
                self._play_audio_file(audio_path)
                
                # 播完删除临时文件
                try:
                    os.remove(audio_path)
                except:
                    pass
                
                self.audio_file_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ 播放错误: {e}")

    # ============================================
    # 辅助函数
    # ============================================
    def _generate_tts_sync(self, text: str) -> str:
        """
        同步包装异步的 edge-tts
        
        Args:
            text: 要生成的文本
            
        Returns:
            生成的音频文件路径
        """
        async def _gen():
            communicate = edge_tts.Communicate(
                text, 
                self.voice, 
                rate=self.rate, 
                pitch=self.pitch
            )
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                await communicate.save(tmp.name)
                return tmp.name
        
        try:
            return asyncio.run(_gen())
        except Exception as e:
            print(f"TTS Error: {e}")
            return None

    def _play_audio_file(self, file_path: str):
        """
        使用 SoundDevice 播放音频并发送口型同步信号
        
        Args:
            file_path: 音频文件路径
        """
        try:
            data, fs = sf.read(file_path, dtype='float32')
            block_size = AUDIO_BLOCK_SIZE
            current_pos = 0
            channels = data.shape[1] if len(data.shape) > 1 else 1

            with sd.OutputStream(samplerate=fs, channels=channels) as stream:
                while current_pos < len(data):
                    if not self.is_running:
                        break
                    
                    chunk = data[current_pos : current_pos + block_size]
                    current_pos += block_size
                    
                    if len(chunk) == 0:
                        break
                    
                    # 计算口型值 (RMS)
                    rms = np.sqrt(np.mean(chunk**2))
                    lip_value = min(rms * LIP_SYNC_SCALE, LIP_SYNC_MAX)
                    
                    # 发送信号
                    signal_bus.lip_sync_value.emit(lip_value)
                    
                    # 播放音频块
                    stream.write(chunk)
            
            # 这一句播完，闭嘴
            signal_bus.lip_sync_value.emit(0.0)
            
        except Exception as e:
            print(f"Play Error: {e}")
