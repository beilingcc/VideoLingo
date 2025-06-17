# -*- coding: utf-8 -*-
"""
字幕生成与时间戳对齐模块

本模块的核心任务是将经过分割和翻译的文本，与原始ASR（自动语音识别）产生的
逐词时间戳进行精确对齐，最终生成行业标准的SRT格式字幕文件。这是将翻译内容
与视频画面同步的关键步骤。

核心功能:
1.  **时间戳格式转换 (Timestamp Formatting)**:
    - `convert_to_srt_format`: 将以秒为单位的时间戳（浮点数）转换为SRT文件
      要求的 `小时:分钟:秒,毫秒` 格式。

2.  **文本清洗 (Text Cleaning)**:
    - `remove_punctuation`: 一个用于对齐算法的辅助函数，它移除文本中的标点
      符号和多余空格，并将所有字符转为小写。这使得后续的字符串匹配更加鲁棒，
      能忽略因标点或大小写差异导致的不匹配。

3.  **核心对齐算法 (Core Alignment Algorithm)**:
    - `get_sentence_timestamps`: 这是整个模块最关键的函数。其工作原理如下：
      a. **构建词汇长字符串**: 将ASR识别出的所有单词（来自 `_2_CLEANED_CHUNKS`）
         清洗后拼接成一个连续的、无空格的长字符串 (`full_words_str`)。
      b. **建立位置映射**: 在构建过程中，创建一个字典 (`position_to_word_idx`)，
         将长字符串中每个字符的位置映射回它所属的原始单词的索引。
      c. **滑动窗口匹配**: 遍历待对齐的句子（来自 `_5_SPLIT_SUB` 或 `_5_REMERGED`），
         同样进行清洗。然后，使用一个滑动窗口在 `full_words_str` 上查找与当前
         句子完全匹配的子串。
      d. **提取时间戳**: 一旦找到匹配，就利用 `position_to_word_idx` 字典，
         获取匹配子串的起始字符和结束字符所对应的原始单词索引。通过这些索引，
         就可以从ASR的词级时间戳数据中，精确地找出该句子的开始时间和结束时间。
      e. **错误处理**: 如果找不到精确匹配，`show_difference` 函数会被调用，
         清晰地展示预期句子和实际匹配内容之间的差异，并抛出异常，便于调试。

4.  **字幕微调 (Subtitle Refinement)**:
    - `align_timestamp` 函数中包含一个“消除间隙”的逻辑。它会检查相邻字幕间
      的微小时间间隔（小于1秒），并将前一条字幕的结束时间延长到后一条字幕的
      开始时间，使得字幕显示更加连贯，避免不必要的闪烁。
    - `clean_translation`: 使用 `autocorrect_py` 库对翻译文本进行自动校正和
      格式化，例如修正标点、调整空格等，提升字幕的美观度。

5.  **SRT文件生成 (SRT File Generation)**:
    - `align_timestamp_main` 是主流程函数。它分别处理用于视频显示的字幕
      （来自 `_5_SPLIT_SUB`）和用于音频生成的字幕（来自 `_5_REMERGED`）。
    - 根据预设的配置（`SUBTITLE_OUTPUT_CONFIGS`），它可以生成多种组合的SRT文件，
      如仅原文、仅译文、或双语字幕，并将它们保存在指定的输出目录中。

使用方法:
  运行 `align_timestamp_main()` 函数，它会自动加载所需的数据文件，执行对齐和
  生成操作，最终在 `output` 和 `audio` 目录下创建多个SRT字幕文件。
"""

import pandas as pd
import os
import re
from rich.panel import Panel
from rich.console import Console
from rich.progress import Progress
from difflib import SequenceMatcher, ndiff
import autocorrect_py as autocorrect
from core.utils import *
from core.utils.models import *

console = Console()

# 为视频播放器配置的字幕输出格式
SUBTITLE_OUTPUT_CONFIGS = [
    ('src.srt', ['Source']),  # 仅源语言
    ('trans.srt', ['Translation']),  # 仅目标语言
    ('src_trans.srt', ['Source', 'Translation']),  # 源语言在上，目标语言在下
    ('trans_src.srt', ['Translation', 'Source'])  # 目标语言在上，源语言在下
]

# 为后续音频生成准备的字幕文件
AUDIO_SUBTITLE_OUTPUT_CONFIGS = [
    ('src_subs_for_audio.srt', ['Source']),
    ('trans_subs_for_audio.srt', ['Translation'])
]

