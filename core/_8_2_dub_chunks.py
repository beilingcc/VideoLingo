# -*- coding: utf-8 -*-
"""
智能配音分块与语速分析模块

本模块承接 `_8_1_audio_task` 生成的初步音频任务列表，进行深度的时序和语速分析，
旨在通过智能合并字幕行，创建出最适合TTS（文本转语音）处理的“配音块”(dubbing chunks)。
其核心目标是解决单个字幕行时长过短、语速过快的问题，确保生成的配音流畅自然。

核心功能:
1.  **时序与语速分析 (`analyze_subtitle_timing_and_speed`)**:
    - **计算间隙 (Gap Calculation)**: 计算每两行字幕之间的时间间隔（`gap`），
      以及最后一行字幕到视频结尾的间隙。这是判断是否可以合并字幕的关键依据。
    - **容忍时长 (Tolerable Duration)**: 基于`gap`和预设的`TOLERANCE`值，计算出
      每行字幕的“可容忍时长”(`tol_dur`)，即 `duration + tolerance`。这代表了
      TTS生成音频时可以“借用”的额外时间。
    - **预估朗读时长 (Estimated Duration)**: 使用 `estimate_duration` 函数估算
      每行文本的实际朗读时间 (`est_dur`)。
    - **语速状态标记 (`if_too_fast`)**: 基于 `est_dur` 和 `tol_dur`，为每行
      字幕打上语速标记：
        - `2`: 极快。即使调到最大语速也无法在 `tol_dur` 内完成朗读。
        - `1`: 偏快。需要在 `tol_dur` 内完成，需要加速。
        - `0`: 正常。语速在正常范围内。
        - `-1`: 偏慢。朗读时间远小于 `duration`。

2.  **智能切分点处理 (`process_cutoffs` & `merge_rows`)**:
    - **初始化切分点**: 默认在`gap`大于`TOLERANCE`的地方设置切分点 (`cut_off=1`)，
      因为大的停顿通常是天然的分割点。
    - **合并逻辑**: 遍历字幕行，当遇到语速正常或偏慢的行，如果下一行语速也正常或偏慢，
      则当前行可独立为一个片段。如果下一行语速偏快，则触发 `merge_rows` 合并逻辑。
      当遇到语速偏快的行，也触发 `merge_rows`。
    - **`merge_rows`**: 这是一个迭代合并函数。它会从一个起始行开始，不断向后合并
      后续行（最多合并`MAX_MERGE_COUNT`行），并在每一步都重新计算合并后片段的
      总`est_dur`和总`tol_dur`。合并会持续到以下任一条件满足：
        - 合并后的片段语速变为正常或偏慢 (`speed_flag <= 0`)。
        - 达到预设的合并上限。
      一旦找到合适的合并终点，就在该行打上 `cut_off=1` 标记。

3.  **生成最终配音块 (`gen_dub_chunks`)**:
    - **加载与分析**: 加载 `_8_1_AUDIO_TASK.xlsx`，并调用上述分析和处理函数。
    - **文本匹配与重组**: 由于分析过程中合并了行，需要将原始SRT文件中的多行文本
      重新组合，以匹配合并后的DataFrame行。它通过 `clean_text` 清理并拼接
      原始SRT行，直到与DataFrame中合并后的`text`字段完全匹配。
    - **保存结果**: 将带有`cut_off`标记、合并后文本以及原始文本行的DataFrame
      保存为 `_8_2_DUBBING_TASK.xlsx`，供后续的TTS模块使用。

使用方法:
  运行 `gen_dub_chunks()` 函数，它会读取 `_8_1_AUDIO_TASK.xlsx`，执行分析和合并，
  并生成最终的配音任务块文件 `_8_2_DUBBING_TASK.xlsx`。
"""

import datetime
import re
import pandas as pd
from core._8_1_audio_task import time_diff_seconds
from core.asr_backend.audio_preprocess import get_audio_duration
from core.tts_backend.estimate_duration import init_estimator, estimate_duration
from core.utils import *
from core.utils.models import *

# 定义输入/输出文件和常量
SRC_SRT = "output/src.srt"
TRANS_SRT = "output/trans.srt"
MAX_MERGE_COUNT = 5  # 单次合并的最大行数
ESTIMATOR = None     # 全局时长估算器实例

