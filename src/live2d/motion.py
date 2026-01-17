"""Live2D 动作引擎 - 表情、身体和手势控制"""
import json
import math
import os
import time

from src.core.config import (
    LIVE2D_EXPRESSIONS_DIR, 
    EXPRESSION_FILE_MAPPING,
    EXPRESSION_RESET_TIMEOUT
)


class ExpressionMixer:
    """表情混音器 - 自动加载和混合表情"""
    
    def __init__(self):
        self.presets = {}  # 表情预设 {logic_id: {param_id: value}}
        self.file_mapping = EXPRESSION_FILE_MAPPING
        
        # 运行时状态
        self.target_params = {}      # 目标参数值
        self.current_params = {}     # 当前参数值 (插值用)
        self.last_interaction_time = time.time()
        self.idle_timeout = EXPRESSION_RESET_TIMEOUT
        self.is_resetting = False
        
        # 表情锁定标志 (用于休眠等特殊状态)
        self.expression_locked = False

        # 基础参数 (Neutral Face)
        self.base_params = {
            "ParamEyeLOpen": 1.0, "ParamEyeROpen": 1.0,
            "ParamEyeLSmile": 0.0, "ParamEyeRSmile": 0.0,
            "ParamEyeBallForm": 0.0, "ParamCheek": 0.0,
            "ParamBrowLAngle": 0.0, "ParamBrowRAngle": 0.0,
            "ParamBrowLY": 0.0, "ParamBrowRY": 0.0,
            "ParamMouthUp": 0.0, "ParamMouthAngry": 0.0,
            "ParamMouthOpenY": 0.0, "ParamMouthForm": 0.0
        }
        
        # 加载表情文件
        self.load_expressions_from_disk()
        
        # 初始化默认表情
        self.set_expression("smile")

    def load_expressions_from_disk(self):
        """扫描并解析 .exp3.json 文件"""
        exp_dir = LIVE2D_EXPRESSIONS_DIR
        
        if not os.path.exists(exp_dir):
            print(f"⚠️ 警告: 表情文件夹未找到: {exp_dir}")
            return

        print(f"📂 开始加载表情文件: {exp_dir}")
        
        for file_name, logic_id in self.file_mapping.items():
            file_path = os.path.join(exp_dir, file_name)
            
            if not os.path.exists(file_path):
                print(f"  ❌ 缺失文件: {file_name} (对应 {logic_id})")
                self.presets[logic_id] = {}
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # 解析 Live2D exp3 格式
                    params = {}
                    if "Parameters" in data:
                        for p in data["Parameters"]:
                            p_id = p.get("Id")
                            p_val = p.get("Value", 0.0)
                            if p_id:
                                params[p_id] = float(p_val)
                    
                    self.presets[logic_id] = params
                    print(f"  ✅ 已加载: {logic_id} <- {file_name} ({len(params)} 参数)")
                    
            except Exception as e:
                print(f"  ❌ 解析失败 {file_name}: {e}")
                self.presets[logic_id] = {}

    def refresh_timer(self):
        """刷新计时器 (有互动时调用)"""
        self.last_interaction_time = time.time()
        self.is_resetting = False
    
    def lock_expression(self, locked: bool = True):
        """锁定或解锁表情 (防止自动重置)"""
        self.expression_locked = locked
        if locked:
            print("🔒 表情已锁定，不会自动重置")
        else:
            print("🔓 表情已解锁")

    def set_emotion_weight(self, emotion_weights: dict):
        """
        设置混合情绪权重
        
        Args:
            emotion_weights: 情绪权重字典, e.g. {"smile": 0.6, "surprise": 0.4}
        """
        self.refresh_timer()
        
        # 1. 从基础脸开始
        final_targets = self.base_params.copy()
        
        # 2. 遍历情绪，累加加权偏移
        for emotion_id, weight in emotion_weights.items():
            try:
                weight = float(weight)
            except (TypeError, ValueError):
                continue
            if weight == 0:
                continue
            preset = self.presets.get(emotion_id, {})
            
            for param_id, target_val in preset.items():
                if param_id not in final_targets:
                    final_targets[param_id] = 0.0
                
                base_val = self.base_params.get(param_id, 0.0)
                diff = (target_val - base_val) * weight
                final_targets[param_id] += diff

        self.target_params = final_targets
        print(f"🎨 情绪混合: {emotion_weights}")

    def set_expression(self, expression_id: str):
        """
        切换表情 (兼容旧方法)
        
        Args:
            expression_id: 表情逻辑ID (smile, happy, sleepy, etc.)
        """
        print(f"🎭 切换表情: {expression_id}")
        self.set_emotion_weight({expression_id: 1.0})

    def update_model(self, model):
        """
        更新模型参数 (每帧调用)
        
        Args:
            model: Live2D 模型对象
        """
        if not model:
            return
        
        # 超时归位 (只有在表情未锁定时才执行)
        if (not self.expression_locked and 
            not self.is_resetting and 
            (time.time() - self.last_interaction_time > self.idle_timeout)):
            self.set_expression("smile")
            self.is_resetting = True

        # 插值平滑
        smoothing = 0.1
        for param_id, target_val in self.target_params.items():
            current_val = self.current_params.get(param_id, target_val)
            next_val = current_val + (target_val - current_val) * smoothing
            self.current_params[param_id] = next_val
            
            model.SetParameterValue(param_id, next_val, 0.8)


