# -*- coding: utf-8 -*-
"""
音频任务生成与预处理模块

本模块是配音流程的起点，负责将用于配音的SRT字幕文件（源语言和翻译）转换成一个
结构化的任务列表（Excel文件）。这个列表不仅包含了文本和时间戳，还进行了一系列
关键的预处理操作，以确保后续TTS（文本转语音）的质量和效率。

核心功能:
1.  **SRT文件解析 (SRT Parsing)**:
    - `process_srt` 函数读取 `trans_subs_for_audio.srt` (翻译字幕) 和
      `src_subs_for_audio.srt` (源语言字幕) 文件。
    - 它逐块解析SRT内容，提取字幕编号、开始时间、结束时间、持续时长、
      翻译文本和对应的原文。
    - 使用正则表达式去除文本中可能干扰TTS的括号内容和特殊字符。

2.  **字幕时长优化 (Subtitle Duration Optimization)**:
    - **合并过短字幕**: `process_srt` 函数会遍历所有字幕项。如果一条字幕的
      持续时间小于配置文件中设定的 `min_subtitle_duration`，并且它与下一条
      字幕的间隔也很短，系统会自动将这两条字幕合并成一条。这可以避免产生
      过多零碎的音频片段，使配音听起来更自然。
    - **延长过短字幕**: 如果一条过短的字幕无法与下一条合并（例如，它们之间
      间隔较长，或是最后一条字幕），系统会将其时长延长到 `min_subtitle_duration`。
      这为TTS生成音频提供了足够的缓冲时间，防止音频被截断。

3.  **智能文本缩减 (Intelligent Text Trimming)**:
    - `check_len_then_trim` 是一个关键的质量控制函数，但请注意，它在当前版本
      的 `gen_audio_task_main` 中并未被直接调用，而是设计为在后续步骤（如
      `_8_2_dub_chunks.py`）中按需使用。
    - **时长预估**: 它首先使用 `estimate_duration` 函数（来自 `tts_backend`）
      来估算给定文本的朗读时间。
    - **调用LLM缩减**: 如果预估的朗读时间超过了字幕本身允许的最大时长，它会调用
      大型语言模型（LLM），通过一个精心设计的提示（`get_subtitle_trim_prompt`）
      来智能地缩短文本，同时尽可能保持原意。
    - **容错处理**: 如果LLM调用失败（例如，内容触发了安全策略），它会退而求其次，
      采用一个简单的策略：移除所有标点符号来缩短文本。

4.  **任务表生成 (Task Table Generation)**:
    - `gen_audio_task_main` 是主函数，它调用 `process_srt` 生成一个 Pandas DataFrame。
    - 这个DataFrame包含了所有处理过的配音任务，列包括：`number`, `start_time`,
      `end_time`, `duration`, `text` (翻译), `origin` (原文)。
    - 最终，这个DataFrame被保存为 `_8_1_AUDIO_TASK` 定义的Excel文件，供后续的
      配音模块使用。

使用方法:
  运行 `audio_task_main()` 函数，它会自动处理位于 `output/audio/` 目录下的
  SRT文件，并生成 `_8_1_AUDIO_TASK.xlsx` 任务清单。
"""

import datetime
import re
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from rich.table import Table
from core.prompts import get_subtitle_trim_prompt
from core.tts_backend.estimate_duration import init_estimator, estimate_duration
from core.utils import *
from core.utils.models import *

console = Console()
speed_factor = load_key("speed_factor")

# 全局朗读时长估算器实例
ESTIMATOR = None

# ------------------ Helper Functions ------------------

def time_str_to_seconds(time_str: str) -> float:
    """将 HH:MM:SS,ms 格式的时间字符串转换为总秒数。"""
    h, m, s_ms = time_str.split(':')
    s, ms = s_ms.split(',')
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

def seconds_to_time_obj(seconds: float) -> datetime.time:
    """将总秒数转换为 datetime.time 对象。"""
    return (datetime.datetime.min + datetime.timedelta(seconds=seconds)).time()