def calc_if_too_fast(est_dur: float, tol_dur: float, duration: float, tolerance: float) -> int:
    """
    计算语速状态标记。

    返回:
        int: 2 (极快), 1 (偏快), 0 (正常), -1 (偏慢)
    """
    accept_speed = load_key("speed_factor.accept")
    if est_dur / accept_speed > tol_dur:  # 即使在最大可接受语速下也超时
        return 2
    elif est_dur > tol_dur:  # 需要在可接受范围内加速
        return 1
    elif est_dur < duration - tolerance:  # 语速过慢
        return -1
    else:  # 语速正常
        return 0

def merge_rows(df: pd.DataFrame, start_idx: int, merge_count: int) -> int:
    """
    从 start_idx 开始，向后合并多行字幕，直到找到一个合适的切分点。

    参数:
        df (pd.DataFrame): 包含字幕信息的DataFrame。
        start_idx (int): 开始合并的行索引。
        merge_count (int): 初始合并计数（通常为1）。

    返回:
        int: 合并的总行数。
    """
    # 初始化合并后的累计值
    merged = {
        'est_dur': df.iloc[start_idx]['est_dur'],
        'tol_dur': df.iloc[start_idx]['tol_dur'],
        'duration': df.iloc[start_idx]['duration']
    }
    
    # 循环合并，直到达到上限或找到切点
    while merge_count < MAX_MERGE_COUNT and (start_idx + merge_count) < len(df):
        next_row = df.iloc[start_idx + merge_count]
        merged['est_dur'] += next_row['est_dur']
        merged['tol_dur'] += next_row['tol_dur']
        merged['duration'] += next_row['duration']
        
        # 重新计算合并后的语速状态
        speed_flag = calc_if_too_fast(
            merged['est_dur'], merged['tol_dur'], merged['duration'],
            df.iloc[start_idx + merge_count]['tolerance']
        )
        
        # 如果语速正常/偏慢，或达到一定合并数量，则设置切点并返回
        if speed_flag <= 0 or merge_count == 2:
            df.at[start_idx + merge_count, 'cut_off'] = 1
            return merge_count + 1
        
        merge_count += 1
    
    # 如果循环结束仍未找到切点（例如，一直过快），则在最后合并的位置强制切分
    if merge_count >= MAX_MERGE_COUNT or (start_idx + merge_count) >= len(df):
        df.at[start_idx + merge_count - 1, 'cut_off'] = 1
    return merge_count

def analyze_subtitle_timing_and_speed(df: pd.DataFrame) -> pd.DataFrame:
    """分析字幕时序、计算间隙、容忍时长、预估朗读时长和语速状态。"""
    rprint("[🔍 分析] 正在计算字幕时序和语速...")
    global ESTIMATOR
    if ESTIMATOR is None: ESTIMATOR = init_estimator()
    
    TOLERANCE = load_key("tolerance")
    whole_dur = get_audio_duration(_RAW_AUDIO_FILE)
    
    # 计算每行字幕后的间隙时间
    df['gap'] = 0.0
    df['end_time_dt'] = pd.to_datetime(df['end_time_str'], format='%H:%M:%S,%f').dt.time
    df['start_time_dt'] = pd.to_datetime(df['start_time_str'], format='%H:%M:%S,%f').dt.time
    
    for i in range(len(df) - 1):
        df.loc[i, 'gap'] = time_diff_seconds(df.loc[i, 'end_time_dt'], df.loc[i + 1, 'start_time_dt'], datetime.date.today())
    
    last_end_seconds = df.iloc[-1]['end_time_dt'].hour * 3600 + df.iloc[-1]['end_time_dt'].minute * 60 + df.iloc[-1]['end_time_dt'].second + df.iloc[-1]['end_time_dt'].microsecond / 1e6
    df.iloc[-1, df.columns.get_loc('gap')] = whole_dur - last_end_seconds
    
    # 计算容忍时长和预估朗读时长
    df['tolerance'] = df['gap'].apply(lambda x: min(x, TOLERANCE))
    df['tol_dur'] = df['duration'] + df['tolerance']
    df['est_dur'] = df.apply(lambda x: estimate_duration(x['text'], ESTIMATOR), axis=1)

    # 计算语速状态标记
    df['if_too_fast'] = df.apply(lambda row: calc_if_too_fast(row['est_dur'], row['tol_dur'], row['duration'], row['tolerance']), axis=1)
    return df.drop(columns=['end_time_dt', 'start_time_dt'])

