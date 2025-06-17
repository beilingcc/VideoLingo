# -*- coding: utf-8 -*-
"""
TTS音频生成与时间轴对齐模块

本模块是配音生成流程的核心引擎，负责将文本转换为语音，并通过复杂的变速和对齐算法，
确保生成的音频在时间上与原始视频完美同步。它衔接了 `_8_2_dub_chunks.py` 生成的
配音规划表，输出最终可用于视频合成的、独立的、已对时的音频片段。

核心功能分为三大步：

1.  **TTS 音频生成 (`generate_tts_audio`)**：
    - **目的**: 将规划表 (`_8_2_DUB_CHUNKS.xlsx`) 中的每一行文本通过指定的TTS引擎
      （如 GPT-SoVITS）转换成初始的WAV音频文件。
    - **并行处理**: 为了大幅提升效率，此步骤采用多线程 (`ThreadPoolExecutor`)
      并行生成音频。但考虑到 `gpt-sovits` 等模型在并行调用时可能不稳定，代码中
      特别加入了判断，当TTS方法为 `gpt-sovits` 时，自动切换回单线程模式，
      体现了设计的鲁棒性。
    - **预热机制 (Warm-up)**: 在大规模并行处理前，先顺序执行前几个任务。这有助于初始化TTS模型、预热GPU，避免在并行初期因资源加载导致超时或错误。
    - **时长计算**: 每生成一个音频，立即计算其精确的实际时长 (`real_dur`)，
      并记录回DataFrame中。这个数据是后续所有时间计算的基础。

2.  **音频块处理与动态变速 (`merge_chunks` & `process_chunk`)**：
    - **目的**: 解决TTS生成音频的自然时长与视频中分配给它的时间段不匹配的问题。
    - **分块处理**: 算法以 `_8_2_dub_chunks.py` 中定义的“块”(`chunk`)
      为单位进行操作。一个块通常是一个完整的意群或句子，对一个块内的所有音频
      采用统一的变速策略，可以使得最终听感更自然，避免语速的突兀变化.
    - **智能变速因子计算 (`process_chunk`)**: 这是本模块最核心的算法。它会综合
      考虑一个块内所有生成音频的总时长、原始字幕间的静音间隙、以及配置文件中
      定义的可容忍时长和最大语速限制，计算出一个最优的整体 `speed_factor`.
      算法会智能决策是“保留”还是“牺牲”字幕间的静音，以在不超出时间限制的前提下，
      尽可能保持自然的语速.
    - **时间轴重建**: 计算出变速因子后，模块会重新计算块内每个音频片段的开始和
      结束时间点，生成一个新的时间轴 `new_sub_times`，确保所有片段能被严丝合缝地
      “铺”在目标时间段内.

3.  **精确对时与容错 (`adjust_audio_speed` & `merge_chunks`中的截断逻辑)**：
    - **目的**: 处理 `ffmpeg` 变速可能带来的微小误差，并对最终时长进行强制对齐.
    - **`ffmpeg` 误差校正 (`adjust_audio_speed`)**: `ffmpeg` 的 `atempo` 滤镜在处理
      极短音频时，变速后的时长可能与理论值有微小出入。此函数在变速后会进行检查，
      如果发现误差，且满足特定条件（如音频很短、误差在容忍范围内），会用 `pydub`
      进行精确裁剪，确保输出时长就是理论时长.
    - **块级时长溢出处理**: 在 `merge_chunks` 的最后，如果一整个块处理完毕后，
      其总时长还是略微超出了原始视频分配的时间（在0.6秒的容忍范围内），算法会
      对这个块的“最后一句”音频进行截断，强制使总时长对齐。这是保证最终音画同步
      的最后一道防线.

最终，该模块会输出所有处理好的、已变速、已对时的音频片段到 `_AUDIO_SEGS_DIR` 目录，
并生成一个包含新时间轴信息的 `_10_GEN_AUDIO.xlsx` 文件，供后续模块使用.

"""
import os
import time
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple

