# -*- coding: utf-8 -*-
"""
智能字幕分割模块

本模块旨在解决机器翻译后字幕行过长的问题。由于源语言和目标语言在表达方式上
的差异，一句原文对应的译文可能会变得很长，不适合作为单条字幕显示。本模块通过
一个迭代的、基于LLM的对齐与分割流程，将过长的字幕行切分为多条符合长度限制的
短字幕行。

核心功能:
1.  **长度计算与识别 (Length Calculation and Identification)**:
    - `calc_len`: 一个加权字符长度计算函数。它为不同语言（如中文、日文、韩文）
      及全角/半角符号分配不同的权重，从而更准确地估算文本在屏幕上的显示宽度，
      这比简单的 `len()` 函数更适合多语言字幕处理。
    - `split_align_subs` 首先会遍历所有字幕行，使用 `calc_len` 和配置中的
      `max_length` 来识别哪些原文或译文行需要被分割。

2.  **基于LLM的智能对齐与分割 (LLM-based Smart Alignment and Splitting)**:
    - 当一条字幕被识别为过长时，流程如下：
      a. `split_sentence`: 首先，使用 `_3_2_split_meaning` 中的语义分割功能，
         将过长的 *原文* 行尝试分割成两个语义连贯的部分。
      b. `align_subs`: 这是核心的智能对齐步骤。它构造一个 Prompt，将原始的
         “原文-译文”对以及刚刚分割好的 *原文部分* 一同发送给 LLM。Prompt 指示
         LLM 理解原文的分割方式，并据此将对应的 *译文* 也分割成两个语义匹配的
         部分。
      c. LLM 返回对齐分割后的译文部分。这样，原来的一条长字幕就被智能地拆分
         成了两条或多条短字幕，且原文和译文的对应关系得以保持。

3.  **迭代处理 (Iterative Processing)**:
    - `split_for_sub_main`: 主函数采用了一个循环结构（最多3次尝试）。在每次
      迭代中，它都会调用 `split_align_subs` 来处理当前所有过长的行。因为一次
      分割可能产生新的、仍然过长的行，所以需要多次迭代，直到所有字幕行都满足
      长度要求为止。

4.  **并行执行 (Concurrent Execution)**:
    - 对于识别出的多个需要分割的字幕行，本模块使用 `concurrent.futures.ThreadPoolExecutor`
      来并行地向 LLM 发送对齐请求，以提高处理效率。

5.  **结果保存 (Saving Results)**:
    - `_5_SPLIT_SUB`: 保存最终被分割好的、用于生成最终字幕的 “原文-译文” 对列表。
      这个文件的行数会比输入多，因为它包含了被拆分后的行。
    - `_5_REMERGED`: 保存一个用于后续音频生成的版本。在这个版本中，被分割的
      译文行会被重新合并（使用特定语言的连接符），以确保TTS（文本到语音）
      处理的是一个完整的句子，从而获得更自然的韵律。

使用方法:
  运行 `split_for_sub_main()` 函数，它会读取 `_4_2_TRANSLATION` 的输出，
  执行上述的迭代分割流程，并生成两个关键的输出文件，为后续的字幕生成和
  音频配音做好准备。
"""

import pandas as pd
from typing import List, Tuple
import concurrent.futures

from core._3_2_split_meaning import split_sentence
from core.prompts import get_align_prompt
from rich.panel import Panel
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from core.utils import *
from core.utils.models import *

console = Console()

def calc_len(text: str) -> float:
    """
    计算文本的加权长度，以更准确地反映其在屏幕上的显示宽度。
    """
    text = str(text)
    def char_weight(char):
        code = ord(char)
        if 0x4E00 <= code <= 0x9FFF or 0x3040 <= code <= 0x30FF: return 1.75 # 中文和日文
        elif 0xAC00 <= code <= 0xD7A3 or 0x1100 <= code <= 0x11FF: return 1.5 # 韩文
        elif 0x0E00 <= code <= 0x0E7F: return 1.0 # 泰文
        elif 0xFF01 <= code <= 0xFF5E: return 1.75 # 全角符号
        else: return 1.0 # 其他
    return sum(char_weight(char) for char in text)

def align_subs(src_sub: str, tr_sub: str, src_part: str) -> Tuple[List[str], List[str], str]:
    """
    使用LLM将源字幕和翻译字幕根据给定的源分片进行对齐分割。
    """
    align_prompt = get_align_prompt(src_sub, tr_sub, src_part)
    
    def valid_align(response_data):
        if 'align' not in response_data: return {"status": "error", "message": "响应中缺少必需的 'align' 键"}
        if len(response_data['align']) < 2: return {"status": "error", "message": "对齐结果应包含至少两个部分"}
        return {"status": "success", "message": "对齐完成"}
    
    parsed = ask_gpt(align_prompt, resp_type='json', valid_def=valid_align, log_title='align_subs')
    align_data = parsed['align']
    src_parts = src_part.split('\n')
    tr_parts = [item[f'target_part_{i+1}'].strip() for i, item in enumerate(align_data)]
    
    whisper_language = load_key("whisper.language")
    language = load_key("whisper.detected_language") if whisper_language == 'auto' else whisper_language
    joiner = get_joiner(language)
    tr_remerged = joiner.join(tr_parts)
    
    table = Table(title="🔗 对齐分割结果", show_header=True, header_style="bold magenta")
    table.add_column("语言", style="cyan")
    table.add_column("分段内容", style="green")
    table.add_row("源语言", "\n".join(src_parts))
    table.add_row("目标语言", "\n".join(tr_parts))
    console.log(table)
    
    return src_parts, tr_parts, tr_remerged

