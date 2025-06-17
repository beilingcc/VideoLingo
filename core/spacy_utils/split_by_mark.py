# -*- coding: utf-8 -*-
"""
基于标点符号的句子分割模块（流水线入口）

本模块是整个句子分割流水线的起始点。它负责从一个包含原始文本片段的 Excel 文件中读取数据，
进行初步的、基于标准结束标点（如句号、问号、感叹号）的分割。

核心功能:
1.  **数据读取与拼接**:
    - 从 `output/log/cleaned_chunks.xlsx` 文件中读取由 ASR（自动语音识别）生成的文本片段。
    - 根据项目配置的语言，使用特定的连接符（`joiner`）将这些文本片段智能地拼接成一个完整的长文本。
      例如，英文使用空格连接，而中文、日文则直接拼接。

2.  **基础分割**:
    - 利用 spaCy 强大的 `doc.sents` 功能，对拼接后的长文本进行第一次分割。这一步主要依赖于
      模型对标准句子结束标点的识别。

3.  **特殊情况合并**:
    - **处理破折号和省略号**: 包含专门的逻辑来识别并合并那些被 `-` (破折号) 或 `...` (省略号)
      错误断开的句子，确保语义的完整性。
    - **修正悬挂标点**: 解决在某些语言（特别是中日韩语言）中，分割后可能产生只包含单个标点的行的问题。
      它会将这些独立的标点符号合并到前一个句子的末尾。

4.  **输出与衔接**:
    - 将处理好的句子列表写入到 `SPLIT_BY_MARK_FILE` 文件中，每行一个句子。
    - 这个输出文件将作为后续分割步骤（如 `split_by_comma.py`）的输入，从而启动整个分割流水线。
"""

import os
import pandas as pd
import warnings
from core.spacy_utils.load_nlp_model import init_nlp, SPLIT_BY_MARK_FILE
from core.utils.config_utils import load_key, get_joiner
from core.utils import rprint, write_to_file

# 忽略不必要的警告信息
warnings.filterwarnings("ignore", category=FutureWarning)

def split_by_mark(nlp):
    """
    执行基于标点的句子分割，并处理特殊的合并逻辑。

    Args:
        nlp (spacy.Language): 已加载的 spaCy 模型实例。
    """
    # --- 1. 加载配置并拼接原始文本 ---
    whisper_language = load_key("whisper.language")
    # 优先使用检测到的语言，同时兼容强制指定语言的情况
    language = load_key("whisper.detected_language") if whisper_language == 'auto' else whisper_language
    joiner = get_joiner(language)
    rprint(f"[blue]🔍 使用 '{language}' 语言连接符: '{joiner}'[/blue]")
    
    # 从 Excel 文件读取原始文本块
    chunks = pd.read_excel("output/log/cleaned_chunks.xlsx")
    # 清理每个文本块首尾可能存在的无关引号
    chunks.text = chunks.text.apply(lambda x: x.strip('"').strip())
    
    # 使用特定语言的连接符将所有文本块拼接成一个长字符串
    input_text = joiner.join(chunks.text.to_list())

    # --- 2. 使用 spaCy 进行基础分割 ---
    doc = nlp(input_text)
    assert doc.has_annotation("SENT_START"), "spaCy未能成功进行句子分割，请检查模型。"

    # --- 3. 处理特殊合并逻辑（破折号和省略号） ---
    # 这个列表用于存储初步分割并经过合并处理的句子
    sentences_after_merge = []
    current_sentence_parts = []
    
    for sent in doc.sents:
        text = sent.text.strip()
        if not text:
            continue

        # 判断当前句子是否应与前一部分合并（例如，以 '...' 或 '-' 开始/结束）
        if current_sentence_parts and (
            text.startswith('-') or 
            text.startswith('...') or
            current_sentence_parts[-1].endswith('-') or
            current_sentence_parts[-1].endswith('...')
        ):
            current_sentence_parts.append(text)
        else:
            # 如果不需合并，则将之前缓存的部分连接成一个完整句子
            if current_sentence_parts:
                sentences_after_merge.append(' '.join(current_sentence_parts))
            # 开始一个新的句子片段
            current_sentence_parts = [text]
    
    # 将最后一个缓存的句子添加到结果列表
    if current_sentence_parts:
        sentences_after_merge.append(' '.join(current_sentence_parts))

    # --- 4. 处理悬挂标点并准备最终输出 ---
    final_sentences = []
    punctuation_to_merge = [',', '.', '，', '。', '？', '！']
    for i, sentence in enumerate(sentences_after_merge):
        # 如果当前行只包含一个标点，并且不是第一行，则将其附加到前一行的末尾
        if i > 0 and sentence.strip() in punctuation_to_merge and final_sentences:
            final_sentences[-1] += sentence
        else:
            final_sentences.append(sentence)

    # --- 5. 写入文件 ---
    output_content = "\n".join(filter(None, final_sentences))
    write_to_file(SPLIT_BY_MARK_FILE, output_content)
    
    rprint(f"[green]💾 已按标点分割句子，结果保存至 → `{SPLIT_BY_MARK_FILE}`[/green]")

if __name__ == "__main__":
    nlp_instance = init_nlp()
    split_by_mark(nlp_instance)
