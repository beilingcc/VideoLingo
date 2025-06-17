# -*- coding: utf-8 -*-
"""
基于自然语言处理 (NLP) 的文本分割模块

本模块是文本处理流水线中的一个关键步骤，位于语音识别之后、翻译之前。
其主要任务是利用 NLP 技术，特别是 Spacy 库，将 ASR（自动语音识别）生成的长文本或句子，
分解成更短、更易于处理的语义单元。这样做有助于提高后续翻译的准确性，
并为生成与语音同步的字幕提供更合适的切分点。

核心功能:
- **多层次分割策略**: 采用一系列从粗到细的分割方法，确保文本被合理地切分：
  1. **基于标点**: 首先使用句号、问号、感叹号等明确的句子结束符进行初步分割。
  2. **基于逗号**: 对较长的、由逗号连接的子句进行切分，同时考虑上下文，避免不自然的断句。
  3. **基于连接词**: 识别并利用连词（如 'and', 'but', 'so'）作为分割点，将并列或转折的子句分开。
  4. **基于句法结构**: 对于没有明显分割标记的复杂长句，利用 Spacy 的依存句法分析功能，找到句子的核心动词（root），并围绕它进行分割，保证每个子单元的语法完整性。
- **Spacy 模型集成**: 封装了 Spacy 模型的加载和初始化过程，方便调用。

使用方法:
  模块的主入口是 `split_by_spacy()` 函数。该函数会依次调用四种不同的分割工具函数，
  每一步都在上一步输出的基础上进行操作，层层递进，最终将处理结果保存到文件中，
  供下一个流水线模块使用。
"""

from core.spacy_utils import *
from core.utils.models import _3_1_SPLIT_BY_NLP
from core.utils import check_file_exists, console
from rich.panel import Panel

# ------------
# 基于NLP的句子分割模块
# 使用Spacy进行自然语言处理，将长句子分割成更小的单位
# ------------

@check_file_exists(_3_1_SPLIT_BY_NLP)
def split_nlp_main():
    """
    使用 Spacy 驱动的 NLP 流水线对文本进行分句。
    """
    console.print(Panel("[bold cyan]📝 启动基于 NLP 的文本分割流程...[/bold cyan]", title="第三步: 文本分割", expand=False))
    try:
        # 步骤 1: 初始化NLP模型
        console.print("[cyan]- 步骤 1/5: 正在初始化 Spacy NLP 模型... (首次运行可能需要下载模型)[/cyan]")
        nlp = init_nlp()
        console.print("[green]  ✅ NLP 模型加载成功。[/green]")

        # 步骤 2: 根据标点符号分割
        console.print("[cyan]- 步骤 2/5: 正在根据标点符号进行初步分割...[/cyan]")
        split_by_mark(nlp)
        console.print("[green]  ✅ 标点分割完成。[/green]")

        # 步骤 3: 根据逗号分割
        console.print("[cyan]- 步骤 3/5: 正在根据逗号进一步分割...[/cyan]")
        split_by_comma_main(nlp)
        console.print("[green]  ✅ 逗号分割完成。[/green]")

        # 步骤 4: 根据连接词分割
        console.print("[cyan]- 步骤 4/5: 正在根据连接词优化分割...[/cyan]")
        split_sentences_main(nlp)
        console.print("[green]  ✅ 连接词分割完成。[/green]")

        # 步骤 5: 根据句法结构分割长句子
        console.print("[cyan]- 步骤 5/5: 正在利用句法结构处理长句...[/cyan]")
        split_long_by_root_main(nlp)
        console.print("[green]  ✅ 长句分割完成。[/green]")

        console.print(Panel(f"[bold green]🎉 NLP 文本分割流程完成！[/bold green]", subtitle=f"结果已保存到 `{_3_1_SPLIT_BY_NLP}`", expand=False))

    except Exception as e:
        console.print(Panel(f"[bold red]❌ NLP 文本分割流程发生错误[/bold red]", subtitle=str(e), expand=False))

if __name__ == '__main__':
    split_nlp_main()