def convert_to_srt_format(start_time: float, end_time: float) -> str:
    """将秒数转换为SRT时间码格式 (时:分:秒,毫秒)。"""
    def seconds_to_hmsm(seconds):
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        milliseconds = int((seconds * 1000) % 1000)
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d},{milliseconds:03d}"

    return f"{seconds_to_hmsm(start_time)} --> {seconds_to_hmsm(end_time)}"

def remove_punctuation(text: str) -> str:
    """移除文本中的标点符号和多余空格，并转为小写，用于模糊匹配。"""
    text = re.sub(r'\s+', ' ', str(text))
    text = re.sub(r'[^\w\s]', '', text)
    return text.lower().strip()

def show_difference(str1: str, str2: str):
    """在控制台清晰地展示两个字符串之间的差异，便于调试。"""
    diffs = list(ndiff(str1, str2))
    line1, line2, marker = '', '', ''
    for d in diffs:
        op, char = d[0], d[2]
        if op == ' ': line1 += char; line2 += char; marker += ' '
        elif op == '-': line1 += f"[on red]{char}[/on red]"; line2 += ' '; marker += '^'
        elif op == '+': line1 += ' '; line2 += f"[on green]{char}[/on green]"; marker += '^'
    console.print(f"预期句子: {line1}")
    console.print(f"实际匹配: {line2}")
    console.print(f"差异标记: [bold yellow]{marker}[/bold yellow]")

def get_sentence_timestamps(df_words: pd.DataFrame, df_sentences: pd.DataFrame) -> list:
    """核心算法：通过匹配清洗后的句子和单词，为每个句子找到精确的起止时间戳。"""
    time_stamp_list = []
    console.log("  - 正在构建词汇索引...")
    full_words_str = ''
    position_to_word_idx = {}
    for idx, word in enumerate(df_words['text']):
        clean_word = remove_punctuation(word)
        start_pos = len(full_words_str)
        full_words_str += clean_word
        for pos in range(start_pos, len(full_words_str)):
            position_to_word_idx[pos] = idx
    
    console.log("  - 正在对齐句子时间戳...")
    current_pos = 0
    with Progress(transient=True) as progress:
        task = progress.add_task("[cyan]对齐中...[/cyan]", total=len(df_sentences))
        for idx, sentence in df_sentences['Source'].items():
            clean_sentence = remove_punctuation(sentence).replace(" ", "")
            sentence_len = len(clean_sentence)
            if not clean_sentence:
                time_stamp_list.append((0.0, 0.0))
                progress.update(task, advance=1)
                continue

            match_found = False
            search_pos = current_pos
            while search_pos <= len(full_words_str) - sentence_len:
                if full_words_str[search_pos : search_pos + sentence_len] == clean_sentence:
                    start_word_idx = position_to_word_idx[search_pos]
                    end_word_idx = position_to_word_idx[search_pos + sentence_len - 1]
                    time_stamp_list.append((float(df_words['start'][start_word_idx]), float(df_words['end'][end_word_idx])))
                    current_pos = search_pos + sentence_len
                    match_found = True
                    break
                search_pos += 1
                
            if not match_found:
                console.print(f"\n[bold red]⚠️ 警告: 未能为句子找到精确的时间戳匹配:[/bold red]\n'{sentence}'")
                search_area = full_words_str[current_pos:]
                matcher = SequenceMatcher(None, clean_sentence, search_area)
                match = matcher.find_longest_match(0, len(clean_sentence), 0, len(search_area))
                best_match_str = search_area[match.b : match.b + len(clean_sentence)]
                show_difference(clean_sentence, best_match_str)
                raise ValueError("❎ 无法对齐时间戳，请检查源文本或ASR结果。")
            
            progress.update(task, advance=1)
    return time_stamp_list

