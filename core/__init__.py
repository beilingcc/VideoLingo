# ------------
# 核心模块初始化文件
# 使用try-except结构避免在安装过程中出现导入错误
# ------------
try:
    # 导入所有核心处理模块
    from . import (
        _1_ytdlp,              # 视频下载模块
        _2_asr,                # 语音识别转录模块
        _3_1_split_nlp,        # 基于NLP的句子分割模块
        _3_2_split_meaning,    # 基于语义的句子分割模块
        _4_1_summarize,        # 内容摘要生成模块
        _4_2_translate,        # 内容翻译模块
        _5_split_sub,          # 字幕分割模块
        _6_gen_sub,            # 字幕生成模块
        _7_sub_into_vid,       # 字幕嵌入视频模块
        _8_1_audio_task,       # 音频任务生成模块
        _8_2_dub_chunks,       # 音频块处理模块
        _9_refer_audio,        # 参考音频提取模块
        _10_gen_audio,         # 音频生成模块
        _11_merge_audio,       # 音频合并模块
        _12_dub_to_vid         # 配音合并到视频模块
    )
    # 导入工具函数
    from .utils import *
    # 导入清理功能
    from .utils.onekeycleanup import cleanup
    # 导入删除配音文件功能
    from .utils.delete_retry_dubbing import delete_dubbing_files
except ImportError:
    # 如果导入失败，静默通过，避免安装过程中报错
    pass

# 定义模块导出的所有组件
__all__ = [
    'ask_gpt',               # GPT查询函数
    'load_key',              # 加载配置键值函数
    'update_key',            # 更新配置键值函数
    'cleanup',               # 清理功能
    'delete_dubbing_files',  # 删除配音文件功能
    '_1_ytdlp',              # 视频下载模块
    '_2_asr',                # 语音识别转录模块
    '_3_1_split_nlp',        # 基于NLP的句子分割模块
    '_3_2_split_meaning',    # 基于语义的句子分割模块
    '_4_1_summarize',        # 内容摘要生成模块
    '_4_2_translate',        # 内容翻译模块
    '_5_split_sub',          # 字幕分割模块
    '_6_gen_sub',            # 字幕生成模块
    '_7_sub_into_vid',       # 字幕嵌入视频模块
    '_8_1_audio_task',       # 音频任务生成模块
    '_8_2_dub_chunks',       # 音频块处理模块
    '_9_refer_audio',        # 参考音频提取模块
    '_10_gen_audio',         # 音频生成模块
    '_11_merge_audio',       # 音频合并模块
    '_12_dub_to_vid'         # 配音合并到视频模块
]