import pandas as pd
from pydub import AudioSegment
from rich.console import Console
from rich.progress import Progress

from core.asr_backend.audio_preprocess import get_audio_duration
from core.tts_backend.tts_main import tts_main
from core.utils import *
from core.utils.models import *

console = Console()

# 定义临时和最终输出文件的路径模板
TEMP_FILE_TEMPLATE = f"{_AUDIO_TMP_DIR}/{{}}_temp.wav"
OUTPUT_FILE_TEMPLATE = f"{_AUDIO_SEGS_DIR}/{{}}.wav"
# 定义预热任务的数量
WARMUP_SIZE = 5

def parse_df_srt_time(time_str: str) -> float:
    """将DataFrame中的SRT时间格式（'HH:MM:SS.ms'）转换为秒。"""
    hours, minutes, seconds_ms = time_str.strip().split(':')
    seconds, milliseconds = seconds_ms.split('.')
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000

def adjust_audio_speed(input_file: str, output_file: str, speed_factor: float) -> None:
    """
    使用ffmpeg调整音频速度，并处理边缘情况以确保时长精确。

    参数：
        input_file (str): 输入的临时音频文件路径。
        output_file (str): 输出的最终音频文件路径。
        speed_factor (float): 速度调整因子。>1 加速, <1 减速。
    """
    # 如果速度因子非常接近1.0，直接复制文件，避免不必要的处理和潜在的精度损失
    if abs(speed_factor - 1.0) < 0.001:
        shutil.copy2(input_file, output_file)
        return

    # 使用ffmpeg的atempo滤镜进行变速
    cmd = ['ffmpeg', '-i', input_file, '-filter:a', f'atempo={speed_factor}', '-y', output_file]
    input_duration = get_audio_duration(input_file)
    max_retries = 2
    for attempt in range(max_retries):
        try:
            # 隐藏ffmpeg的输出，只在出错时捕获
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            output_duration = get_audio_duration(output_file)
            expected_duration = input_duration / speed_factor
            diff = output_duration - expected_duration

            # **核心容错逻辑**: 处理ffmpeg atempo在短音频上的不精确问题
            # 如果变速后时长超出预期，但音频本身很短(<3s)且误差不大(<0.1s)，则强制裁剪到预期长度
            if output_duration >= expected_duration * 1.02 and input_duration < 3 and diff <= 0.1:
                audio = AudioSegment.from_wav(output_file)
                trimmed_audio = audio[:int(expected_duration * 1000)]  # pydub使用毫秒
                trimmed_audio.export(output_file, format="wav")
                # console.log(f"[yellow]✂️ 音频 '{os.path.basename(input_file)}' 被裁剪至预期时长: {expected_duration:.2f}s[/yellow]")
                return
            # 如果误差过大，则抛出异常，防止问题累积
            elif output_duration >= expected_duration * 1.02:
                raise RuntimeError(f"音频变速后时长异常: ... speed_factor={speed_factor}, in_dur={input_duration:.2f}s, out_dur={output_duration:.2f}s")
            return
        except subprocess.CalledProcessError as e:
            if attempt < max_retries - 1:
                rprint(f"[yellow]⚠️ 音频变速失败，1秒后重试 ({attempt + 1}/{max_retries}) 文件: {os.path.basename(input_file)}[/yellow]")
                time.sleep(1)
            else:
                rprint(f"[red]❌ 音频变速失败达到最大重试次数: {os.path.basename(input_file)}[/red]")
                raise e