def align_timestamp(df_text: pd.DataFrame, df_translate: pd.DataFrame, subtitle_output_configs: list, output_dir: str, for_display: bool = True):
    """将时间戳对齐到翻译数据上，并生成SRT文件。"""
    df_trans_time = df_translate.copy()
    time_stamp_list = get_sentence_timestamps(df_text, df_translate)
    df_trans_time['timestamp'] = time_stamp_list
    df_trans_time['duration'] = df_trans_time['timestamp'].apply(lambda x: x[1] - x[0])

    console.log("  - 正在消除字幕间的小于1秒的间隙...")
    for i in range(len(df_trans_time) - 1):
        delta_time = df_trans_time.loc[i + 1, 'timestamp'][0] - df_trans_time.loc[i, 'timestamp'][1]
        if 0 < delta_time < 1:
            df_trans_time.at[i, 'timestamp'] = (df_trans_time.loc[i, 'timestamp'][0], df_trans_time.loc[i + 1, 'timestamp'][0])

    df_trans_time['timestamp_srt'] = df_trans_time['timestamp'].apply(lambda x: convert_to_srt_format(x[0], x[1]))

    if for_display:
        df_trans_time['Translation'] = df_trans_time['Translation'].apply(lambda x: re.sub(r'[，。]', ' ', str(x)).strip())

    def generate_subtitle_string(df, columns):
        parts = []
        for i, row in df.iterrows():
            text_parts = [str(row[col]).strip() for col in columns if pd.notna(row[col])]
            if not text_parts: continue
            parts.append(f"{i+1}\n{row['timestamp_srt']}\n{'\n'.join(text_parts)}\n")
        return "\n".join(parts)

    console.log(f"  - 正在写入 {len(subtitle_output_configs)} 个SRT文件到 `{output_dir}`...")
    os.makedirs(output_dir, exist_ok=True)
    for filename, columns in subtitle_output_configs:
        subtitle_str = generate_subtitle_string(df_trans_time, columns)
        with open(os.path.join(output_dir, filename), 'w', encoding='utf-8') as f:
            f.write(subtitle_str)
    return df_trans_time

def clean_translation(x):
    """对翻译文本进行清洗和自动校正。"""
    if pd.isna(x): return ''
    cleaned = str(x).strip('。').strip('，')
    return autocorrect.format(cleaned)

@check_file_exists(
    *[os.path.join(_SUBTITLE_DIR, cfg[0]) for cfg in SUBTITLE_OUTPUT_CONFIGS],
    *[os.path.join(_AUDIO_DIR, cfg[0]) for cfg in AUDIO_SUBTITLE_OUTPUT_CONFIGS]
)
def gen_sub_main():
    """字幕生成和时间戳对齐的主函数。"""
    console.print(Panel("🎬 [bold cyan]启动字幕生成与时间戳对齐流程[/bold cyan]", 
                        title="[bold]步骤 6[/bold]", subtitle="[bold]生成字幕[/bold]", expand=False))
    try:
        console.log("步骤 1/3: 正在加载所需数据...")
        df_text = pd.read_csv(_2_CLEANED_CHUNKS)
        df_sub_for_display = pd.read_excel(_5_SPLIT_SUB)
        df_sub_for_audio = pd.read_excel(_5_REMERGED)
        console.log(f"[green]  ✓ 已成功加载 ASR 词语时间戳 (来自 `{_2_CLEANED_CHUNKS}`)[/green]")
        console.log(f"[green]  ✓ 已成功加载视频显示字幕 (来自 `{_5_SPLIT_SUB}`)[/green]")
        console.log(f"[green]  ✓ 已成功加载音频生成字幕 (来自 `{_5_REMERGED}`)[/green]")

        df_sub_for_audio.rename(columns={'Remerged': 'Source'}, inplace=True)
        df_sub_for_audio['Translation'] = df_sub_for_audio['Source']

        console.log("步骤 2/3: 正在生成用于视频播放的SRT字幕...")
        align_timestamp(df_text, df_sub_for_display, SUBTITLE_OUTPUT_CONFIGS, _SUBTITLE_DIR, for_display=True)
        console.log(f"[green]  ✓ 视频字幕文件已生成并保存至 `{_SUBTITLE_DIR}` 目录。[/green]")

        console.log("步骤 3/3: 正在生成用于TTS语音合成的SRT字幕...")
        align_timestamp(df_text, df_sub_for_audio, AUDIO_SUBTITLE_OUTPUT_CONFIGS, _AUDIO_DIR, for_display=False)
        console.log(f"[green]  ✓ 音频字幕文件已生成并保存至 `{_AUDIO_DIR}` 目录。[/green]")

        final_message = (f"🎉 [bold green]字幕生成流程成功完成！[/bold green]\n"
                         f"  - 视频播放器字幕保存在: `{_SUBTITLE_DIR}`\n"
                         f"  - 语音合成用字幕保存在: `{_AUDIO_DIR}`")
        console.print(Panel(final_message, title="[bold green]成功[/bold green]", expand=True))

    except Exception as e:
        console.print(Panel(f"字幕生成过程中发生意外错误: {e}", title="[bold red]错误[/bold red]", expand=True))
        raise

if __name__ == '__main__':
    gen_sub_main()