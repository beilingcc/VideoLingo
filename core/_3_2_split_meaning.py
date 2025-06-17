# -*- coding: utf-8 -*-
"""
基于大型语言模型 (LLM) 的语义分割模块

本模块是继基于规则的 NLP 分割（_3_1_split_nlp.py）之后的进阶处理步骤。
它的核心任务是利用大型语言模型（如 GPT）的强大语义理解能力，
对那些依然过长的句子进行智能切分。这对于处理复杂句式、口语化表达以及
没有明显语法分割点的文本至关重要。

核心功能:
- **智能语义分割**: 通过精心设计的 Prompt，引导 LLM 在保持句子核心意义不断裂的前提下，
  找到最合适的分割点，并插入特殊标记 `[br]`。
- **精确位置映射**: LLM 返回的分割结果可能在措辞上与原文有细微差异。
  本模块通过 `difflib.SequenceMatcher` 算法，将 LLM 建议的分割点精确地映射回
  原始句子的字符位置，确保分割操作不会修改原文内容，只在恰当位置插入换行符。
- **并行处理**: 对于需要处理的大量句子，采用多线程 (`concurrent.futures.ThreadPoolExecutor`)
  并行调用 LLM API，极大地提高了处理效率。
- **健壮的重试机制**: 考虑到网络请求和 LLM 响应的不确定性，内置了重试循环，
  确保所有长句都能被成功处理。

使用方法:
  主函数 `split_sentences_by_meaning()` 会读取上一步 NLP 分割的结果，
  筛选出长度超过预设阈值的句子，然后调用并行处理函数 `parallel_split_sentences`
  进行处理，最后将完全分割好的句子列表写入文件，供后续流程使用。
"""

import concurrent.futures
from difflib import SequenceMatcher
import math
from core.prompts import get_split_prompt
from core.spacy_utils.load_nlp_model import init_nlp
from core.utils import *
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress
from core.utils.models import _3_1_SPLIT_BY_NLP, _3_2_SPLIT_BY_MEANING

console = Console()

def tokenize_sentence(sentence: str, nlp) -> list:
    doc = nlp(sentence)
    return [token.text for token in doc]

def find_split_positions(original: str, modified: str) -> list:
    split_positions = []
    parts = modified.split('[br]')
    start = 0
    whisper_language = load_key("whisper.language")
    language = load_key("whisper.detected_language") if whisper_language == 'auto' else whisper_language
    joiner = get_joiner(language)

    for i in range(len(parts) - 1):
        max_similarity = 0
        best_split = None
        for j in range(start, len(original)):
            original_left = original[start:j]
            modified_left = joiner.join(parts[i].split())
            left_similarity = SequenceMatcher(None, original_left, modified_left).ratio()
            if left_similarity > max_similarity:
                max_similarity = left_similarity
                best_split = j

        if max_similarity < 0.9:
            console.log(f"[yellow]低相似度警告: {max_similarity:.2f} for part '{parts[i]}...'[/yellow]")
        if best_split is not None:
            split_positions.append(best_split)
            start = best_split
        else:
            console.log(f"[red]分割点查找失败 for part {i+1}[/red]")
    return split_positions

def split_sentence(sentence: str, num_parts: int, word_limit: int = 20, index: int = -1, retry_attempt: int = 0) -> str:
    split_prompt = get_split_prompt(sentence, num_parts, word_limit)
    def valid_split(response_data):
        choice = response_data.get("choice")
        if not choice or f'split{choice}' not in response_data:
            return {"status": "error", "message": "响应中缺少 'split' 或 'choice' 键"}
        if "[br]" not in response_data[f"split{choice}"]:
            return {"status": "error", "message": "分割失败，未找到 [br] 标记"}
        return {"status": "success", "message": "分割成功"}

    response_data = ask_gpt(split_prompt + " " * retry_attempt, resp_type='json', valid_def=valid_split, log_title='split_by_meaning')
    choice = response_data["choice"]
    best_split_modified = response_data[f"split{choice}"]
    split_points = find_split_positions(sentence, best_split_modified)

    result_parts = []
    last_pos = 0
    for pos in split_points:
        result_parts.append(sentence[last_pos:pos])
        last_pos = pos
    result_parts.append(sentence[last_pos:])
    best_split_original = '\n'.join(part.strip() for part in result_parts if part.strip())

    # 仅在日志模式下打印详细表格
    # table = Table(title=f"句子 {index} 分割详情", show_header=False, box=box.SIMPLE)
    # table.add_row("[cyan]原始[/cyan]", sentence)
    # table.add_row("[green]分割后[/green]", best_split_original.replace('\n', ' [color(248)]||[/color(248)] '))
    # console.log(table)
    
    return best_split_original