def process_cutoffs(df: pd.DataFrame) -> pd.DataFrame:
    """根据语速状态和合并逻辑，生成最终的切分点。"""
    rprint("[✂️ 处理] 正在生成切分点...")
    df['cut_off'] = 0
    df.loc[df['gap'] >= load_key("tolerance"), 'cut_off'] = 1  # 优先在长间隙处切分
    
    idx = 0
    while idx < len(df):
        if df.iloc[idx]['cut_off'] == 1:
            if df.iloc[idx]['if_too_fast'] == 2:
                rprint(f"[⚠️ 警告] 第 {idx} 行语速极快，无法通过调速修复。")
            idx += 1
            continue

        if idx + 1 >= len(df):
            df.at[idx, 'cut_off'] = 1; break

        if df.iloc[idx]['if_too_fast'] <= 0: # 当前行语速正常或偏慢
            if df.iloc[idx + 1]['if_too_fast'] <= 0: # 下一行也正常或偏慢
                df.at[idx, 'cut_off'] = 1 # 当前行可独立成块
                idx += 1
            else: # 下一行偏快，需要合并
                idx += merge_rows(df, idx, 1)
        else: # 当前行偏快，需要合并
            idx += merge_rows(df, idx, 1)
    
    return df

@check_file_exists(_8_2_DUBBING_TASK)
def dub_chunks_main():
    """主函数：生成最终的配音任务块。"""
    console.print(Panel("[bold cyan]🧠 开始生成智能配音块...[/bold cyan]", title="第八步 (2/2): 优化配音分块", expand=False))

    # 步骤 1: 加载初级任务
    console.print(f"[cyan]- 步骤 1/4: 正在从 `{_8_1_AUDIO_TASK}` 加载音频任务...[/cyan]")
    df = pd.read_excel(_8_1_AUDIO_TASK)
    console.print(f"[green]  ✅ 加载完成，共 {len(df)} 条初级任务。[/green]")

    # 步骤 2: 分析时序与语速
    console.print("[cyan]- 步骤 2/4: 正在进行时序与语速分析...[/cyan]")
    df = analyze_subtitle_timing_and_speed(df)
    fast_count = len(df[df['if_too_fast'] > 0])
    console.print(f"[green]  ✅ 分析完成，识别出 {fast_count} 条语速可能过快的字幕。[/green]")

    # 步骤 3: 智能合并与切分
    console.print("[cyan]- 步骤 3/4: 正在智能合并字幕以优化语速...[/cyan]")
    df = process_cutoffs(df)
    final_df = df[df['cut_off'] == 1].copy()
    console.print(f"[green]  ✅ 合并完成，生成 {len(final_df)} 个最终配音块。[/green]")

    # 步骤 4: 匹配原始文本并保存
    console.print("[cyan]- 步骤 4/4: 正在匹配原始文本并保存最终任务清单...[/cyan]")
    with open(TRANS_SRT, "r", encoding="utf-8") as f: content = f.read()
    with open(SRC_SRT, "r", encoding="utf-8") as f: ori_content = f.read()
    
    def get_lines_from_srt(srt_content):
        lines_list = []
        for block in srt_content.strip().split('\n\n'):
            lines = [line.strip() for line in block.split('\n') if line.strip()]
            if len(lines) >= 3:
                text = ' '.join(lines[2:])
                text = re.sub(r'\([^)]*\)|（[^）]*）', '', text).strip().replace('-', '')
                lines_list.append(text)
        return lines_list

    content_lines = get_lines_from_srt(content)
    ori_content_lines = get_lines_from_srt(ori_content)

    final_df['lines'] = None
    final_df['src_lines'] = None
    last_idx = 0

    def clean_text(text):
        return re.sub(r'[^\w\s]|\s', '', str(text)) if text else ''

    # 重置索引以便于遍历
    final_df.reset_index(drop=True, inplace=True)
    temp_df = df.copy()
    temp_df.reset_index(drop=True, inplace=True)
    original_indices = final_df['number'].apply(lambda x: temp_df[temp_df['number'] == x].index[0])

    for i, (final_idx, row) in enumerate(final_df.iterrows()):
        start_original_idx = original_indices[i]
        if i + 1 < len(original_indices):
            end_original_idx = original_indices[i+1]
        else:
            end_original_idx = len(df)
        
        merged_rows = df.iloc[start_original_idx:end_original_idx]
        
        lines_to_match = list(merged_rows['number'] - 1) # srt number is 1-based
        final_df.at[final_idx, 'lines'] = [content_lines[j] for j in lines_to_match]
        final_df.at[final_idx, 'src_lines'] = [ori_content_lines[j] for j in lines_to_match]

    final_df.to_excel(_8_2_DUBBING_TASK, index=False)
    console.print(Panel(f"[bold green]🎉 智能配音块生成成功！[/bold green]", subtitle=f"最终任务文件已保存至: {_8_2_DUBBING_TASK}", expand=False))

if __name__ == '__main__':
    dub_chunks_main()