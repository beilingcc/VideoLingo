# ------------
# 本模块用于本地WhisperX模型的加载、推理和对齐，支持自动选择HuggingFace镜像
# ------------
import os
import warnings
import time
import subprocess
import torch
import whisperx
import librosa
from rich import print as rprint
from core.utils import *

# 忽略警告
warnings.filterwarnings("ignore")
# 模型存储目录
MODEL_DIR = load_key("model_dir")

# ------------
# 检查HuggingFace镜像速度，自动选择最快的镜像
# ------------
@except_handler("failed to check hf mirror", default_return=None)
def check_hf_mirror():
    mirrors = {'Official': 'huggingface.co', 'Mirror': 'hf-mirror.com'}
    fastest_url = f"https://{mirrors['Official']}"
    best_time = float('inf')
    rprint("[cyan]🔍 正在检测HuggingFace镜像...[/cyan]")
    for name, domain in mirrors.items():
        if os.name == 'nt':
            cmd = ['ping', '-n', '1', '-w', '3000', domain]
        else:
            cmd = ['ping', '-c', '1', '-W', '3', domain]
        start = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True)
        response_time = time.time() - start
        if result.returncode == 0:
            if response_time < best_time:
                best_time = response_time
                fastest_url = f"https://{domain}"
            rprint(f"[green]✓ {name}:[/green] {response_time:.2f}s")
    if best_time == float('inf'):
        rprint("[yellow]⚠️ 所有镜像检测失败，使用默认[/yellow]")
    rprint(f"[cyan]🚀 选用镜像:[/cyan] {fastest_url} ({best_time:.2f}s)")
    return fastest_url

# ------------
# 本地WhisperX推理与对齐主流程
# ------------
@except_handler("WhisperX processing error:")
def transcribe_audio(raw_audio_file, vocal_audio_file, start, end):
    # 设置HuggingFace镜像
    os.environ['HF_ENDPOINT'] = check_hf_mirror()
    WHISPER_LANGUAGE = load_key("whisper.language")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    rprint(f"🚀 启动WhisperX，设备: {device} ...")
    # 根据显存自动调整batch size和计算类型
    if device == "cuda":
        gpu_mem = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        batch_size = 16 if gpu_mem > 8 else 2
        compute_type = "float16" if torch.cuda.is_bf16_supported() else "int8"
        rprint(f"[cyan]🎮 GPU显存:[/cyan] {gpu_mem:.2f} GB, [cyan]📦 Batch size:[/cyan] {batch_size}, [cyan]⚙️ 计算类型:[/cyan] {compute_type}")
    else:
        batch_size = 1
        compute_type = "int8"
        rprint(f"[cyan]📦 Batch size:[/cyan] {batch_size}, [cyan]⚙️ 计算类型:[/cyan] {compute_type}")
    rprint(f"[green]▶️ 开始WhisperX转录 {start:.2f}s 到 {end:.2f}s...[/green]")
    # 选择模型
    if WHISPER_LANGUAGE == 'zh':
        model_name = "Huan69/Belle-whisper-large-v3-zh-punct-fasterwhisper"
        local_model = os.path.join(MODEL_DIR, "Belle-whisper-large-v3-zh-punct-fasterwhisper")
    else:
        model_name = load_key("whisper.model")
        local_model = os.path.join(MODEL_DIR, model_name)
    if os.path.exists(local_model):
        rprint(f"[green]📥 加载本地WHISPER模型:[/green] {local_model} ...")
        model_name = local_model
    else:
        rprint(f"[green]📥 使用HuggingFace模型:[/green] {model_name} ...")
    # VAD和ASR参数
    vad_options = {"vad_onset": 0.500,"vad_offset": 0.363}
    asr_options = {"temperatures": [0],"initial_prompt": "",}
    whisper_language = None if 'auto' in WHISPER_LANGUAGE else WHISPER_LANGUAGE
    rprint("[bold yellow] 可忽略`Model was trained with torch...`警告[/bold yellow]")
    # 加载模型
    model = whisperx.load_model(model_name, device, compute_type=compute_type, language=whisper_language, vad_options=vad_options, asr_options=asr_options, download_root=MODEL_DIR)
    # 加载音频片段
    def load_audio_segment(audio_file, start, end):
        audio, _ = librosa.load(audio_file, sr=16000, offset=start, duration=end - start, mono=True)
        return audio
    raw_audio_segment = load_audio_segment(raw_audio_file, start, end)
    vocal_audio_segment = load_audio_segment(vocal_audio_file, start, end)
    # ------------
    # 1. 转录原始音频
    # ------------
    transcribe_start_time = time.time()
    rprint("[bold green]提示: 若正常工作会显示进度条↓[/bold green]")
    result = model.transcribe(raw_audio_segment, batch_size=batch_size, print_progress=True)
    transcribe_time = time.time() - transcribe_start_time
    rprint(f"[cyan]⏱️ 转录用时:[/cyan] {transcribe_time:.2f}s")
    # 释放GPU资源
    del model
    torch.cuda.empty_cache()
    # 保存语言
    update_key("whisper.language", result['language'])
    if result['language'] == 'zh' and WHISPER_LANGUAGE != 'zh':
        raise ValueError("请指定转录语言为zh后重试！")
    # ------------
    # 2. 用人声音频对齐时间戳
    # ------------
    align_start_time = time.time()
    model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=device)
    result = whisperx.align(result["segments"], model_a, metadata, vocal_audio_segment, device, return_char_alignments=False)
    align_time = time.time() - align_start_time
    rprint(f"[cyan]⏱️ 对齐用时:[/cyan] {align_time:.2f}s")
    # 再次释放GPU资源
    torch.cuda.empty_cache()
    del model_a
    # 时间戳全局偏移
    for segment in result['segments']:
        segment['start'] += start
        segment['end'] += start
        for word in segment['words']:
            if 'start' in word:
                word['start'] += start
            if 'end' in word:
                word['end'] += start
    return result