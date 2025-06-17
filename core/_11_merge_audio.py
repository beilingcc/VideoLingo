# -*- coding: utf-8 -*-
"""
================================================================================================================
# 模块名称：_11_merge_audio.py
# 模块功能：音频合并与字幕生成模块
# 模块描述：
#   本模块是视频配音流程的收尾步骤之一，负责将上一阶段(_10_gen_audio.py)生成的所有、经过精确对时的
#   独立音频片段，根据其新的时间轴信息，合并成一个完整的、与视频总时长匹配的配音音轨。
#   同时，它还会根据最终的时间轴数据生成一个SRT格式的字幕文件，确保配音和字幕的完美同步。
#
# 核心功能：
#   1. 数据加载与预处理：从 _10_GEN_AUDIO.xlsx 文件中加载包含最终时间轴和文本信息的数据。
#   2. 音频片段处理：对每个音频片段进行标准化处理（如压缩、格式转换），为合并做准备。
#   3. 静音填充与合并：精确计算每个音频片段之间的静音间隙，并将其插入到合并的音轨中，
#      最终将所有片段和静音拼接成一个连续的音频流。
#   4. SRT字幕文件生成：使用最终确定的时间戳和对应的文本行，生成标准的SRT字幕文件。
#   5. 主流程控制：协调以上所有步骤，输出最终的配音文件 (dub.mp3) 和字幕文件 (dub.srt)。
#
# 设计思路与关键点：
#   - 时间精确性：合并过程严格遵循 _10_gen_audio.py 中重建的时间轴，这是保证音画同步的关键。
#   - 鲁棒性：代码包含对缺失音频文件的检查，避免因个别文件错误导致整个流程中断。
#   - 效率：通过 pydub 库高效处理音频，并使用 ffmpeg 进行底层音视频操作。
#   - 用户体验：使用 rich 库提供清晰的命令行进度反馈。
#
# 输出文件：
#   - output/dub.mp3: 最终合并生成的配音文件。
#   - output/dub.srt: 与配音文件同步的SRT字幕文件。
# ================================================================================================================
"""
import os
import pandas as pd
import subprocess
from pydub import AudioSegment
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.console import Console
from rich.panel import Panel

from core.utils import *
from core.utils.models import *

console = Console()

# 定义输出文件的路径
DUB_VOCAL_FILE = 'output/dub.mp3'  # 最终配音文件
DUB_SUB_FILE = 'output/dub.srt'    # 配音对应的字幕文件
OUTPUT_FILE_TEMPLATE = f"{_AUDIO_SEGS_DIR}/{{}}.wav"  # 单个音频片段的路径模板

def load_and_flatten_data(excel_file):
    """
    从指定的Excel文件中加载数据，并对特定列（lines, new_sub_times）进行“扁平化”处理。
    这些列中存储的是字符串形式的列表，需要用eval解析并展开成一个单一列表。

    Args:
        excel_file (str): 输入的Excel文件路径 (_10_GEN_AUDIO.xlsx)。

    Returns:
        tuple: 包含原始DataFrame、扁平化后的文本行列表和扁平化后的时间戳列表。
    """
    df = pd.read_excel(excel_file)
    # 解析并扁平化'lines'列
    lines = [eval(line) if isinstance(line, str) else line for line in df['lines'].tolist()]
    lines = [item for sublist in lines for item in sublist]
    
    # 解析并扁平化'new_sub_times'列
    new_sub_times = [eval(time) if isinstance(time, str) else time for time in df['new_sub_times'].tolist()]
    new_sub_times = [item for sublist in new_sub_times for item in sublist]
    
    return df, lines, new_sub_times

def get_audio_files(df):
    """
    根据DataFrame中的信息，生成所有待合并的音频片段的文件路径列表。

    Args:
        df (pd.DataFrame): 包含音频块信息的DataFrame。

    Returns:
        list: 包含所有音频片段绝对路径的列表。
    """
    audios = []
    for index, row in df.iterrows():
        number = row['number']
        # 解析'lines'列以确定每个块包含多少行（即多少个音频文件）
        line_count = len(eval(row['lines']) if isinstance(row['lines'], str) else row['lines'])
        for line_index in range(line_count):
            temp_file = OUTPUT_FILE_TEMPLATE.format(f"{number}_{line_index}")
            audios.append(temp_file)
    return audios

def process_audio_segment(audio_file):
    """
    处理单个音频片段。使用ffmpeg将其转换为特定参数（16kHz, 单声道, 64k比特率）的MP3，
    然后加载为pydub的AudioSegment对象，便于后续处理。

    Args:
        audio_file (str): 待处理的音频文件路径（.wav格式）。

    Returns:
        AudioSegment: 处理后的pydub音频对象。
    """
    temp_file = f"{audio_file}_temp.mp3"
    # 构建ffmpeg命令，进行音频压缩和格式转换
    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-i', audio_file,
        '-ar', '16000',  # 设置采样率为16kHz
        '-ac', '1',      # 设置为单声道
        '-b:a', '64k',   # 设置比特率为64kbps
        temp_file
    ]
    # 执行命令，隐藏输出
    subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # 从临时MP3文件加载音频
    audio_segment = AudioSegment.from_mp3(temp_file)
    # 删除临时文件
    os.remove(temp_file)
    return audio_segment

