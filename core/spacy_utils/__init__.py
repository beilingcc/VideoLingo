# -*- coding: utf-8 -*-
"""
spacy_utils - 自然语言处理工具包 (基于 spaCy)

本模块是 VideoLingo 项目中专门用于自然语言处理（NLP）的核心工具包，主要依赖 spaCy 库。
它封装了一系列用于文本预处理，特别是句子分割（Sentence Splitting/Segmentation）的复杂逻辑。

核心功能:
- **NLP模型管理**: 包含加载和初始化 spaCy NLP模型的功能，确保模型在整个应用中高效、一致地被使用。
- **多策略句子分割**: 提供了多种先进的句子分割策略，以应对不同场景下的文本切分需求。
  这些策略能够处理简单的标点分割，以及复杂的、依赖句法分析的长句切分。

公开接口 (Public API):
- `init_nlp`: 初始化并加载 spaCy 模型，是使用本工具包其他功能前必须调用的函数。
- `split_by_mark`: 基于常规标点符号（如句号、问号、感叹号）进行句子分割。
- `split_by_comma_main`: 进一步基于逗号进行分割，处理并列子句。
- `split_sentences_main`: 基于语法连接词（如'and', 'but', 'so'等）进行智能分割。
- `split_long_by_root_main`: 最复杂的策略，通过分析句子的依存关系树（Dependency Tree），
  找到核心动词（ROOT），并围绕它来切分过长的句子，以保证切分后子句的语义完整性。

通过 `__all__` 变量，这些核心功能被明确地导出，方便项目其他模块直接调用。
"""

# 从当前包的各个子模块中导入核心功能函数。
# 这种方式有助于组织代码，使得从 spacy_utils 包的顶层即可访问所有关键功能。
# 导入顺序大致遵循了“先初始化，后按分割复杂度递增”的原则。

from .load_nlp_model import init_nlp                   # 负责加载和初始化 spaCy NLP 模型的函数。
from .split_by_mark import split_by_mark               # 提供基于标点符号（如。？！）的基础句子分割功能。
from .split_by_comma import split_by_comma_main       # 提供基于逗号的分割逻辑，用于处理并列从句等情况。
from .split_by_connector import split_sentences_main   # 提供基于连接词（如'and', 'but', 'so'）的智能分割功能。
from .split_long_by_root import split_long_by_root_main # 提供基于句法依存关系树的高级长句分割功能。


# `__all__` 列表定义了当其他模块使用 `from core.spacy_utils import *` 时，
# 哪些名称会被导入。这是一种明确声明包的公共API的方式，可以防止内部辅助函数被意外导出。
__all__ = [
    # 核心功能函数列表，顺序与上面的导入保持一致，便于阅读和维护。
    "init_nlp",                 # NLP模型初始化函数
    "split_by_mark",           # 基于标点符号的句子分割函数
    "split_by_comma_main",     # 基于逗号的句子分割函数
    "split_sentences_main",    # 基于连接词的句子分割函数
    "split_long_by_root_main", # 基于句法根节点的长句子分割函数
]
