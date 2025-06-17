# -*- coding: utf-8 -*-
"""
================================================================================================================
# 模块名称：_12_dub_to_vid.py
# 模块功能：视频与音频合成模块
# 模块描述：
#   本模块是整个视频配音流程的最后一步。它负责将原始视频、新生成的配音音轨、背景音乐以及
#   SRT字幕文件进行最终合成，生成一个带有硬字幕（如果选择）的配音版视频。
#
# 核心功能：
#   1. 音频标准化：对生成的配音文件进行音量标准化，以确保音量适中。
#   2. 视频、音频、字幕合成：使用强大的 FFmpeg 工具，将视频流、多路音频流（配音、背景音）
#      和字幕文件合并。
#   3. 字幕烧录：支持将 SRT 字幕文件作为硬字幕直接“烧录”到视频画面上，并提供丰富的样式自定义选项
#      （字体、大小、颜色、描边、背景等）。
#   4. 视频画面处理：在合成时保持原始视频的宽高比，通过缩放和填充（padding）避免画面拉伸变形。
#   5. 音频混合：将新的配音和原始视频的背景音（或指定的背景音乐）进行混合。
#   6. GPU加速：支持利用 NVIDIA GPU (h264_nvenc) 进行视频编码加速，大幅提升处理速度。
#   7. 平台兼容性：自动检测操作系统（Windows, Linux, macOS）以选择合适的默认字体。
#
# 设计思路与关键点：
#   - FFmpeg 核心：所有核心的合成工作都通过构造复杂的 FFmpeg 命令来实现，利用其强大的 filter_complex
#     功能处理多路输入和复杂的音视频操作。
#   - 可配置性：通过 `core.utils.load_key` 从配置文件加载关键参数，如是否烧录字幕、是否使用GPU加速，
#     使得流程更加灵活。
#   - 鲁棒性：在执行合成前，会检查必要的输入文件是否存在。
#
# 输出文件：
#   - output/output_dub.mp4: 最终合成的配音版视频文件。
# ================================================================================================================
"""
import platform
import subprocess

import cv2
import numpy as np
from rich.console import Console

from core._1_ytdlp import find_video_files
from core.asr_backend.audio_preprocess import normalize_audio_volume
from core.utils import *
from core.utils.models import *

console = Console()

# 定义最终输出的视频文件路径
DUB_VIDEO = "output/output_dub.mp4"
# 定义输入的字幕和音频文件路径
DUB_SUB_FILE = 'output/dub.srt'
DUB_AUDIO = 'output/dub.mp3'

# --- 字幕样式配置 ---
# 根据不同操作系统设置默认字体，以确保兼容性
TRANS_FONT_SIZE = 17
TRANS_FONT_NAME = 'Arial'  # Windows 默认字体
if platform.system() == 'Linux':
    TRANS_FONT_NAME = 'NotoSansCJK-Regular'  # Linux 推荐字体
if platform.system() == 'Darwin':
    TRANS_FONT_NAME = 'Arial Unicode MS'  # macOS 推荐字体

# 字幕颜色、描边、背景等详细样式参数
TRANS_FONT_COLOR = '&H00FFFF'      # 字体颜色 (黄色)
TRANS_OUTLINE_COLOR = '&H000000'   # 描边颜色 (黑色)
TRANS_OUTLINE_WIDTH = 1            # 描边宽度
TRANS_BACK_COLOR = '&H33000000'    # 字体背景色 (半透明黑)