def split_align_subs(src_lines: List[str], tr_lines: List[str]):
    """
    识别并处理需要分割的字幕行，并使用线程池并行处理。
    """
    subtitle_set = load_key("subtitle")
    MAX_SUB_LENGTH = subtitle_set["max_length"]
    TARGET_SUB_MULTIPLIER = subtitle_set["target_multiplier"]
    remerged_tr_lines = tr_lines.copy()
    
    to_split_indices = [i for i, (src, tr) in enumerate(zip(src_lines, tr_lines)) 
                      if len(str(src)) > MAX_SUB_LENGTH or calc_len(str(tr)) * TARGET_SUB_MULTIPLIER > MAX_SUB_LENGTH]

    if not to_split_indices:
        console.log("[green]  ✓ 所有行均符合长度要求，无需分割。[/green]")
        return src_lines, tr_lines, remerged_tr_lines

    console.log(f"识别到 {len(to_split_indices)} 行需要分割。")
    
    @except_handler("在 split_align_subs 中出错")
    def process(i):
        split_src = split_sentence(src_lines[i], num_parts=2).strip()
        src_parts, tr_parts, tr_remerged = align_subs(src_lines[i], tr_lines[i], split_src)
        src_lines[i] = src_parts
        tr_lines[i] = tr_parts
        remerged_tr_lines[i] = tr_remerged
    
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        task = progress.add_task("[cyan]并行分割中...[/cyan]", total=len(to_split_indices))
        with concurrent.futures.ThreadPoolExecutor(max_workers=load_key("max_workers")) as executor:
            futures = {executor.submit(process, i): i for i in to_split_indices}
            for future in concurrent.futures.as_completed(futures):
                progress.update(task, advance=1)
    
    src_lines_flat = [item for sublist in src_lines for item in (sublist if isinstance(sublist, list) else [sublist])]
    tr_lines_flat = [item for sublist in tr_lines for item in (sublist if isinstance(sublist, list) else [sublist])]
    
    return src_lines_flat, tr_lines_flat, remerged_tr_lines

@check_file_exists(_5_SPLIT_SUB, _5_REMERGED)
def split_for_sub_main():
    """
    字幕分割的主函数，会进行多次迭代以确保所有行都符合长度要求。
    """
    console.print(Panel("🔪 [bold cyan]启动智能字幕分割流程[/bold cyan]", 
                        title="[bold]步骤 5[/bold]", subtitle="[bold]字幕分割[/bold]", expand=False))
    try:
        console.log("步骤 1/3: 正在加载待处理的字幕...")
        df = pd.read_excel(_4_2_TRANSLATION)
        src, trans = df['Source'].tolist(), df['Translation'].tolist()
        console.log(f"[green]  ✓ 已成功加载 {len(src)} 条字幕。[/green]")

        console.log("步骤 2/3: 正在进行迭代分割，最多尝试3轮...")
        subtitle_set = load_key("subtitle")
        MAX_SUB_LENGTH = subtitle_set["max_length"]
        TARGET_SUB_MULTIPLIER = subtitle_set["target_multiplier"]
        
        split_src, split_trans, remerged = src, trans, trans
        for attempt in range(3):
            console.print(Panel(f"🔄 第 {attempt + 1} 轮分割尝试", expand=False, border_style="blue"))
            split_src, split_trans, remerged = split_align_subs(src, trans)
            
            if all(len(str(s)) <= MAX_SUB_LENGTH for s in split_src) and \
               all(calc_len(t) * TARGET_SUB_MULTIPLIER <= MAX_SUB_LENGTH for t in split_trans):
                console.log(f"[bold green]  ✓ 第 {attempt + 1} 轮后，所有字幕行均符合长度要求。[/bold green]")
                break
            else:
                console.log(f"[yellow]  - 第 {attempt + 1} 轮后，仍有部分字幕超长，准备下一轮...[/yellow]")
                src, trans = split_src, split_trans
        else:
            console.log("[bold yellow]⚠️ 警告: 经过3轮尝试后，仍有字幕行可能超长。[/bold yellow]")

        console.log("步骤 3/3: 正在保存分割后的结果...")
        pd.DataFrame({'Source': split_src, 'Translation': split_trans}).to_excel(_5_SPLIT_SUB, index=False)
        pd.DataFrame({'Remerged': remerged}).to_excel(_5_REMERGED, index=False)
        
        console.print(Panel(f"🎉 [bold green]字幕分割流程完成！[/bold green]" 
                            f"\n  - 分割后用于生成字幕的文件已保存到: `{_5_SPLIT_SUB}`" 
                            f"\n  - 合并后用于语音合成的文件已保存到: `{_5_REMERGED}`",
                            title="[bold green]成功[/bold green]", expand=True))

    except Exception as e:
        console.print(Panel(f"字幕分割过程中发生意外错误: {e}", title="[bold red]错误[/bold red]", expand=True))
        raise

if __name__ == '__main__':
    split_for_sub_main()