def parse_srt_to_list(srt_path: str) -> list:
    """解析SRT文件并返回一个字典列表。"""
    if not os.path.exists(srt_path):
        console.log(f"[bold red]错误：SRT文件不存在于 {srt_path}[/bold red]")
        return []
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    subtitles = []
    for block in content.strip().split('\n\n'):
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        if len(lines) < 3:
            continue
        try:
            number = int(lines[0])
            start_str, end_str = lines[1].split(' --> ')
            start_sec = time_str_to_seconds(start_str)
            end_sec = time_str_to_seconds(end_str)
            text = ' '.join(lines[2:])
            text = re.sub(r'\([^)]*\)|（[^）]*）', '', text).strip().replace('-', ' ')
            subtitles.append({
                'number': number,
                'start_time': start_sec,
                'end_time': end_sec,
                'duration': end_sec - start_sec,
                'text': text
            })
        except ValueError as e:
            console.log(Panel(f"无法解析字幕块: '{block}'\n错误: {e}\n将跳过此块。", title="[red]SRT解析错误[/red]", border_style="red"))
    return subtitles

def optimize_subtitle_durations(df: pd.DataFrame) -> pd.DataFrame:
    """合并或延长过短的字幕片段。"""
    if df.empty:
        return df

    min_sub_duration = load_key("min_subtitle_duration", default=1.0)
    processed_rows = []
    i = 0
    
    with Progress(SpinnerColumn(), *Progress.get_default_columns(), "Time Elapsed:", TimeElapsedColumn(), transient=True) as progress:
        task = progress.add_task("[cyan]优化字幕时长...[/cyan]", total=len(df))
        
        while i < len(df):
            current_row = df.iloc[i].to_dict()
            progress.update(task, advance=1)
            
            if current_row['duration'] < min_sub_duration:
                # 如果不是最后一条，且与下一条间隔很近，则合并
                if i < len(df) - 1 and (df.iloc[i+1]['start_time'] - current_row['end_time']) < 0.5:
                    console.log(f"[yellow]合并字幕 #{current_row['number']} 和 #{df.iloc[i+1]['number']} (时长过短)[/yellow]")
                    next_row = df.iloc[i+1]
                    current_row['text'] += ' ' + next_row['text']
                    current_row['origin'] += ' ' + next_row['origin']
                    current_row['end_time'] = next_row['end_time']
                    current_row['duration'] = current_row['end_time'] - current_row['start_time']
                    i += 1 # 跳过下一行，因为它已经被合并
                else:
                    # 否则，延长当前片段的时长
                    console.log(f"[blue]延长字幕 #{current_row['number']} 的时长至 {min_sub_duration}s[/blue]")
                    current_row['end_time'] = current_row['start_time'] + min_sub_duration
                    current_row['duration'] = min_sub_duration
            
            processed_rows.append(current_row)
            i += 1
            
    return pd.DataFrame(processed_rows)

def check_and_trim_text(text: str, duration: float) -> str:
    """检查文本预估时长，如果超限则使用LLM缩减。"""
    global ESTIMATOR
    if ESTIMATOR is None:
        console.log("[yellow]首次调用，正在初始化时长估算器...[/yellow]")
        ESTIMATOR = init_estimator()
    
    max_speed_factor = load_key("speed_factor.max", default=1.5)
    estimated_duration = estimate_duration(text, ESTIMATOR) / max_speed_factor
    
    if estimated_duration > duration:
        console.log(Panel(f"预估时长 [bold yellow]{estimated_duration:.2f}s[/] > 允许时长 [bold blue]{duration:.2f}s[/]。启动LLM文本缩减。\n原始文本: [dim]{text}[/dim]", title="[yellow]时长超限[/yellow]", border_style="yellow", expand=False))
        prompt = get_subtitle_trim_prompt(text, duration)
        
        try:
            response = ask_gpt(prompt, resp_type='json', log_title='sub_trim')
            shortened_text = response.get('result', text)
            if shortened_text == text:
                 console.log("[yellow]LLM未能缩减文本，将采用备用方案：移除标点符号。[/yellow]")
                 return re.sub(r'[,.!?;:，。！？；：]', ' ', text).strip()
            console.log(f"[green]缩减后[/]: [dim]{shortened_text}[/dim]")
            return shortened_text
        except Exception as e:
            console.log(f"[bold red]🚫 LLM调用失败 ({e})，将采用备用方案：移除标点符号。[/bold red]")
            return re.sub(r'[,.!?;:，。！？；：]', ' ', text).strip()
    return text

