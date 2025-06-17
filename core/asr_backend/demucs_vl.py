# ------------
# 本模块用于音频分离，调用Demucs模型将音频分离为人声和背景音乐
# ------------
import os
import torch
from rich.console import Console
from rich import print as rprint
from demucs.pretrained import get_model
from demucs.audio import save_audio
from torch.cuda import is_available as is_cuda_available
from typing import Optional
from demucs.api import Separator
from demucs.apply import BagOfModels
import gc
from core.utils.models import *

# ------------
# 预加载分离器，支持多设备
# ------------
class PreloadedSeparator(Separator):
    def __init__(self, model, shifts = 1, overlap = 0.25,
                 split = True, segment = None, jobs = 0):
        # 直接使用已加载的模型，自动选择设备
        self._model, self._audio_channels, self._samplerate = model, model.audio_channels, model.samplerate
        device = "cuda" if is_cuda_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        self.update_parameter(device=device, shifts=shifts, overlap=overlap, split=split,
                            segment=segment, jobs=jobs, progress=True, callback=None, callback_arg=None)

# ------------
# Demucs音频分离主流程
# ------------
def demucs_audio():
    # 如果已存在分离结果则跳过
    if os.path.exists(_VOCAL_AUDIO_FILE) and os.path.exists(_BACKGROUND_AUDIO_FILE):
        rprint(f"[yellow]⚠️ {_VOCAL_AUDIO_FILE} 和 {_BACKGROUND_AUDIO_FILE} 已存在，跳过Demucs处理。[/yellow]")
        return
    console = Console()
    os.makedirs(_AUDIO_DIR, exist_ok=True)
    # 加载Demucs模型
    console.print("🤖 正在加载 <htdemucs> 模型...")
    model = get_model('htdemucs')
    separator = PreloadedSeparator(model=model, shifts=1, overlap=0.25)
    # 分离音频
    console.print("🎵 正在分离音频...")
    _, outputs = separator.separate_audio_file(_RAW_AUDIO_FILE)
    # 保存人声
    kwargs = {"samplerate": model.samplerate, "bitrate": 128, "preset": 2, 
             "clip": "rescale", "as_float": False, "bits_per_sample": 16}
    console.print("🎤 正在保存人声轨道...")
    save_audio(outputs['vocals'].cpu(), _VOCAL_AUDIO_FILE, **kwargs)
    # 保存背景音乐
    console.print("🎹 正在保存背景音乐...")
    background = sum(audio for source, audio in outputs.items() if source != 'vocals')
    save_audio(background.cpu(), _BACKGROUND_AUDIO_FILE, **kwargs)
    # 清理内存
    del outputs, background, model, separator
    gc.collect()
    console.print("[green]✨ 音频分离完成！[/green]")

if __name__ == "__main__":
    # ------------
    # 测试主程序，直接分离_RAW_AUDIO_FILE
    # ------------
    demucs_audio()