@check_file_exists(_12_DUB_TO_VID)
def dub_to_vid_main():
    """
    主函数，执行视频和音频的合并流程。
    该函数会根据配置决定是否烧录字幕，并最终生成一个合成视频。
    """
    console.print(Panel("[bold cyan]🚀 开始最终视频合成...[/bold cyan]", title="第十二步: 合成配音视频", expand=False))

    # --- 步骤 1: 初始化与配置检查 ---
    console.print("[cyan]- 步骤 1/4: 正在初始化并检查配置...[/cyan]")
    VIDEO_FILE = find_video_files()
    if not VIDEO_FILE:
        console.print("[bold red]  ❌ 错误: 在项目中未找到任何视频文件。请确保视频文件存在。[/bold red]")
        return
    console.print(f"[green]  ✅ 找到源视频文件: `{VIDEO_FILE}`[/green]")

    if not load_key("burn_subtitles"):
        console.print("[bold yellow]  ⚠️  警告: 根据配置，未启用字幕烧录。将跳过视频合成。[/bold yellow]")
        console.print("[cyan]  - 正在创建一个0秒的黑色视频作为占位符...[/cyan]")
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(DUB_VIDEO, fourcc, 1, (1920, 1080))
        out.write(frame)
        out.release()
        console.print(Panel("[bold yellow]🟡 合成跳过[/bold yellow]", subtitle=f"已生成占位符视频: `{DUB_VIDEO}`", expand=False))
        return
    console.print("[green]  ✅ 配置检查完成，将执行字幕烧录与视频合成。[/green]")

    # --- 步骤 2: 标准化配音音量 ---
    console.print("[cyan]- 步骤 2/4: 正在标准化配音音量...[/cyan]")
    normalized_dub_audio = 'output/normalized_dub.wav'
    normalize_audio_volume(DUB_AUDIO, normalized_dub_audio)
    console.print(f"[green]  ✅ 配音音量已标准化，临时文件: `{normalized_dub_audio}`[/green]")

    # --- 步骤 3: 构建 FFmpeg 合成命令 ---
    console.print("[cyan]- 步骤 3/4: 正在构建 FFmpeg 合成命令...[/cyan]")
    background_file = _BACKGROUND_AUDIO_FILE
    video = cv2.VideoCapture(VIDEO_FILE)
    TARGET_WIDTH = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    TARGET_HEIGHT = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video.release()
    console.print(f"[green]  - 视频目标分辨率: {TARGET_WIDTH}x{TARGET_HEIGHT}[/green]")

    subtitle_filter = (
        f"subtitles={DUB_SUB_FILE}:force_style='FontSize={TRANS_FONT_SIZE},"
        f"FontName={TRANS_FONT_NAME},PrimaryColour={TRANS_FONT_COLOR},"
        f"OutlineColour={TRANS_OUTLINE_COLOR},OutlineWidth={TRANS_OUTLINE_WIDTH},"
        f"BackColour={TRANS_BACK_COLOR},Alignment=2,MarginV=27,BorderStyle=4'"
    )

    cmd = [
        'ffmpeg', '-y',
        '-i', VIDEO_FILE,             # 输入0: 原始视频
        '-i', background_file,        # 输入1: 背景音
        '-i', normalized_dub_audio,   # 输入2: 标准化后的配音
        '-filter_complex',
        f'[0:v]scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease,'
        f'pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2,'
        f'{subtitle_filter}[v];'
        f'[1:a][2:a]amix=inputs=2:duration=first:dropout_transition=3[a]'
    ]

    if load_key("ffmpeg_gpu"):
        console.print("[green]  - 检测到GPU加速已启用 (h264_nvenc)。[/green]")
        cmd.extend(['-map', '[v]', '-map', '[a]', '-c:v', 'h264_nvenc'])
    else:
        console.print("[green]  - 将使用CPU进行编码。[/green]")
        cmd.extend(['-map', '[v]', '-map', '[a]'])

    cmd.extend(['-c:a', 'aac', '-b:a', '96k', DUB_VIDEO])
    console.print("[green]  ✅ FFmpeg 命令构建完成。[/green]")

    # --- 步骤 4: 执行视频合成 ---
    console.print("[cyan]- 步骤 4/4: 正在执行视频合成... (这可能需要一些时间，请耐心等待) 🎬[/cyan]")
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    console.print(Panel(f"[bold green]🎉 视频合成完毕！[/bold green]", subtitle=f"最终配音视频: `{DUB_VIDEO}`", expand=False))


if __name__ == '__main__':
    dub_to_vid_main()