def process_row(row: pd.Series, tasks_df: pd.DataFrame) -> Tuple[int, float]:
    """
    处理单行任务的辅助函数：调用TTS并计算生成音频的总时长。

    参数：
        row (pd.Series): 需要处理的任务行。
        tasks_df (pd.DataFrame): 完整的任务DataFrame，用于传递给TTS后端。

    返回：
        Tuple[int, float]: 任务编号和该任务所有行生成的音频总时长。
    """
    number = row['number']
    # 'lines'列可能是字符串格式的列表，需要用eval解析
    lines = eval(row['lines']) if isinstance(row['lines'], str) else row['lines']
    real_dur = 0
    for line_index, line_text in enumerate(lines):
        temp_file = TEMP_FILE_TEMPLATE.format(f"{number}_{line_index}")
        tts_main(line_text, temp_file, number, tasks_df)
        real_dur += get_audio_duration(temp_file)
    return number, real_dur

def generate_tts_audio(tasks_df: pd.DataFrame) -> pd.DataFrame:
    """
    通过TTS批量生成音频，并计算实际时长。
    包含预热和并行处理逻辑。
    """
    tasks_df['real_dur'] = 0.0
    rprint("[bold green]🎯 开始生成TTS音频...[/bold green]")

    with Progress(transient=True) as progress:
        task = progress.add_task("[cyan]🔄 生成TTS音频...", total=len(tasks_df))

        # 1. 预热阶段：顺序处理前几个任务，以稳定初始化模型
        warmup_size = min(WARMUP_SIZE, len(tasks_df))
        for index, row in tasks_df.head(warmup_size).iterrows():
            try:
                number, real_dur = process_row(row, tasks_df)
                tasks_df.loc[index, 'real_dur'] = real_dur
                progress.advance(task)
            except Exception as e:
                rprint(f"[red]❌ 预热阶段出错: {e}[/red]")
                raise

        # 2. 并行处理阶段：处理剩余任务
        # 特殊处理：如果TTS方法是gpt_sovits，则不使用并行处理
        max_workers = load_key("max_workers") if load_key("tts_method") != "gpt_sovits" else 1
        if len(tasks_df) > warmup_size:
            remaining_tasks = tasks_df.iloc[warmup_size:]
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 创建一个从future到原始索引的映射
                future_to_index = {executor.submit(process_row, row, tasks_df.copy()): index for index, row in remaining_tasks.iterrows()}

                for future in as_completed(future_to_index):
                    original_index = future_to_index[future]
                    try:
                        _, real_dur = future.result()
                        tasks_df.loc[original_index, 'real_dur'] = real_dur
                    except Exception as e:
                        rprint(f"[red]❌ 并行处理任务时出错 (行: {original_index}): {e}[/red]")
                        # 可选择在此处标记失败的任务，而不是直接中断
                        tasks_df.loc[original_index, 'real_dur'] = -1 # 标记为失败
                    finally:
                        progress.advance(task)

    rprint("[bold green]✨ TTS音频生成完成！[/bold green]")
    return tasks_df

def process_chunk(chunk_df: pd.DataFrame, accept: float, min_speed: float) -> tuple[float, bool]:
    """
    处理单个音频块，计算出最优的整体变速因子和是否保留间隙。
    """
    chunk_durs = chunk_df['real_dur'].sum()  # 块内所有TTS音频的实际总长
    tol_durs = chunk_df['tol_dur'].sum()      # 块内所有行可用的总时长（含容忍度）
    durations = tol_durs - chunk_df.iloc[-1]['tolerance'] # 块内所有行分配到的总时长（不含最后一行容忍度）
    all_gaps = chunk_df['gap'].sum() - chunk_df.iloc[-1]['gap'] # 块内所有字幕间的总间隙

    keep_gaps = True
    speed_var_error = 0.1 # 一个微小的误差修正值，防止速度计算结果过于贴近边界

    # 核心决策逻辑：根据不同情况计算变速因子
    if (chunk_durs + all_gaps) / accept < durations:
        # 情况1: 即使保留所有间隙，并按正常语速播放，时间也足够。可以适当放慢语速。
        speed_factor = max(min_speed, (chunk_durs + all_gaps) / (durations - speed_var_error))
    elif chunk_durs / accept < durations:
        # 情况2: 保留间隙时间不够，但去掉间隙后，按正常语速播放时间足够。
        speed_factor = max(min_speed, chunk_durs / (durations - speed_var_error))
        keep_gaps = False # 决策：牺牲间隙
    elif (chunk_durs + all_gaps) / accept < tol_durs:
        # 情况3: 时间紧张，即使利用上所有容忍时长，也需要加速，但还能保留间隙。
        speed_factor = max(min_speed, (chunk_durs + all_gaps) / (tol_durs - speed_var_error))
    else:
        # 情况4: 时间最紧张，必须牺牲间隙并利用所有容忍时长进行加速。
        speed_factor = chunk_durs / (tol_durs - speed_var_error)
        keep_gaps = False

    return round(speed_factor, 3), keep_gaps

