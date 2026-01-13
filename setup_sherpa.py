# -*- coding: utf-8 -*-
"""
SenseVoice (Sherpa-ONNX) 语音识别设置脚本
自动检查和下载 SenseVoice 模型（如果缺失）
"""

import os
import sys
import subprocess
import urllib.request
import tarfile
from pathlib import Path

# 强制使用 UTF-8 编码输出 (解决 Windows 控制台乱码)
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

print("="*60)
print("SenseVoice 离线语音识别 - 自动设置")
print("="*60)

# 获取项目根目录
ROOT_DIR = Path(__file__).parent
# 定义模型存放目录 (解压后的文件夹名)
MODEL_FOLDER_NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
model_dir = ROOT_DIR / "model" / MODEL_FOLDER_NAME

# ============================================
# 1. 检查并安装依赖
# ============================================
print("\n📦 步骤 1: 检查依赖包...")

required_packages = [
    "sherpa-onnx==1.12.20",  # 指定版本以确保兼容性
    "onnxruntime",
    "numpy",
]

missing_packages = []
for package in required_packages:
    # 提取包名（去掉版本号）用于 import 检查
    package_name = package.split('==')[0].split('>=')[0].replace("-", "_")
    try:
        __import__(package_name)
        print(f"  ✅ {package} 已安装")
    except ImportError:
        print(f"  ❌ {package} 未安装")
        missing_packages.append(package)

if missing_packages:
    print(f"\n⚠️  缺少依赖: {', '.join(missing_packages)}")
    print("正在安装...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_packages)
        print("✅ 依赖安装成功")
    except subprocess.CalledProcessError as e:
        print(f"❌ 依赖安装失败: {e}")
        sys.exit(1)
else:
    print("✅ 所有依赖已安装")

# ============================================
# 2. 检查并自动下载 SenseVoice 模型
# ============================================
print("\n📂 步骤 2: 检查 SenseVoice 模型...")

# 关键文件路径
model_file = model_dir / "model.int8.onnx"
tokens_file = model_dir / "tokens.txt"

# 下载配置
tar_filename = f"{MODEL_FOLDER_NAME}.tar.bz2"
download_url = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{tar_filename}"
tar_save_path = ROOT_DIR / "model" / tar_filename

if model_file.exists() and tokens_file.exists():
    print(f"✅ SenseVoice 模型已就绪")
else:
    print(f"⚠️  模型缺失，准备自动下载...")
    
    # 确保 model 目录存在
    (ROOT_DIR / "model").mkdir(exist_ok=True)

    try:
        # 定义进度条回调
        def show_progress(block_num, block_size, total_size):
            downloaded = block_num * block_size
            if total_size > 0:
                percent = 100 * downloaded / total_size
                if percent > 100: percent = 100
                print(f"\r  ⬇️ 下载进度: {percent:.1f}% ({downloaded/1024/1024:.1f} MB)", end="")

        print(f"  🔗 地址: {download_url}")
        if tar_save_path.exists():
             print(f"\n  ⚠️ 检测到已下载的压缩包，尝试直接解压...")
        else:
             print("  ⏳ 开始下载 (约 120MB)，请保持网络通畅...")
             # 1. 下载
             urllib.request.urlretrieve(download_url, tar_save_path, reporthook=show_progress)
             print(f"\n  ✅ 下载完成")

        # 2. 解压
        print(f"  📦 正在解压...")
        if not tarfile.is_tarfile(tar_save_path):
             raise Exception("下载的文件不是有效的 tar 压缩包")

        with tarfile.open(tar_save_path, "r:bz2") as tar:
            tar.extractall(path=ROOT_DIR / "model")
        print(f"  ✅ 解压完成")

        # 3. 清理压缩包
        print(f"  🧹 清理临时文件...")
        try:
            os.remove(tar_save_path)
        except:
            pass

    except Exception as e:
        print(f"\n❌ 自动下载/解压失败: {e}")
        print(f"💡 建议手动下载: {download_url}")
        print(f"💡 解压到: {ROOT_DIR / 'model'}")

# ============================================
# 3. 检查 Silero VAD 模型
# ============================================
print("\n📂 步骤 3: 检查 Silero VAD 模型...")

vad_model_file = ROOT_DIR / "model" / "silero_vad.onnx"

if vad_model_file.exists():
    print(f"✅ Silero VAD 模型已存在")
else:
    print(f"⚠️  未找到 Silero VAD 模型，正在下载...")
    try:
        (ROOT_DIR / "model").mkdir(parents=True, exist_ok=True)
        url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"
        urllib.request.urlretrieve(url, vad_model_file)
        print(f"✅ Silero VAD 模型下载成功")
    except Exception as e:
        print(f"❌ Silero VAD 下载失败: {e}")

# ============================================
# 4. 测试模型加载
# ============================================
if model_file.exists() and tokens_file.exists() and vad_model_file.exists():
    print("\n🧪 步骤 4: 测试模型加载...")
    try:
        import sherpa_onnx
        
        # 测试 SenseVoice
        # 正确的 API: sherpa_onnx.offline_recognizer.OfflineRecognizer
        recognizer = sherpa_onnx.offline_recognizer.OfflineRecognizer.from_sense_voice(
            model=str(model_file),
            tokens=str(tokens_file),
            language="auto",
            use_itn=True,
            num_threads=4,
            provider="cpu",
        )
        print(f"✅ sherpa-onnx 版本: {sherpa_onnx.__version__}")
        print(f"✅ SenseVoice 模型加载成功")
        
        # 测试 Silero VAD
        vad_config = sherpa_onnx.VadModelConfig()
        vad_config.silero_vad.model = str(vad_model_file)
        vad_config.sample_rate = 16000
        vad_config.silero_vad.threshold = 0.5
        vad_config.silero_vad.min_silence_duration = 0.5
        vad_config.silero_vad.min_speech_duration = 0.25
        
        vad = sherpa_onnx.VoiceActivityDetector(
            vad_config,
            60
        )
        print(f"✅ Silero VAD 模型加载成功")
        print(f"✅ 支持语言: 中文、英文、日语、韩语、粤语")
        
        print("\n" + "="*60)
        print("✅ 所有设置完成! 随时可以启动 MiliChat。")
        print("="*60)
        
    except Exception as e:
        print(f"❌ 模型加载测试失败: {e}")
        import traceback
        traceback.print_exc()
else:
    print("\n❌ 错误: 部分模型文件缺失，无法通过测试。")
    print("请检查上方报错信息并重试。")