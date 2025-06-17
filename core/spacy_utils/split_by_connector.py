# -*- coding: utf-8 -*-
"""
基于连接词的智能句子分割模块

本模块是句子分割流水线中的高级步骤，专门用于处理基于语法连接词的分割。
它支持多种语言，并利用 spaCy 提供的句法依存分析来智能地判断是否应该在连接词处切分句子，
从而有效处理复杂的复合句和并列句。

核心功能:
- **多语言支持**: 内置了对英语、中文、日语、法语、俄语、西班牙语、德语和意大利语等多种语言的
  连接词和语法规则的支持。
- **句法感知分割**: 不仅仅是查找关键词，`analyze_connectors` 函数会分析连接词的词性（POS）和
  依存关系（Dependency），以区分其在句子中的不同语法功能。例如，它可以区分作为从句引导词的 'that'
  和作为限定词的 'that'，只在前者的情况下进行分割。
- **迭代式分割**: `split_by_connectors` 函数采用一种巧妙的迭代方法，每次只在句子中第一个
  最合适的连接词处进行分割，然后在新生成的句子片段上重复此过程，直到没有更多的分割点。
  这种方法可以避免将一个长句一次性切得过于零碎。
- **流水线操作**: 作为处理流程的一部分，`split_sentences_main` 函数会读取上一步（逗号分割）
  的输出，应用本模块的逻辑，将结果写入新文件，并删除上一步的中间文件。
"""

import os
import warnings
from core.spacy_utils.load_nlp_model import init_nlp, SPLIT_BY_COMMA_FILE, SPLIT_BY_CONNECTOR_FILE
from core.utils import rprint, write_to_file

# 忽略不必要的警告信息
warnings.filterwarnings("ignore", category=FutureWarning)

def analyze_connectors(doc, token) -> bool:
    """
    分析一个 token 是否为应触发句子分割的连接词。
    这是一个核心决策函数，它基于语言和词的句法功能来判断。

    处理逻辑顺序:
     1. 根据文档语言，确定要检查的连接词列表和相应的语法规则。
     2. 检查当前 token 是否在目标连接词列表中。
     3. 对特定词（如英语中的 'that'）进行特殊处理，检查其依存关系以确定其功能。
     4. 检查 token 是否作为名词的限定词或代词，如果是，则不分割。
     5. 如果以上条件都不满足，默认对于大部分连接词进行分割。

    Args:
        doc (spacy.tokens.doc.Doc): 当前正在处理的 spaCy Doc 对象。
        token (spacy.tokens.token.Token): 需要分析的 token。

    Returns:
        bool: 如果应该在该 token 前进行分割，则返回 True，否则返回 False。
    """
    lang = doc.lang_  # 获取文档的语言代码

    # --- 多语言连接词和语法规则定义 ---
    # 为每种支持的语言定义连接词列表和相关的依存关系、词性标签。
    if lang == "en":
        connectors = ["that", "which", "where", "when", "because", "but", "and", "or"]
        mark_dep = "mark"  # 从句引导词的依存关系
        det_pron_deps = ["det", "pron"]  # 限定词和代词的依存关系
        verb_pos = "VERB"
        noun_pos = ["NOUN", "PROPN"]
    elif lang == "zh":
        connectors = ["因为", "所以", "但是", "而且", "虽然", "如果", "即使", "尽管"]
        mark_dep = "mark"
        det_pron_deps = ["det", "pron"]
        verb_pos = "VERB"
        noun_pos = ["NOUN", "PROPN"]
    # ... (其他语言的定义与此类似) ...
    elif lang == "ja":
        connectors = ["けれども", "しかし", "だから", "それで", "ので", "のに", "ため"]
        mark_dep = "mark"
        det_pron_deps = ["case"]
        verb_pos = "VERB"
        noun_pos = ["NOUN", "PROPN"]
    elif lang == "fr":
        connectors = ["que", "qui", "où", "quand", "parce que", "mais", "et", "ou"]
        mark_dep = "mark"
        det_pron_deps = ["det", "pron"]
        verb_pos = "VERB"
        noun_pos = ["NOUN", "PROPN"]
    elif lang == "ru":
        connectors = ["что", "который", "где", "когда", "потому что", "но", "и", "или"]
        mark_dep = "mark"
        det_pron_deps = ["det"]
        verb_pos = "VERB"
        noun_pos = ["NOUN", "PROPN"]
    elif lang == "es":
        connectors = ["que", "cual", "donde", "cuando", "porque", "pero", "y", "o"]
        mark_dep = "mark"
        det_pron_deps = ["det", "pron"]
        verb_pos = "VERB"
        noun_pos = ["NOUN", "PROPN"]
    elif lang == "de":
        connectors = ["dass", "welche", "wo", "wann", "weil", "aber", "und", "oder"]
        mark_dep = "mark"
        det_pron_deps = ["det", "pron"]
        verb_pos = "VERB"
        noun_pos = ["NOUN", "PROPN"]
    elif lang == "it":
        connectors = ["che", "quale", "dove", "quando", "perché", "ma", "e", "o"]
        mark_dep = "mark"
        det_pron_deps = ["det", "pron"]
        verb_pos = "VERB"
        noun_pos = ["NOUN", "PROPN"]
    else:
        # 如果语言不支持，则不进行分割
        return False
    
    # 如果当前 token 不在连接词列表中，则不分割
    if token.text.lower() not in connectors:
        return False
    
    # --- 特定规则判断 ---
    # 规则1: 对英语中的 'that' 进行特殊处理
    if lang == "en" and token.text.lower() == "that":
        # 如果 'that' 是一个从句引导词 (mark)，并且其头部是一个动词，那么它很可能引导一个新子句，应该分割。
        if token.dep_ == mark_dep and token.head.pos_ == verb_pos:
            return True
        else:
            # 否则，'that' 可能是一个限定词（如 'that book'），不应分割。
            return False
    # 规则2: 如果 token 是一个限定词或代词，并且其头部是一个名词，则不分割。
    # 这可以防止在关系从句中（如 'the man who...'）或名词短语中错误地分割。
    elif token.dep_ in det_pron_deps and token.head.pos_ in noun_pos:
        return False
    else:
        # 默认情况：如果 token 是一个连接词且不满足上述排除条件，则进行分割。
        return True

