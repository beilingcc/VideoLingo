# -*- coding: utf-8 -*-
"""
并行翻译模块

本模块负责将经过语义分割的文本块进行高效的并行翻译。其设计旨在最大化翻译效率，
同时通过上下文感知来保证翻译质量和连贯性。

核心功能:
1.  **文本分块 (Chunking)**:
    - `split_chunks_by_chars`: 将完整的文本（来自 `_3_2_SPLIT_BY_MEANING` 的输出）
      按照指定的字符数和最大行数分割成适合并行处理的文本块（chunks）。
      这样做是为了平衡 API 调用开销和上下文长度，避免单个请求过大或过小。

2.  **上下文感知翻译 (Context-Aware Translation)**:
    - `get_previous_content` / `get_after_content`: 为每个待翻译的文本块提取其
      前几行和后几行的内容作为上下文。这对于处理跨越多行的句子、解决代词指代
      不清等问题至关重要，能显著提升翻译的连贯性和准确性。
    - `translate_chunk`: 单个文本块的翻译单元。它整合了原文、上下文、以及从
      `_4_1_summarize` 模块获取的主题和术语表，然后调用 `translate_lines` 函数
      （通常是与 LLM API 交互的封装）来获取翻译结果。

3.  **并行处理 (Concurrent Execution)**:
    - 利用 `concurrent.futures.ThreadPoolExecutor` 实现对多个文本块的并行翻译请求。
      这极大地缩短了总翻译时间，特别是对于长视频。
    - `max_workers` 参数可以从配置中加载，允许用户根据自己的网络和 API 限制
      来调整并发级别。

4.  **结果整合与校验 (Result Integration and Validation)**:
    - `similar`: 使用 `difflib.SequenceMatcher` 计算原文块和返回的翻译结果中原文部分
      的相似度。这是一个关键的校验步骤，用于确保 LLM 返回的结果与我们发送的请求
      是正确对应的，防止因 API 问题或并发处理导致的数据错乱。
    - 在收集完所有并行任务的结果后，按原始顺序排序，并通过相似度匹配将翻译
      结果与原文块一一对应。如果相似度低于阈值，将抛出异常，防止错误的翻译
      内容进入后续流程。

5.  **时间戳对齐与后处理 (Timestamp Alignment and Post-processing)**:
    - `align_timestamp`: 将翻译好的文本与原始的带时间戳的 ASR 结果进行对齐，
      生成用于制作字幕的 SRT 文件格式所需的数据结构。
    - `check_len_then_trim`: 对翻译后的文本进行长度检查，如果译文相对于其
      对应的时间戳过长，会进行智能裁剪，以保证字幕的显示效果。

6.  **结果保存 (Saving Results)**:
    - 最终将包含原文、译文和时间戳的 DataFrame 保存到 Excel 文件
      (`_4_2_TRANSLATION`) 中，供后续生成音频和视频的模块使用。

使用方法:
  运行 `translate_all()` 函数即可启动整个翻译流程。这是一个自动化的、端到端的
  翻译步骤，是整个视频翻译流程中的核心环节。
"""

import pandas as pd
import json
import concurrent.futures
from difflib import SequenceMatcher
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from core.translate_lines import translate_lines
from core._8_1_audio_task import check_len_then_trim
from core._6_gen_sub import align_timestamp
from core.utils import *
from core.utils.models import *

console = Console()

def split_chunks_by_chars(chunk_size: int, max_i: int) -> list[str]:
    """
    根据字符数和最大行数将文本分割成块。
    """
    with open(_3_2_SPLIT_BY_MEANING, "r", encoding="utf-8") as file:
        sentences = file.read().strip().split('\n')

    chunks = []
    current_chunk = ''
    sentence_count = 0
    for sentence in sentences:
        if len(current_chunk) + len(sentence + '\n') > chunk_size or sentence_count >= max_i:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + '\n'
            sentence_count = 1
        else:
            current_chunk += sentence + '\n'
            sentence_count += 1
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks

def get_previous_content(chunks: list[str], chunk_index: int) -> list[str] or None:
    """获取当前块之前的内容作为上下文（前3行）。"""
    if chunk_index == 0:
        return None
    return chunks[chunk_index - 1].split('\n')[-3:]

def get_after_content(chunks: list[str], chunk_index: int) -> list[str] or None:
    """获取当前块之后的内容作为上下文（后2行）。"""
    if chunk_index >= len(chunks) - 1:
        return None
    return chunks[chunk_index + 1].split('\n')[:2]

def translate_chunk(chunk: str, chunks: list[str], theme_prompt: str, terms: list[dict], i: int) -> tuple[int, str, str]:
    """
    翻译单个文本块，并整合上下文信息和术语提示。
    """
    # 从预加载的术语列表中搜索需要特别注意的术语
    things_to_note_list = [term for term in terms if term.get('src', '').lower() in chunk.lower()]
    things_to_note_prompt = None
    if things_to_note_list:
        things_to_note_prompt = '\n'.join(
            f'{idx+1}. "{term["src"]}": "{term["tgt"]}", meaning: {term["note"]}'
            for idx, term in enumerate(things_to_note_list)
        )
    
    previous_content_prompt = get_previous_content(chunks, i)
    after_content_prompt = get_after_content(chunks, i)
    
    translation, english_result = translate_lines(chunk, previous_content_prompt, after_content_prompt, things_to_note_prompt, theme_prompt, i)
    return i, english_result, translation