class BodyMotionEngine:
    """身体动作引擎 - 呼吸和语音驱动"""
    
    def __init__(self):
        self.start_time = time.time()
        
        # 参数
        self.breath_scale = 0.5
        self.speech_scale = 5.0
        
        # 平滑变量
        self.current_body_x = 0.0
        self.current_head_x = 0.0
        self.smoothed_audio_level = 0.0

    def update_model(self, model, audio_level: float):
        """
        更新身体动作 (每帧调用)
        
        Args:
            model: Live2D 模型对象
            audio_level: 当前音量级别 (0.0 - 1.0)
        """
        if not model:
            return

        t = time.time() - self.start_time
        
        # 音量平滑处理
        self.smoothed_audio_level += (audio_level - self.smoothed_audio_level) * 0.1
        level = self.smoothed_audio_level

        # 1. 基础呼吸律动
        idle_sway_x = math.sin(t * 1.5) * 2.0 
        idle_sway_z = math.sin(t * 1.2) * 1.5 
        
        # 2. 语音驱动
        target_body_x = idle_sway_x + (level * 1.5)
        target_head_x = math.sin(t * 2.0) * 1.0 - (level * self.speech_scale)
        target_head_z = idle_sway_z

        # 3. 动作平滑
        smoothing_factor = 0.05
        self.current_body_x += (target_body_x - self.current_body_x) * smoothing_factor
        self.current_head_x += (target_head_x - self.current_head_x) * smoothing_factor
        
        # 4. 应用参数
        model.SetParameterValue("ParamBodyAngleX", self.current_body_x, 0.5)
        model.SetParameterValue("ParamAngleX", self.current_head_x, 0.5)
        model.SetParameterValue("ParamAngleZ", target_head_z, 0.5)
        
        # 呼吸
        breath_val = (math.sin(t * 2.5) + 1.0) / 2.0
        model.SetParameterValue("ParamBreath", breath_val, 0.8)


class GestureEngine:
    """手势引擎 - 右手魔杖动作"""
    
    def __init__(self):
        self.start_time = time.time()
        
        self.current_wand_activity = 0.0
        self.smoothed_input_audio = 0.0
        
        # 摆动幅度系数
        self.wand_scale = 15.0

    def update_model(self, model, audio_level: float):
        """
        更新手势动作 (每帧调用)
        
        Args:
            model: Live2D 模型对象
            audio_level: 当前音量级别 (0.0 - 1.0)
        """
        if not model:
            return
        
        t = time.time() - self.start_time
        
        # 1. 输入信号平滑
        self.smoothed_input_audio += (audio_level - self.smoothed_input_audio) * 0.2
        
        # 噪音门限
        effective_audio = 0.0
        if self.smoothed_input_audio > 0.05:
            effective_audio = self.smoothed_input_audio
        
        # 2. 右手逻辑 (非对称平滑)
        target_wand_activity = effective_audio * self.wand_scale
        
        # 关键修复：Attack/Decay 不对称
        if target_wand_activity > self.current_wand_activity:
            # 兴奋阶段 - 快速跟上
            smoothing = 0.1
        else:
            # 衰减阶段 - 极慢回落 (保持惯性)
            smoothing = 0.01
            
        self.current_wand_activity += (target_wand_activity - self.current_wand_activity) * smoothing
        
        # 计算最终角度
        base_wand = math.sin(t * 1.5) * 2.0  # 待机微动
        speak_wand = math.sin(t * 2.5) * self.current_wand_activity  # 说话挥舞
        final_wand = base_wand + speak_wand
        
        # 应用参数
        model.SetParameterValue("ParamWandRotate", final_wand, 0.5)
        
        # 右臂联动
        right_arm_angle = self.current_wand_activity * 0.5
        model.SetParameterValue("ParamArmRA01", right_arm_angle, 0.5)
        model.SetParameterValue("ParamArmRB01", right_arm_angle, 0.5)