def merge_chunks(tasks_df: pd.DataFrame) -> pd.DataFrame:
    """
    合并音频块，应用变速，并重建时间轴。
    """
    rprint("[bold blue]🔄 开始处理音频块并对齐时间轴...[/bold blue]")
    accept = load_key("speed_factor.accept")
    min_speed = load_key("speed_factor.min")
    chunk_start_index = 0

    tasks_df['new_sub_times'] = None # 初始化新时间轴列

    for index, row in tasks_df.iterrows():
        if row['cut_off'] == 1:
            # 识别到一个块的结束点
            chunk_df = tasks_df.iloc[chunk_start_index:index + 1].reset_index(drop=True)
            speed_factor, keep_gaps = process_chunk(chunk_df, accept, min_speed)

            # 步骤1: 计算块的起止时间，并初始化当前时间指针
            chunk_start_time = parse_df_srt_time(chunk_df.iloc[0]['start_time_str'])
            # 块的结束时间是最后一行字幕的结束时间点加上其容忍度
            chunk_end_time = parse_df_srt_time(chunk_df.iloc[-1]['end_time_str']) + chunk_df.iloc[-1]['tolerance']
            cur_time = chunk_start_time

            for i, chunk_row in chunk_df.iterrows():
                # 如果不是块的第一行，且决定保留间隙，则在当前时间上加上变速后的间隙
                if i != 0 and keep_gaps:
                    cur_time += chunk_df.iloc[i - 1]['gap'] / speed_factor

                new_sub_times = []
                number = chunk_row['number']
                lines = eval(chunk_row['lines']) if isinstance(chunk_row['lines'], str) else chunk_row['lines']

                for line_index, _ in enumerate(lines):
                    # 步骤2: 对块内的每个音频片段进行变速处理
                    temp_file = TEMP_FILE_TEMPLATE.format(f"{number}_{line_index}")
                    output_file = OUTPUT_FILE_TEMPLATE.format(f"{number}_{line_index}")
                    adjust_audio_speed(temp_file, output_file, speed_factor)

                    # 步骤3: 更新时间轴
                    ad_dur = get_audio_duration(output_file)
                    new_sub_times.append([cur_time, cur_time + ad_dur])
                    cur_time += ad_dur

                # 在主DataFrame中找到对应行并更新其新时间轴
                main_df_idx = tasks_df[tasks_df['number'] == chunk_row['number']].index[0]
                tasks_df.at[main_df_idx, 'new_sub_times'] = new_sub_times

            # 步骤4: 打印处理信息
            emoji = "⚡" if speed_factor <= accept else "⚠️"
            rprint(f"[cyan]{emoji} 已处理块 {chunk_start_index}-{index}，统一变速因子: {speed_factor}, 保留间隙: {'是' if keep_gaps else '否'}[/cyan]")

            # 步骤5: 最终容错 - 检查块的总时长是否溢出，并进行裁剪
            if cur_time > chunk_end_time:
                time_diff = cur_time - chunk_end_time
                if time_diff <= 0.6:  # 如果溢出时间在0.6秒内，则裁剪最后一个音频
                    rprint(f"[yellow]⚠️ 块 {chunk_start_index}-{index} 时长溢出 {time_diff:.3f}s，正在裁剪最后一个音频...[/yellow]")
                    last_row_in_chunk = chunk_df.iloc[-1]
                    last_number = last_row_in_chunk['number']
                    last_lines = eval(last_row_in_chunk['lines']) if isinstance(last_row_in_chunk['lines'], str) else last_row_in_chunk['lines']
                    last_line_index = len(last_lines) - 1
                    last_file = OUTPUT_FILE_TEMPLATE.format(f"{last_number}_{last_line_index}")

                    audio = AudioSegment.from_wav(last_file)
                    original_duration_ms = len(audio)
                    new_duration_ms = original_duration_ms - time_diff * 1000
                    trimmed_audio = audio[:int(new_duration_ms)]
                    trimmed_audio.export(last_file, format="wav")

                    # 更新被裁剪音频的结束时间戳
                    main_df_idx = tasks_df[tasks_df['number'] == last_number].index[0]
                    last_times = tasks_df.at[main_df_idx, 'new_sub_times']
                    last_times[-1][1] = chunk_end_time
                    tasks_df.at[main_df_idx, 'new_sub_times'] = last_times

            # 更新下一个块的起始索引
            chunk_start_index = index + 1
    return tasks_df

