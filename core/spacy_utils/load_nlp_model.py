# -*- coding: utf-8 -*-
"""
spaCy NLP 模型加载与管理模块

本模块是 `spacy_utils` 工具包的基石，负责根据项目配置动态加载和初始化 spaCy 自然语言处理 (NLP) 模型。
它是所有后续文本分析（如句子分割）功能得以运行的前提。

核心功能:
- **模型动态选择**: 根据 `config.yaml` 中配置的语言（`whisper.language` 或 `whisper.detected_language`），
  从 `spacy_model_map` 映射表中查找并确定需要加载的 spaCy 模型。
- **自动下载与安装**: 如果所需的 spaCy 模型在本地环境中不存在，本模块会自动调用 `spacy.cli.download` 
  进行下载和安装，极大地简化了用户的初始环境配置。
- **统一初始化入口**: 提供唯一的 `init_nlp()` 函数作为 NLP 模型的初始化入口，确保整个应用中
  使用的是同一个、正确配置的 `nlp` 实例。
- **异常处理**: 使用 `@except_handler` 装饰器对模型加载过程中的潜在错误进行统一捕获和报告。

使用流程:
1. 程序启动时，首先调用 `init_nlp()` 函数。
2. `init_nlp()` 确定语言，并获取对应的模型名称。
3. 尝试加载模型，如果失败（通常是 `OSError`），则触发下载流程。
4. 成功加载或下载后，返回一个可用的 `nlp` 对象，供其他模块使用。
"""

import spacy
from spacy.cli import download
from core.utils import rprint, load_key, except_handler

# 从 `config.yaml` 配置文件中加载语言代码到 spaCy 模型名称的映射表。
# 这个映射表是实现多语言支持的关键。
# 示例: {'en': 'en_core_web_md', 'zh': 'zh_core_web_md'}
SPACY_MODEL_MAP = load_key("spacy_model_map")

def get_spacy_model(language: str) -> str:
    """
    根据提供的语言代码，从 SPACY_MODEL_MAP 中获取对应的 spaCy 模型名称。

    Args:
        language (str): 语言代码，例如 'en', 'zh', 'de' 等。
        
    Returns:
        str: 对应的 spaCy 模型名称。如果映射表中不支持该语言，则返回一个默认的英语模型作为后备，
             并打印警告信息。
    """
    # 将语言代码转为小写以进行不区分大小写的匹配，并从映射表中获取模型名称。
    model = SPACY_MODEL_MAP.get(language.lower(), "en_core_web_md")
    
    # 如果提供的语言不在映射表的键中，说明该语言不被正式支持，发出警告。
    if language.lower() not in SPACY_MODEL_MAP:
        rprint(f"[yellow]警告: spaCy 模型配置不支持语言 '{language}'，将使用默认的 'en_core_web_md' 模型。[/yellow]")
    return model

@except_handler("加载 NLP Spacy 模型失败")
def init_nlp() -> spacy.Language:
    """
    初始化并加载 spaCy NLP 模型。
    
    此函数是获取 NLP 功能的入口点。它会根据 `config.yaml` 的设置确定语言，
    加载相应的 spaCy 模型。如果模型在本地不存在，它将自动尝试下载。
    
    Returns:
        spacy.Language: 一个已加载并准备就绪的 spaCy 语言模型实例。
    """
    # 1. 确定要使用的语言：优先使用用户在配置中指定的 `whisper.language`，如果为 'en' 则直接用 'en'。
    #    否则，使用 Whisper 模型自动检测出的 `detected_language`。
    language = "en" if load_key("whisper.language") == "en" else load_key("whisper.detected_language")
    
    # 2. 根据确定的语言获取对应的模型名称。
    model = get_spacy_model(language)
    rprint(f"[blue]⏳ 正在加载 NLP (spaCy) 模型: <{model}> ...[/blue]")
    
    try:
        # 3. 尝试加载指定的模型。
        nlp = spacy.load(model)
    except OSError:
        # 4. 如果加载失败（通常是因为模型未安装），则捕获 OSError 异常，并启动自动下载流程。
        rprint(f"[yellow]模型 '{model}' 未找到，正在尝试自动下载...[/yellow]")
        rprint("[yellow]如果下载失败，请检查您的网络连接或尝试手动安装: pip install {model}[/yellow]")
        download(model)  # 调用 spaCy 的命令行下载功能
        nlp = spacy.load(model)  # 下载后再次尝试加载
        
    rprint("[green]✅ NLP (spaCy) 模型加载成功！[/green]")
    return nlp

# ----------------------------------------------------------------------------
# 定义中间过程日志文件路径
# 这些常量用于指定不同句子分割策略产生的中间结果的保存位置，便于调试和分析。
# ----------------------------------------------------------------------------

# 用于保存“按逗号分割”策略结果的日志文件
SPLIT_BY_COMMA_FILE = "output/log/split_by_comma.txt"
# 用于保存“按连接词分割”策略结果的日志文件
SPLIT_BY_CONNECTOR_FILE = "output/log/split_by_connector.txt"
# 用于保存“按标点分割”策略结果的日志文件
SPLIT_BY_MARK_FILE = "output/log/split_by_mark.txt"
