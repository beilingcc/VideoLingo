# ------------------------------------------
# 定义中间产出文件
# ------------------------------------------

# 转录后的清理后的文本块
_2_CLEANED_CHUNKS = "output/log/cleaned_chunks.xlsx"
# NLP分割后的文本
_3_1_SPLIT_BY_NLP = "output/log/split_by_nlp.txt"
# 基于语义分割后的文本
_3_2_SPLIT_BY_MEANING = "output/log/split_by_meaning.txt"
# 术语表JSON文件
_4_1_TERMINOLOGY = "output/log/terminology.json"
# 翻译结果文件
_4_2_TRANSLATION = "output/log/translation_results.xlsx"
# 为字幕分割的翻译结果
_5_SPLIT_SUB = "output/log/translation_results_for_subtitles.xlsx"
# 重新合并的翻译结果
_5_REMERGED = "output/log/translation_results_remerged.xlsx"

# 音频任务定义文件
_8_1_AUDIO_TASK = "output/audio/tts_tasks.xlsx"


# ------------------------------------------
# 定义音频文件
# ------------------------------------------
# 输出目录
_OUTPUT_DIR = "output"
# 音频目录
_AUDIO_DIR = "output/audio"
# 原始音频文件
_RAW_AUDIO_FILE = "output/audio/raw.mp3"
# 人声音频文件
_VOCAL_AUDIO_FILE = "output/audio/vocal.mp3"
# 背景音频文件
_BACKGROUND_AUDIO_FILE = "output/audio/background.mp3"
# 参考音频目录
_AUDIO_REFERS_DIR = "output/audio/refers"
# 音频片段目录
_AUDIO_SEGS_DIR = "output/audio/segs"
# 音频临时文件目录
_AUDIO_TMP_DIR = "output/audio/tmp"

# ------------------------------------------
# 导出
# ------------------------------------------

# 导出所有变量，使其可以通过from core.utils.models import *导入
__all__ = [
    "_2_CLEANED_CHUNKS",
    "_3_1_SPLIT_BY_NLP",
    "_3_2_SPLIT_BY_MEANING",
    "_4_1_TERMINOLOGY",
    "_4_2_TRANSLATION",
    "_5_SPLIT_SUB",
    "_5_REMERGED",
    "_8_1_AUDIO_TASK",
    "_OUTPUT_DIR",
    "_AUDIO_DIR",
    "_RAW_AUDIO_FILE",
    "_VOCAL_AUDIO_FILE",
    "_BACKGROUND_AUDIO_FILE",
    "_AUDIO_REFERS_DIR",
    "_AUDIO_SEGS_DIR",
    "_AUDIO_TMP_DIR"
]