def similar(a: str, b: str) -> float:
    """计算两个字符串的相似度。"""
    return SequenceMatcher(None, a, b).ratio()

@check_file_exists(_4_2_TRANSLATION)
def translate_main():
    """
    执行所有文本块的翻译主流程。
    """
    console.print(Panel("🚀 [bold cyan]启动并行翻译流程[/bold cyan]", 
                        title="[bold]步骤 4.2[/bold]", subtitle="[bold]并行翻译[/bold]", expand=False))
    try:
        # 步骤 1: 文本分块
        console.log("步骤 1/6: 正在将文本分割成适合翻译的块...")
        chunks = split_chunks_by_chars(chunk_size=600, max_i=10)
        console.log(f"[green]  ✓ 文本已成功分割成 {len(chunks)} 个块。[/green]")

        # 步骤 2: 加载术语和主题
        console.log("步骤 2/6: 正在加载术语表和主题提示...")
        with open(_4_1_TERMINOLOGY, 'r', encoding='utf-8') as file:
            terminology_data = json.load(file)
            theme_prompt = terminology_data.get('theme')
            terms_list = terminology_data.get('terms', [])
        console.log(f"[green]  ✓ 术语表加载完成。[/green]")

        # 步骤 3: 并行翻译
        console.log(f"步骤 3/6: 正在启动并行翻译... (共 {len(chunks)} 个任务)")
        results = []
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}{task.percentage:>3.0f}%"), transient=False) as progress:
            task = progress.add_task("[cyan]翻译中...[/cyan]", total=len(chunks))
            with concurrent.futures.ThreadPoolExecutor(max_workers=load_key("max_workers")) as executor:
                futures = [executor.submit(translate_chunk, chunk, chunks, theme_prompt, terms_list, i) for i, chunk in enumerate(chunks)]
                
                for future in concurrent.futures.as_completed(futures):
                    results.append(future.result())
                    progress.update(task, advance=1)
        console.log(f"[green]  ✓ 所有翻译任务已完成。[/green]")

        # 步骤 4: 结果排序与校验
        console.log("步骤 4/6: 正在对翻译结果进行排序和校验...")
        results.sort(key=lambda x: x[0])
        
        src_text, trans_text = [], []
        for i, chunk in enumerate(chunks):
            chunk_lines = chunk.split('\n')
            src_text.extend(chunk_lines)
            
            chunk_text_lower = ''.join(chunk_lines).lower()
            matching_results = [(r, similar(''.join(r[1].split('\n')).lower(), chunk_text_lower)) for r in results]
            best_match = max(matching_results, key=lambda x: x[1])
            
            if best_match[1] < 0.9:
                raise ValueError(f"翻译匹配失败 (块 {i})，最佳匹配相似度: {best_match[1]:.3f}")
            elif best_match[1] < 0.99:
                console.log(f"[yellow]  ⚠️ 警告: 找到块 {i} 的近似匹配 (相似度: {best_match[1]:.3f})[/yellow]")
                
            trans_text.extend(best_match[0][2].split('\n'))
        console.log("[green]  ✓ 结果校验成功，所有翻译块均已正确匹配。[/green]")

        # 步骤 5: 时间戳对齐与译文裁剪
        console.log("步骤 5/6: 正在进行时间戳对齐和译文长度裁剪...")
        df_text = pd.read_excel(_2_CLEANED_CHUNKS)
        df_text['text'] = df_text['text'].str.strip('"').str.strip()
        df_translate = pd.DataFrame({'Source': src_text, 'Translation': trans_text})
        
        subtitle_output_configs = [('trans_subs_for_audio.srt', ['Translation'])]
        df_time = align_timestamp(df_text, df_translate, subtitle_output_configs, output_dir=None, for_display=False)
        
        df_time['Translation'] = df_time.apply(
            lambda row: check_len_then_trim(row['Translation'], row['duration']) 
            if row['duration'] > load_key("min_trim_duration") else row['Translation'], 
            axis=1
        )
        console.log("[green]  ✓ 时间戳对齐和译文裁剪完成。[/green]")

        # 步骤 6: 保存最终结果
        console.log("步骤 6/6: 正在保存最终翻译结果...")
        df_time.to_excel(_4_2_TRANSLATION, index=False)
        console.print(Panel(f"✅ [bold green]翻译流程全部完成！[/bold green]\n结果已保存至 '{_4_2_TRANSLATION}'", 
                            title="[bold green]成功[/bold green]", expand=True))

    except Exception as e:
        console.print(Panel(f"翻译过程中发生意外错误: {e}", title="[bold red]错误[/bold red]", expand=True))
        raise

if __name__ == '__main__':
    translate_main()