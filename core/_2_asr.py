# -*- coding: utf-8 -*-
"""
自动语音识别 (ASR) 模块

本模块负责将视频中的音频内容转换为带时间戳的文本。这是视频处理流水线的第二步，
紧接着视频下载。它整合了多种语音识别后端，并提供了音频预处理功能，如人声分离，
以提高转录的准确性。

核心功能:
- **视频到音频转换**: 首先将输入视频文件中的音频流提取出来，保存为独立的音频文件。
- **人声分离 (可选)**: 利用 Demucs 模型，可以从音频中分离出人声，去除背景音乐和噪音，从而显著提升语音识别的准确率。此功能可根据配置开关。
- **音频分块**: 将完整的音频文件切割成较小的片段，以便于并行处理和减小单个识别任务的内存消耗。
- **多后端支持**: 支持多种 ASR 引擎，包括:
    - **本地 WhisperX**: 在本地机器上运行 Whisper 模型，适合对数据隐私有较高要求的场景。
    - **云端 WhisperX (302 API)**: 通过 API 调用外部服务进行识别，可能提供更强的性能。
    - **ElevenLabs API**: 调用 ElevenLabs 的语音识别服务，是另一个高质量的云端选项。
- **结果整合与后处理**: 将所有音频片段的识别结果合并，并进行格式化处理，最终保存为结构化的数据文件（如 CSV），为后续的翻译和字幕生成步骤做准备。

使用方法:
  该模块通常作为流水线的一部分被自动调用。也可以独立运行 `transcribe()` 函数，
  它会自动查找前一步下载的视频文件，并执行完整的语音识别流程。
"""

from core.utils import *
from core.asr_backend.demucs_vl import demucs_audio
from core.asr_backend.audio_preprocess import process_transcription, convert_video_to_audio, split_audio, save_results, normalize_audio_volume
from core._1_ytdlp import find_video_files
from core.utils.models import *
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress

console = Console()

@check_file_exists(_2_ASR_CHUNK_FILE)
def asr_main():
    """
    执行完整的视频音频转录流程。
    """
    console.print(Panel("[bold cyan]🚀 启动自动语音识别 (ASR) 流程...[/bold cyan]", title="第二步: 语音识别", expand=False))
    try:
        # 步骤 1: 将视频转换为音频
        console.print("[cyan]- 步骤 1/5: 正在从视频中提取音频...[/cyan]")
        video_file = find_video_files()
        console.print(f"[green]  - 找到视频文件: {video_file}[/green]")
        convert_video_to_audio(video_file)
        console.print(f"[green]  ✅ 音频提取完成，文件: `{_RAW_AUDIO_FILE}`[/green]")

        # 步骤 2: (可选) 使用 Demucs 分离人声
        console.print("[cyan]- 步骤 2/5: 正在检查是否分离人声...[/cyan]")
        if load_key("demucs"):
            console.print("[green]  - 检测到 Demucs 已启用，正在分离人声... (这可能需要较长时间)[/green]")
            demucs_audio()
            console.print("[green]  - 正在对分离出的人声进行音量标准化...[/green]")
            vocal_audio = normalize_audio_volume(_VOCAL_AUDIO_FILE, _VOCAL_AUDIO_FILE, format="mp3")
            console.print(f"[green]  ✅ 人声分离完成，使用音轨: `{vocal_audio}`[/green]")
        else:
            console.print("[yellow]  - Demucs 未启用，将使用原始音轨进行识别。[/yellow]")
            vocal_audio = _RAW_AUDIO_FILE

        # 步骤 3: 将完整音频分割成小片段以便处理
        console.print("[cyan]- 步骤 3/5: 正在将音频分割成处理片段...[/cyan]")
        segments = split_audio(vocal_audio)  # 修正: 对处理后的音轨进行分割
        console.print(f"[green]  ✅ 音频已分割成 {len(segments)} 个片段。[/green]")

        # 步骤 4: 根据配置选择 ASR 后端，并逐片段进行转录
        console.print("[cyan]- 步骤 4/5: 正在调用 ASR 引擎进行语音转录...[/cyan]")
        runtime = load_key("whisper.runtime")
        if runtime == "local":
            from core.asr_backend.whisperX_local import transcribe_audio as ts
            console.print("[green]  - 使用本地 WhisperX 模型。[/green]")
        elif runtime == "cloud":
            from core.asr_backend.whisperX_302 import transcribe_audio_302 as ts
            console.print("[green]  - 使用云端 WhisperX (302 API)。[/green]")
        elif runtime == "elevenlabs":
            from core.asr_backend.elevenlabs_asr import transcribe_audio_elevenlabs as ts
            console.print("[green]  - 使用 ElevenLabs API。[/green]")

        all_results = []
        with Progress(console=console) as progress:
            task = progress.add_task("[green]  - 转录进度...", total=len(segments))
            for start, end in segments:
                result = ts(_RAW_AUDIO_FILE, vocal_audio, start, end)
                if result:
                    all_results.append(result)
                progress.update(task, advance=1)
        console.print("[green]  ✅ 所有片段转录完成。[/green]")

        # 步骤 5: 合并、处理并保存最终结果
        console.print("[cyan]- 步骤 5/5: 正在合并和处理转录结果...[/cyan]")
        combined_result = {'segments': []}
        for res in all_results:
            if res and 'segments' in res:
                combined_result['segments'].extend(res['segments'])

        df = process_transcription(combined_result)
        save_results(df)
        console.print("[green]  ✅ 结果处理完成。[/green]")

        console.print(Panel(f"[bold green]🎉 ASR 流程完成！[/bold green]", subtitle=f"结果已保存到 `{_2_ASR_CHUNK_FILE}`", expand=False))

    except Exception as e:
        console.print(Panel(f"[bold red]❌ ASR 流程发生错误[/bold red]", subtitle=str(e), expand=False))


if __name__ == "__main__":
    asr_main()