def split_by_connectors(text: str, context_words: int = 5, nlp=None) -> list:
    """
    对单句文本应用基于连接词的迭代式分割逻辑。

    Args:
        text (str): 需要分割的单句文本。
        context_words (int): 分割点两侧必须满足的最小单词数，用于避免在短语中分割。
        nlp (spacy.Language): 已加载的 spaCy 模型实例。

    Returns:
        list: 分割后的子句列表。
    """
    doc = nlp(text)
    sentences = [doc.text]  # 初始时，句子列表只包含原始句子
    
    # 迭代分割，直到句子中再也找不到合适的分割点
    while True:
        split_occurred = False  # 标记本轮迭代是否发生了分割
        new_sentences = []
        
        for sent in sentences:
            doc = nlp(sent)
            start = 0
            
            # 遍历句子中的每个 token，寻找第一个合适的分割点
            for i, token in enumerate(doc):
                should_split = analyze_connectors(doc, token)
                
                # 跳过缩写词，避免如 "that's" 被错误分割
                if i + 1 < len(doc) and doc[i + 1].text in ["'s", "'re", "'ve", "'ll", "'d"]:
                    continue
                
                # 检查上下文单词数量，确保分割点两侧都有足够的内容
                left_words = [word for word in doc[max(0, token.i - context_words):token.i] if not word.is_punct]
                right_words = [word for word in doc[token.i+1:min(len(doc), token.i + context_words + 1)] if not word.is_punct]
                
                if len(left_words) >= context_words and len(right_words) >= context_words and should_split:
                    rprint(f"[yellow]✂️  在连接词前分割 '{token.text}': {' '.join(t.text for t in left_words)} | {token.text} {' '.join(t.text for t in right_words)}[/yellow]")
                    new_sentences.append(doc[start:token.i].text.strip())  # 添加分割点前的部分
                    start = token.i  # 更新下一句的起始点
                    split_occurred = True
                    break  # 找到第一个分割点后，立即跳出内层循环，处理下一个句子片段
            
            # 将当前处理的句子的剩余部分（或未被分割的整个句子）添加到新列表
            if start < len(doc):
                new_sentences.append(doc[start:].text.strip())
        
        # 如果本轮迭代没有发生任何分割，说明处理完成，退出循环
        if not split_occurred:
            break
        
        # 用新生成的句子列表替换旧的，准备下一轮迭代
        sentences = new_sentences
    
    return sentences

def split_sentences_main(nlp):
    """
    执行连接词分割的主函数，是整个流程的一部分。
    它读取前一阶段的输出，进行连接词分割，然后将结果写入新文件，并清理掉前一阶段的文件。

    Args:
        nlp (spacy.Language): 已加载的 spaCy 模型实例。
    """
    # 检查输入文件是否存在，如果不存在则跳过此步骤
    if not os.path.exists(SPLIT_BY_COMMA_FILE):
        rprint(f"[yellow]未找到输入文件 {SPLIT_BY_COMMA_FILE}，跳过连接词分割步骤。[/yellow]")
        write_to_file(SPLIT_BY_CONNECTOR_FILE, "") # 创建空文件以保证流程连贯
        return

    with open(SPLIT_BY_COMMA_FILE, "r", encoding="utf-8") as input_file:
        sentences = input_file.readlines()
    
    all_split_sentences = []
    for sentence in sentences:
        # 对每个从文件中读出的句子应用连接词分割逻辑
        split_sentences = split_by_connectors(sentence.strip(), nlp=nlp)
        all_split_sentences.extend(split_sentences)
    
    # 将所有处理后的句子连接成一个字符串，用换行符分隔，然后一次性写入文件
    # 这样更高效，也避免了在文件末尾留下多余的换行符
    output_content = "\n".join(filter(None, all_split_sentences))
    write_to_file(SPLIT_BY_CONNECTOR_FILE, output_content)

    # 重要：删除作为输入的上一步中间文件，这是流水线设计的核心部分
    os.remove(SPLIT_BY_COMMA_FILE)
    
    rprint(f"[green]💾 按连接词分割完成，结果已保存到 → `{SPLIT_BY_CONNECTOR_FILE}`[/green]")

if __name__ == "__main__":
    # --- 测试代码 ---
    test_nlp = init_nlp()
    test_sentence = "and show the specific differences that make a difference between a breakaway that results in a goal in the NHL versus one that doesn't."
    rprint(f"原始句子: {test_sentence}")
    split_result = split_by_connectors(test_sentence, nlp=test_nlp)
    rprint("--- 分割结果 ---")
    for s in split_result:
        print(s)