# ------------------ Main Function -------------------

@check_file_exists(load_key("paths.audio_tasks"))
def audio_task_main():
    """主函数：执行SRT处理并保存结果到Excel文件。"""
    try:
        console.print(Panel("[bold cyan]🎤 开始生成音频任务清单...[/bold cyan]", title="第八步 (1/2): 生成配音任务", expand=False))

        # 步骤 1: 加载和解析SRT
        console.log("[cyan]▶ 步骤 1/4: 加载并解析SRT文件...[/cyan]")
        trans_srt_path = load_key("paths.audio_srt_trans")
        src_srt_path = load_key("paths.audio_srt_src")
        
        trans_subs = parse_srt_to_list(trans_srt_path)
        src_subs_list = parse_srt_to_list(src_srt_path)
        src_subs_map = {item['number']: item['text'] for item in src_subs_list}

        if not trans_subs:
            console.print(Panel("[bold red]未能从翻译SRT文件生成任何任务，请检查输入文件。[/bold red]", title="[red]错误[/red]"))
            return

        df = pd.DataFrame(trans_subs)
        df['origin'] = df['number'].map(src_subs_map).fillna('')
        console.log(f"[green]✅ 成功解析 {len(df)} 条字幕。[/green]")

        # 步骤 2: 优化字幕时长
        console.log("[cyan]▶ 步骤 2/4: 合并与延长过短的字幕...[/cyan]")
        df = optimize_subtitle_durations(df)
        console.log(f"[green]✅ 时长优化完成，当前任务数: {len(df)}。[/green]")

        # 步骤 3: 检查并缩减过长文本 (激活此功能)
        console.log("[cyan]▶ 步骤 3/4: 检查文本时长并使用LLM智能缩减...[/cyan]")
        with Progress(SpinnerColumn(), *Progress.get_default_columns(), transient=True) as progress:
            task = progress.add_task("[cyan]智能缩减文本...[/cyan]", total=len(df))
            df['text'] = df.apply(lambda row: check_and_trim_text(row['text'], row['duration']), axis=1)
            progress.update(task, completed=len(df))
        console.log("[green]✅ 文本智能缩减完成。[/green]")

        # 步骤 4: 保存到Excel
        console.log("[cyan]▶ 步骤 4/4: 保存任务清单到Excel...[/cyan]")
        output_path = load_key("paths.audio_tasks")
        df['start_time'] = df['start_time'].apply(lambda s: seconds_to_time_obj(s).strftime('%H:%M:%S,%f')[:-3])
        df['end_time'] = df['end_time'].apply(lambda s: seconds_to_time_obj(s).strftime('%H:%M:%S,%f')[:-3])
        final_df = df[['number', 'start_time', 'end_time', 'duration', 'text', 'origin']]
        
        final_df.to_excel(output_path, index=False, engine='openpyxl')
        
        # 显示预览
        table = Table(title="前5条音频任务预览")
        table.add_column("编号", justify="right", style="cyan", no_wrap=True)
        table.add_column("开始时间", justify="right", style="magenta")
        table.add_column("结束时间", justify="right", style="magenta")
        table.add_column("时长", justify="right", style="green")
        table.add_column("文本", justify="left", style="green")
        table.add_column("原文", justify="left", style="green")
        
        for row in final_df.head().itertuples(index=False):
            table.add_row(str(row[0]), row[1], row[2], str(row[3]), row[4], row[5])
        
        console.print(table)

        console.print(Panel(f"[bold green]🎉 音频任务清单生成成功！[/bold green]", subtitle=f"文件已保存至: {os.path.abspath(output_path)}", expand=False))

    except Exception as e:
        console.print(Panel(f"[bold red]生成音频任务时发生未知错误: {e}[/bold red]", title="[red]致命错误[/red]"))
        import traceback
        console.print(traceback.format_exc())

if __name__ == '__main__':
    audio_task_main()