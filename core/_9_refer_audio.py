# -*- coding: utf-8 -*-
"""
参考音频提取模块

本模块的核心功能是根据 `_8_1_AUDIO_TASK.xlsx` 中定义的精确时间戳，从经过
Demucs分离后的人声轨道（`_VOCAL_AUDIO_FILE`）中，切割出与每条字幕相对应的
音频片段。这些切割出的音频片段被称为“参考音频”(Reference Audio)。

为什么需要参考音频？
在高质量的TTS（文本转语音）声音克隆（Voice Clone）流程中，参考音频扮演着至关重要的角色。
它为TTS系统提供了模仿的蓝本，使得生成的配音能够在以下方面与原始说话者保持高度一致：
- **音色 (Timbre)**: 确保配音的音色与原声相符。
- **韵律 (Prosody)**: 模仿原声的语速、节奏和抑扬顿挫。
- **情感 (Emotion)**: 传递与原声相似的情感色彩。
- **口音 (Accent)**: 在某些情况下，可以保留或模仿特定的口音。

工作流程：
1.  **前置检查与执行 (`demucs_audio`)**: 
    - 在开始提取前，脚本会首先调用 `demucs_audio()` 函数。这是一个保障性措施，
      确保即使之前的步骤被跳过，Demucs人声分离也一定被执行了。只有获得了
      纯净的人声轨道，后续的参考音频才具有价值。

2.  **跳过已存在任务**: 
    - 检查目标目录 `_AUDIO_REFERS_DIR` 是否已存在音频片段。如果已存在，则跳过
      整个提取过程，避免重复工作。

3.  **加载数据**: 
    - 使用 `pandas` 读取 `_8_1_AUDIO_TASK.xlsx` 任务清单。
    - 使用 `soundfile` 库加载人声文件 `_VOCAL_AUDIO_FILE`，获取音频数据和采样率。

4.  **时间戳转换与切割 (`extract_audio` & `time_to_samples`)**: 
    - 遍历任务清单中的每一行。
    - `time_to_samples` 函数将SRT格式的时间字符串（如 '00:01:23,456'）
      精确转换为音频采样点（sample）的索引。这是通过将时、分、秒、毫秒换算
      成总秒数，再乘以采样率得到的。
    - `extract_audio` 函数利用计算出的开始和结束采样点，从加载的音频数据中
      切片，提取出对应的音频片段。

5.  **保存与反馈**: 
    - 每个提取出的音频片段被保存为独立的WAV文件，以其在任务表中的编号命名
      （例如 `1.wav`, `2.wav`），并存放在 `_AUDIO_REFERS_DIR` 目录中。
    - 使用 `rich.progress` 显示一个可视化的进度条，实时反馈提取进度。
    - 任务完成后，打印成功的面板消息。

使用方法：
  直接运行 `extract_refer_audio_main()` 函数。它会自动完成所有检查、加载、
  提取和保存工作。
"""

import os
import pandas as pd
import soundfile as sf
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from core.asr_backend.demucs_vl import demucs_audio
from core.utils import *
from core.utils.models import *

console = Console()

def time_to_samples(time_str: str, sr: int) -> int:
    """
    将 'HH:MM:SS,ms' 格式的时间字符串转换为音频采样点索引。

    参数：
        time_str (str): SRT格式的时间戳字符串。
        sr (int): 音频的采样率。

    返回：
        int: 对应于该时间的采样点索引。
    """
    try:
        h, m, s_ms = time_str.split(':')
        s, ms = s_ms.split(',') if ',' in s_ms else (s_ms, '0')
        total_seconds = int(h) * 3600 + int(m) * 60 + float(s) + float(ms) / 1000
        return int(total_seconds * sr)
    except ValueError:
        console.log(f"[bold red]错误: 时间格式无效 '{time_str}'。请使用 'HH:MM:SS,ms' 格式。[/bold red]")
        # 返回一个有效值或重新引发异常，以避免进一步的错误
        raise

def extract_audio(audio_data: np.ndarray, sr: int, start_time: str, end_time: str, out_file: str):
    """
    根据开始和结束时间戳，从音频数据中提取片段并保存为文件。

    参数：
        audio_data (np.ndarray): 完整的音频数据。
        sr (int): 采样率。
        start_time (str): 开始时间戳。
        end_time (str): 结束时间戳。
        out_file (str): 输出WAV文件的路径。
    """
    start_sample = time_to_samples(start_time, sr)
    end_sample = time_to_samples(end_time, sr)
    
    # 确保切片索引在数组边界内
    segment = audio_data[start_sample:end_sample]
    sf.write(out_file, segment, sr)

@check_file_exists(_9_REFER_AUDIO)
def refer_audio_main():
    """主函数：执行参考音频的提取流程。"""
    console.print(Panel("[bold cyan]🔊 开始提取参考音频...[/bold cyan]", title="第九步: 提取参考音源", expand=False))

    # 步骤 1: 确保Demucs已运行
    console.print("[cyan]- 步骤 1/4: 正在检查并确保人声已从音轨中分离...[/cyan]")
    demucs_audio()
    console.print("[green]  ✅ Demucs人声分离已确认。[/green]")

    # 步骤 2: 检查是否已提取
    if os.path.exists(os.path.join(_AUDIO_REFERS_DIR, '1.wav')):
        console.print(Panel("[bold blue]参考音频片段已存在，跳过提取过程。[/bold blue]", title="提示", expand=False))
        return

    # 步骤 3: 加载数据
    console.print(f"[cyan]- 步骤 2/4: 正在从 `{_8_1_AUDIO_TASK}` 和 `{_VOCAL_AUDIO_FILE}` 加载数据...[/cyan]")
    try:
        os.makedirs(_AUDIO_REFERS_DIR, exist_ok=True)
        df = pd.read_excel(_8_1_AUDIO_TASK)
        df['start_time_str'] = df['start_time_str'].astype(str)
        df['end_time_str'] = df['end_time_str'].astype(str)
        data, sr = sf.read(_VOCAL_AUDIO_FILE)
        console.print(f"[green]  ✅ 数据加载成功，共 {len(df)} 条任务，音频采样率: {sr}Hz。[/green]")
    except FileNotFoundError as e:
        console.print(Panel(f"[bold red]错误: 必需文件未找到: {e.filename}。请确保之前的步骤已成功运行。[/bold red]", title="文件缺失"))
        return
    except Exception as e:
        console.print(Panel(f"[bold red]加载数据时发生未知错误: {e}[/bold red]", title="错误"))
        return

    # 步骤 4: 提取并保存
    console.print("[cyan]- 步骤 3/4: 正在逐条提取参考音频片段...[/cyan]")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        transient=True
    ) as progress:
        task = progress.add_task("[cyan]提取进度[/cyan]", total=len(df))
        for _, row in df.iterrows():
            out_file = os.path.join(_AUDIO_REFERS_DIR, f"{row['number']}.wav")
            extract_audio(data, sr, row['start_time_str'], row['end_time_str'], out_file)
            progress.update(task, advance=1)
    console.print("[green]  ✅ 所有参考音频片段提取完成。[/green]")

    console.print(Panel(f"[bold green]🎉 参考音源提取成功！[/bold green]", subtitle=f"所有片段已保存至: {_AUDIO_REFERS_DIR}", expand=False))

if __name__ == "__main__":
    refer_audio_main()