def merge_audio_segments(audios, new_sub_times, sample_rate):
    """
    将所有音频片段根据新的时间轴合并成一个完整的音轨。

    该函数的核心逻辑是：
    1. 创建一个空的音频段作为画布。
    2. 遍历每个音频片段和其对应的时间戳。
    3. 计算当前片段与上一个片段之间的静音时长。
    4. 将这段静音添加到画布上。
    5. 将当前音频片段添加到画布上。
    6. 重复此过程，直到所有片段都合并完毕。

    Args:
        audios (list): 所有音频片段的文件路径列表。
        new_sub_times (list): 与音频片段对应的时间戳列表 ([(start, end), ...])。
        sample_rate (int): 音频采样率。

    Returns:
        AudioSegment: 最终合并生成的完整pydub音频对象。
    """
    # 初始化一个空的音频段，采样率与目标一致
    merged_audio = AudioSegment.silent(duration=0, frame_rate=sample_rate)
    
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn()) as progress:
        merge_task = progress.add_task("[green]🎵 正在合并音频片段...[/green]", total=len(audios))
        
        for i, (audio_file, time_range) in enumerate(zip(audios, new_sub_times)):
            if not os.path.exists(audio_file):
                console.print(f"[bold yellow]⚠️  警告: 文件 {audio_file} 不存在，已跳过。[/bold yellow]")
                progress.advance(merge_task)
                continue
                
            audio_segment = process_audio_segment(audio_file)
            start_time, end_time = time_range
            
            # 关键步骤：添加静音片段以保证时间对齐
            if i > 0:
                # 计算与上一个片段结尾的间隔
                prev_end = new_sub_times[i-1][1]
                silence_duration = start_time - prev_end
                if silence_duration > 0:
                    silence = AudioSegment.silent(duration=int(silence_duration * 1000), frame_rate=sample_rate)
                    merged_audio += silence
            elif start_time > 0:
                # 处理第一个片段之前的静音
                silence = AudioSegment.silent(duration=int(start_time * 1000), frame_rate=sample_rate)
                merged_audio += silence
                
            # 将当前处理好的音频片段拼接到主音轨
            merged_audio += audio_segment
            progress.advance(merge_task)
    
    return merged_audio

def create_srt_subtitle(lines, new_sub_times):
    """
    根据最终的文本行和时间戳生成SRT字幕文件。

    Args:
        lines (list): 所有字幕行的文本内容列表。
        new_sub_times (list): 对应的开始和结束时间戳列表。
    """
    with open(DUB_SUB_FILE, 'w', encoding='utf-8') as f:
        for i, ((start_time, end_time), line) in enumerate(zip(new_sub_times, lines), 1):
            # 将秒转换为SRT时间码格式 (时:分:秒,毫秒)
            start_str = f"{int(start_time//3600):02d}:{int((start_time%3600)//60):02d}:{int(start_time%60):02d},{int((start_time*1000)%1000):03d}"
            end_str = f"{int(end_time//3600):02d}:{int((end_time%3600)//60):02d}:{int(end_time%60):02d},{int((end_time*1000)%1000):03d}"
            
            # 写入SRT格式内容
            f.write(f"{i}\n")
            f.write(f"{start_str} --> {end_str}\n")
            f.write(f"{line}\n\n")

@check_file_exists(DUB_VOCAL_FILE) # 检查最终的音频文件
def merge_audio_main():
    """主函数：协调整个音频合并与字幕生成流程。"""
    console.print(Panel("[bold cyan]🚀 开始合并最终音轨与生成字幕...[/bold cyan]", title="第十一步: 合成音频与字幕", expand=False))

    # 步骤 1: 加载并解析时间轴数据
    console.print(f"[cyan]- 步骤 1/4: 正在从 `{_10_GEN_AUDIO}` 加载并解析最终时间轴数据...[/cyan]")
    df, lines, new_sub_times = load_and_flatten_data(_10_GEN_AUDIO)
    console.print(f"[green]  ✅ 数据加载与扁平化完成，共 {len(lines)} 个音频片段需要处理。[/green]")

    # 步骤 2: 获取音频文件列表
    console.print("[cyan]- 步骤 2/4: 正在生成音频文件列表...[/cyan]")
    audios = get_audio_files(df)
    console.print(f"[green]  ✅ 文件列表生成，确认共 {len(audios)} 个文件。[/green]")

    # 步骤 3: 合并所有音频片段
    console.print("[cyan]- 步骤 3/4: 正在合并所有音频片段为一个音轨...[/cyan]")
    sample_rate = 16000  # 与process_audio_segment中的设置保持一致
    merged_audio = merge_audio_segments(audios, new_sub_times, sample_rate)
    console.print(f"[green]  ✅ 音频合并完成，音轨总时长: {len(merged_audio) / 1000:.2f}s。[/green]")

    # 步骤 4: 导出最终成品
    console.print(f"[cyan]- 步骤 4/4: 正在导出最终配音文件和SRT字幕...[/cyan]")
    merged_audio.export(DUB_VOCAL_FILE, format="mp3", bitrate="64k")
    create_srt_subtitle(lines, new_sub_times)

    console.print(Panel(f"[bold green]🎉 音频与字幕合成完毕！[/bold green]", subtitle=f"最终配音音轨: `{DUB_VOCAL_FILE}`\n最终字幕文件: `{DUB_SUB_FILE}`", expand=False))


if __name__ == '__main__':
    merge_audio_main()