@check_file_exists(_10_GEN_AUDIO)
def gen_audio_main():
    """主函数：协调TTS生成、音频处理和时间轴对齐的整个流程。"""
    console.print(Panel("[bold cyan]🚀 开始生成最终配音...[/bold cyan]", title="第十步: 生成与对齐音频", expand=False))

    # 准备工作：确保目录存在
    os.makedirs(_AUDIO_TMP_DIR, exist_ok=True)
    os.makedirs(_AUDIO_SEGS_DIR, exist_ok=True)

    # 步骤 1: 加载最终配音任务
    console.print(f"[cyan]- 步骤 1/4: 正在从 `{_8_2_DUB_CHUNKS}` 加载智能配音块任务...[/cyan]")
    tasks_df = pd.read_excel(_8_2_DUB_CHUNKS)
    console.print(f"[green]  ✅ 加载完成，共 {len(tasks_df)} 个配音块待处理。[/green]")

    # 步骤 2: 并行生成TTS音频
    console.print("[cyan]- 步骤 2/4: 正在并行调用TTS引擎生成初始音频...[/cyan]")
    tasks_df = generate_tts_audio(tasks_df)
    failed_tasks = tasks_df[tasks_df['real_dur'] == -1]
    if not failed_tasks.empty:
        console.print(Panel(f"[bold yellow]警告: {len(failed_tasks)} 个任务在TTS生成阶段失败，已标记但流程将继续。[/bold yellow]", title="TTS生成失败"))
    console.print("[green]  ✅ 初始音频生成完成。[/green]")

    # 步骤 3: 智能变速与时间轴重建
    console.print("[cyan]- 步骤 3/4: 正在对音频块进行智能变速和时间轴重建...[/cyan]")
    tasks_df = merge_chunks(tasks_df)
    console.print("[green]  ✅ 所有配音块处理完毕，时间轴已精确对齐。[/green]")

    # 步骤 4: 保存最终结果
    console.print(f"[cyan]- 步骤 4/4: 正在保存最终的音频任务清单到 `{_10_GEN_AUDIO}`...[/cyan]")
    tasks_df.to_excel(_10_GEN_AUDIO, index=False)

    console.print(Panel(f"[bold green]🎉 配音生成与对齐全部完成！[/bold green]", subtitle=f"所有音频片段已保存至 `{_AUDIO_SEGS_DIR}`\n最终数据已保存至 `{_10_GEN_AUDIO}`", expand=False))

if __name__ == '__main__':
    gen_audio_main()
