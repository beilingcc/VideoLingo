# -*- coding: utf-8 -*-
"""
智能逗号分割模块

本模块是句子分割流程中的一个关键步骤，专门负责处理基于逗号的智能分割。
与简单的按逗号切分不同，本模块利用 spaCy 进行句法分析，判断逗号是否分隔了两个
在语法上相对独立的子句（即都包含主语和谓语），从而决定是否进行分割。

核心逻辑:
1.  **有效短语判断**: `is_valid_phrase` 函数通过检查一个 spaCy 短语片段（Span）是否同时
    包含主语（nsubj, nsubjpass）和动词（VERB, AUX）来判断其是否构成一个有效的子句。
2.  **逗号上下文分析**: `analyze_comma` 函数是决策核心。对于每一个逗号，它会检查其右侧的
    短语是否是一个有效的子句，并确保逗号两侧都有足够数量的词（默认大于3），以避免
    在列表或简短插入语中进行不当分割。
3.  **流水线操作**: `split_by_comma_main` 函数定义了本模块的工作流。它会读取上一步
    （按标点分割）的输出文件，对其中的每一句话应用逗号分割逻辑，然后将结果写入新的
    输出文件，并删除原始的输入文件。

这种智能分割方法可以有效处理并列句、复合句，同时避免破坏句子结构，提高分割质量。
"""

import itertools
import os
import warnings
from core.utils import rprint, write_to_file
from core.spacy_utils.load_nlp_model import init_nlp, SPLIT_BY_COMMA_FILE, SPLIT_BY_MARK_FILE

# 忽略来自旧版本库可能产生的FutureWarning警告
warnings.filterwarnings("ignore", category=FutureWarning)

def is_valid_phrase(phrase) -> bool:
    """
    检查一个短语（spaCy Span对象）是否构成一个有效的独立子句。
    有效子句的标准是：必须同时包含主语和动词。

    Args:
        phrase (spacy.tokens.span.Span): 需要分析的短语。

    Returns:
        bool: 如果短语包含主语和动词，则返回 True，否则返回 False。
    """
    # 检查是否存在主语：依存关系为'nsubj'(名词主语)或'nsubjpass'(被动名词主语)，或者词性为代词(PRON)。
    has_subject = any(token.dep_ in ["nsubj", "nsubjpass"] or token.pos_ == "PRON" for token in phrase)
    # 检查是否存在动词：词性为'VERB'(动词)或'AUX'(助动词)。
    has_verb = any((token.pos_ == "VERB" or token.pos_ == 'AUX') for token in phrase)
    return has_subject and has_verb

def analyze_comma(start: int, doc, token) -> bool:
    """
    分析给定逗号是否适合作为分割点。

    Args:
        start (int): 当前处理句段在原始doc中的起始索引。
        doc (spacy.tokens.doc.Doc): 完整的spaCy Doc对象。
        token (spacy.tokens.token.Token): 当前正在分析的逗号token。

    Returns:
        bool: 如果该逗号适合分割，返回 True，否则返回 False。
    """
    # 提取逗号左侧和右侧的上下文短语，窗口大小约为9个token。
    left_phrase = doc[max(start, token.i - 9):token.i]
    right_phrase = doc[token.i + 1:min(len(doc), token.i + 10)]
    
    # 核心判断：只有当逗号右侧的短语是一个有效的独立子句时，才考虑分割。
    # 左侧短语默认被认为是有效的，因为它是句子的前半部分。
    suitable_for_splitting = is_valid_phrase(right_phrase)
    
    # 附加条件：为防止在短列表或插入语（如 'a, b, c'）中分割，
    # 检查逗号两侧的实际单词数量（排除标点符号）。
    left_words = [t for t in left_phrase if not t.is_punct]
    # 对于右侧，只检查到下一个标点前的单词，避免跨越多个子句。
    right_words = list(itertools.takewhile(lambda t: not t.is_punct, right_phrase))
    
    # 如果任何一侧的单词数小于等于3，则认为不适合分割。
    if len(left_words) <= 3 or len(right_words) <= 3:
        suitable_for_splitting = False

    return suitable_for_splitting

