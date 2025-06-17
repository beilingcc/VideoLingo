# -*- coding: utf-8 -*-
"""
文本摘要与术语提取模块

本模块的核心任务是利用大型语言模型（LLM）对经过预处理的文本（来自上一步的输出）
进行分析，以实现两个主要目标：
1.  **生成摘要**：虽然当前版本主要侧重于术语提取，但框架设计上可以扩展为生成全文摘要。
2.  **提取关键术语**：识别并提取文本中包含的专有名词、技术术语、特定概念等，并为它们
    提供翻译和解释。这对于保证后续翻译的一致性和准确性至关重要。

核心功能:
- **文本整合**: 将之前步骤中分割好的文本片段重新组合成一个连贯的文本块，作为 LLM 的输入。
- **自定义术语加载**: 支持从外部文件（如 `custom_terms.xlsx`）加载用户预定义的术语表。
  这些术语会与 LLM 提取的术语合并，确保用户特定的翻译和解释得到遵循。
- **基于 LLM 的术语提取**: 通过一个精心设计的 Prompt，引导 LLM 分析文本，识别出重要的
  术语（`src`），并提供其目标语言的翻译（`tgt`）以及相关的注释或解释（`note`）。
- **结果验证与合并**: 对 LLM 返回的结果进行格式校验，确保其完整性和正确性。然后，将
  LLM 提取的术语与用户自定义的术语合并，形成一个完整的术语表。
- **持久化存储**: 将最终的术语表以 JSON 格式保存到文件中，供后续的翻译模块使用。

使用方法:
  运行 `get_summary()` 函数将启动整个流程。它首先整合文本，加载自定义术语，
  然后调用 LLM 进行分析，最后处理并保存结果。该模块是翻译流程前一个关键的
  准备步骤。
"""

import json
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from core.prompts import get_summary_prompt
from core.utils import *
from core.utils.models import _3_2_SPLIT_BY_MEANING, _4_1_TERMINOLOGY

# 初始化 rich console
console = Console()

# 用户自定义术语文件的路径
CUSTOM_TERMS_PATH = 'custom_terms.xlsx'

def combine_chunks() -> str:
    """
    将分割后的文本行合并成单个长文本字符串。

    Returns:
        str: 合并后的文本内容，会根据配置中的 `summary_length` 限制长度。
    """
    with open(_3_2_SPLIT_BY_MEANING, 'r', encoding='utf-8') as file:
        sentences = file.readlines()
    cleaned_sentences = [line.strip() for line in sentences if line.strip()]
    combined_text = ' '.join(cleaned_sentences)
    # 根据配置限制送入LLM的文本长度，以节约成本和提高效率
    return combined_text[:load_key('summary_length')]

@check_file_exists(_4_1_TERMINOLOGY)
def summarize_main():
    """
    执行文本摘要和术语提取的核心流程。
    """
    console.print(Panel("🔍 [bold cyan]启动术语提取与摘要流程[/bold cyan]", 
                        title="[bold]步骤 4.1[/bold]", subtitle="[bold]摘要与术语[/bold]", expand=False))
    try:
        # 步骤 1: 合并文本块
        console.log("步骤 1/4: 正在合并文本块以供分析...")
        src_content = combine_chunks()
        console.log(f"[green]  ✓ 文本块合并完成，总长度: {len(src_content)} 字符。[/green]")

        # 步骤 2: 加载用户自定义术语
        console.log("步骤 2/4: 正在加载用户自定义术语...")
        custom_terms_json = {"terms": []}
        try:
            custom_terms_df = pd.read_excel(CUSTOM_TERMS_PATH)
            if not custom_terms_df.empty:
                custom_terms_json = {
                    "terms": [
                        {
                            "src": str(row.iloc[0]),
                            "tgt": str(row.iloc[1]), 
                            "note": str(row.iloc[2])
                        }
                        for _, row in custom_terms_df.iterrows()
                    ]
                }
                console.log(f"[green]  ✓ 已成功加载 {len(custom_terms_df)} 条自定义术语。[/green]")
            else:
                console.log("[yellow]  - 自定义术语文件为空，跳过。[/yellow]")
        except FileNotFoundError:
            console.log(f"[yellow]  - 未找到自定义术语文件 '{CUSTOM_TERMS_PATH}'，跳过。[/yellow]")

        # 步骤 3: 调用 LLM 提取术语
        console.log("步骤 3/4: 正在调用 LLM 进行术语提取...")
        summary_prompt = get_summary_prompt(src_content, custom_terms_json)
        
        def valid_summary(response_data):
            required_keys = {'src', 'tgt', 'note'}
            if 'terms' not in response_data or not isinstance(response_data['terms'], list):
                return {"status": "error", "message": "响应格式无效，缺少 'terms' 列表"}
            for term in response_data['terms']:
                if not required_keys.issubset(term.keys()):
                    return {"status": "error", "message": f"术语条目缺少必要键: {term}"}   
            return {"status": "success", "message": "摘要完成"}

        summary = None
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task(description="正在分析文本并提取术语，请稍候...", total=None)
            summary = ask_gpt(summary_prompt, resp_type='json', valid_def=valid_summary, log_title='summary')

        if not summary or 'terms' not in summary:
            console.log("[yellow]  - LLM 未能提取任何术语，将仅使用自定义术语。[/yellow]")
            summary = {"terms": []}
        else:
            llm_terms_count = len(summary.get('terms', []))
            console.log(f"[green]  ✓ LLM 调用完成，提取到 {llm_terms_count} 条术语。[/green]")

        # 步骤 4: 合并并保存最终术语表
        console.log("步骤 4/4: 正在合并并保存最终术语表...")
        
        # 优化合并逻辑，避免重复
        final_terms = {term['src']: term for term in summary.get('terms', [])}
        for term in custom_terms_json.get('terms', []):
            if term['src'] not in final_terms:
                final_terms[term['src']] = term
        
        final_summary = {"terms": list(final_terms.values())}
        total_terms = len(final_summary['terms'])

        with open(_4_1_TERMINOLOGY, 'w', encoding='utf-8') as f:
            json.dump(final_summary, f, ensure_ascii=False, indent=4)

        console.print(Panel(f"🎉 [bold green]术语提取完成！[/bold green]\n共 {total_terms} 条术语已保存到 `{_4_1_TERMINOLOGY}`。",
                            title="[bold green]成功[/bold green]", expand=True))

    except Exception as e:
        console.print(Panel(f"处理过程中发生意外错误: {e}", title="[bold red]错误[/bold red]", expand=True))
        raise

if __name__ == '__main__':
    summarize_main()