def parallel_split_sentences(sentences_to_split: list, max_length: int, max_workers: int, nlp, retry_attempt: int = 0) -> list:
    results = [None] * len(sentences_to_split)
    futures = []
    with Progress(console=console) as progress:
        task = progress.add_task(f"[cyan]  - 第 {retry_attempt + 1} 轮语义分割...", total=len(sentences_to_split))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            for index, (original_index, sentence) in enumerate(sentences_to_split):
                tokens = tokenize_sentence(sentence, nlp)
                num_parts = math.ceil(len(tokens) / max_length)
                future = executor.submit(split_sentence, sentence, num_parts, max_length, index=original_index, retry_attempt=retry_attempt)
                futures.append((future, original_index, sentence))

            for future, original_index, sentence in futures:
                try:
                    split_result = future.result()
                    if split_result:
                        split_lines = split_result.strip().split('\n')
                        results[futures.index((future, original_index, sentence))] = [line.strip() for line in split_lines]
                    else:
                        results[futures.index((future, original_index, sentence))] = [sentence]
                except Exception as e:
                    console.log(f"[red]错误: 分割句子 {original_index} 时出错: {e}[/red]")
                    results[futures.index((future, original_index, sentence))] = [sentence]
                progress.update(task, advance=1)
    return results

@check_file_exists(_3_2_SPLIT_BY_MEANING)
def split_meaning_main():
    """
    按语义分割句子的主函数。
    """
    console.print(Panel("[bold cyan]🧠 启动基于 LLM 的语义分割流程...[/bold cyan]", title="第三步 (补充): 语义分割", expand=False))
    try:
        # 步骤 1: 加载上一步的分割结果
        console.print(f"[cyan]- 步骤 1/4: 正在加载 NLP 分割后的句子...[/cyan]")
        try:
            with open(_3_1_SPLIT_BY_NLP, 'r', encoding='utf-8') as f:
                sentences = [line.strip() for line in f.readlines() if line.strip()]
            console.print(f"[green]  ✅ 成功加载 {len(sentences)} 个句子，源文件: `{_3_1_SPLIT_BY_NLP}`[/green]")
        except FileNotFoundError:
            console.print(Panel(f"[bold red]❌ 输入文件未找到[/bold red]", subtitle=f"请确保 `{_3_1_SPLIT_BY_NLP}` 文件存在。", expand=False))
            return

        # 步骤 2: 初始化模型和配置
        console.print(f"[cyan]- 步骤 2/4: 正在初始化模型和配置...[/cyan]")
        nlp = init_nlp()
        max_len = load_key("max_split_length")
        max_w = load_key("max_workers")
        console.print(f"[green]  ✅ 模型和配置加载完毕 (最大长度: {max_len}, 最大线程数: {max_w})。[/green]")

        # 步骤 3: 循环进行并行语义分割
        console.print(f"[cyan]- 步骤 3/4: 正在对长句进行多轮并行语义分割...[/cyan]")
        for retry_attempt in range(3): # 最多进行3轮分割
            long_sentences_to_split = [(i, s) for i, s in enumerate(sentences) if len(tokenize_sentence(s, nlp)) > max_len]
            
            if not long_sentences_to_split:
                console.print("[green]  ✅ 所有句子长度均已达标，无需进一步分割。[/green]")
                break

            console.print(f"[cyan]  - 第 {retry_attempt + 1} 轮分割开始 (发现 {len(long_sentences_to_split)} 个长句)...[/cyan]")
            split_results = parallel_split_sentences([(i, s) for i, s in long_sentences_to_split], max_length=max_len, max_workers=max_w, nlp=nlp, retry_attempt=retry_attempt)
            
            # 将分割结果更新回主列表
            new_sentences = list(sentences)
            for (original_index, _), result_lines in zip(long_sentences_to_split, split_results):
                new_sentences[original_index] = result_lines
            
            sentences = [item for sublist in new_sentences for item in (sublist if isinstance(sublist, list) else [sublist])]

            needs_another_round = any(len(tokenize_sentence(s, nlp)) > max_len for s in sentences)
            if not needs_another_round:
                console.print(f"[green]  ✅ 第 {retry_attempt + 1} 轮后，所有句子长度均已达标。[/green]")
                break
        console.print("[green]  ✅ 语义分割处理完成。[/green]")

        # 步骤 4: 保存最终结果
        console.print(f"[cyan]- 步骤 4/4: 正在保存最终结果...[/cyan]")
        with open(_3_2_SPLIT_BY_MEANING, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sentences))
        
        console.print(Panel(f"[bold green]🎉 语义分割流程完成！[/bold green]", subtitle=f"结果已保存到 `{_3_2_SPLIT_BY_MEANING}`", expand=False))

    except Exception as e:
        console.print(Panel(f"[bold red]❌ 语义分割流程发生严重错误[/bold red]", subtitle=str(e), expand=False))

if __name__ == '__main__':
    split_meaning_main()