def split_by_comma(text: str, nlp) -> list:
    """
    对单句文本应用智能逗号分割逻辑。

    Args:
        text (str): 需要分割的单句文本。
        nlp (spacy.Language): 已加载的spaCy模型实例。

    Returns:
        list: 分割后的子句列表。
    """
    doc = nlp(text)
    sentences = []
    start = 0  # 当前子句的起始token索引
    
    # 遍历句子中的每一个token
    for token in doc:
        # 同时检查英文逗号和中文逗号
        if token.text in [",", "，"]:
            # 调用分析函数判断是否应该在此处分割
            if analyze_comma(start, doc, token):
                # 如果适合分割，则将逗号前的部分作为一个子句添加
                sentences.append(doc[start:token.i].text.strip())
                rprint(f"[yellow]✂️  在逗号处分割: ...{doc[start:token.i].text[-10:]},| {doc[token.i + 1:].text[:10]}...[/yellow]")
                # 更新下一个子句的起始位置到逗号之后
                start = token.i + 1
    
    # 将最后一个分割点到句子末尾的部分作为最后一个子句添加
    sentences.append(doc[start:].text.strip())
    return sentences

def split_by_comma_main(nlp):
    """
    执行逗号分割的主函数，是整个流程的一部分。
    它读取前一阶段（按标点分割）的输出，进行逗号分割，然后将结果写入新文件，
    并清理掉前一阶段的文件。

    Args:
        nlp (spacy.Language): 已加载的spaCy模型实例。
    """
    # 检查输入文件是否存在，如果不存在则直接返回，避免错误。
    if not os.path.exists(SPLIT_BY_MARK_FILE):
        rprint(f"[yellow]未找到输入文件 {SPLIT_BY_MARK_FILE}，跳过逗号分割步骤。[/yellow]")
        # 创建一个空的输出文件，以确保后续流程的连贯性
        write_to_file(SPLIT_BY_COMMA_FILE, "")
        return

    with open(SPLIT_BY_MARK_FILE, "r", encoding="utf-8") as input_file:
        sentences = input_file.readlines()

    all_split_sentences = []
    for sentence in sentences:
        # 对每一句从文件中读出的句子，应用逗号分割逻辑
        split_sentences = split_by_comma(sentence.strip(), nlp)
        all_split_sentences.extend(split_sentences)

    # 将所有分割后的子句写入输出文件
    output_content = "\n".join(filter(None, all_split_sentences))
    write_to_file(SPLIT_BY_COMMA_FILE, output_content)
    
    # 重要：删除原始的输入文件，因为它已经被处理并被新文件取代。
    # 这是流水线设计的一部分。
    os.remove(SPLIT_BY_MARK_FILE)
    
    rprint(f"[green]💾 按逗号分割完成，结果已保存到 → `{SPLIT_BY_COMMA_FILE}`[/green]")

if __name__ == "__main__":
    # --- 测试代码 ---
    # 初始化NLP模型
    test_nlp = init_nlp()
    # 构造一个测试用的输入文件
    test_sentences = [
        "So in the same frame, right there, almost in the exact same spot on the ice, Brown has committed himself, whereas McDavid has not.",
        "This is a simple sentence, it has two parts.",
        "We need to buy apples, oranges, and bananas."
    ]
    with open(SPLIT_BY_MARK_FILE, "w", encoding="utf-8") as f:
        for s in test_sentences:
            f.write(s + "\n")
    
    # 运行主函数进行测试
    split_by_comma_main(test_nlp)
    
    # 打印结果进行验证
    with open(SPLIT_BY_COMMA_FILE, "r", encoding="utf-8") as f:
        rprint("\n--- 分割结果 ---")
        print(f.read())
        rprint("--- 测试结束 ---")