# 导入所需的库
import os  # 用于操作系统相关操作
from core.st_utils.imports_and_utils import *  # 导入项目核心工具和库
from core.utils.onekeycleanup import cleanup  # 导入清理函数
from core.utils import load_key  # 导入加载配置的函数
import shutil  # 用于文件操作
from functools import partial  # 用于创建偏函数，方便调用
from rich.panel import Panel  # 用于创建美观的终端面板
from rich.console import Console  # 用于美化终端输出
from core import *  # 导入所有核心模块

# 初始化rich控制台
console = Console()

# --- 常量定义 ---
INPUT_DIR = 'batch/input'  # 批处理输入目录
OUTPUT_DIR = 'output'      # 临时输出目录
SAVE_DIR = 'batch/output'  # 最终保存目录
ERROR_OUTPUT_DIR = 'batch/output/ERROR'  # 错误文件保存目录
YTB_RESOLUTION_KEY = "ytb_resolution"  # YouTube视频下载分辨率的配置键

def process_video(file, dubbing=False, is_retry=False):
    """
    处理单个视频文件的核心流程函数。

    Args:
        file (str): 视频文件名或URL。
        dubbing (bool, optional): 是否执行配音流程。默认为 False。
        is_retry (bool, optional): 是否为重试任务。默认为 False。

    Returns:
        tuple: (bool, str, str) -> (处理是否成功, 发生错误的步骤, 错误信息)
    """
    # 如果不是重试任务，则清空并准备输出文件夹
    if not is_retry:
        prepare_output_folder(OUTPUT_DIR)
    
    # 定义文本处理（字幕生成）相关的步骤
    text_steps = [
        ("🎥 处理输入文件", partial(process_input_file, file)),
        ("🎙️ 使用Whisper进行语音转写", partial(_2_asr.transcribe)),
        ("✂️ 智能拆分句子", split_sentences),
        ("📝 总结与翻译", summarize_and_translate),
        ("⚡ 处理与对齐字幕", process_and_align_subtitles),
        ("🎬 将字幕合并到视频", _7_sub_into_vid.merge_subtitles_to_video),
    ]
    
    # 如果需要配音，则添加配音相关的步骤
    if dubbing:
        dubbing_steps = [
            ("🔊 生成音频任务", gen_audio_tasks),
            ("🎵 提取参考音频", _9_refer_audio.extract_refer_audio_main),
            ("🗣️ 生成配音音频", _10_gen_audio.gen_audio),
            ("🔄 合并为完整音频", _11_merge_audio.merge_full_audio),
            ("🎞️ 将配音合并到视频", _12_dub_to_vid.merge_video_audio),
        ]
        text_steps.extend(dubbing_steps)
    
    current_step = ""
    # 依次执行定义好的所有步骤
    for step_name, step_func in text_steps:
        current_step = step_name
        # 每个步骤最多重试3次
        for attempt in range(3):
            try:
                console.print(Panel(
                    f"[bold green]{step_name}[/]",
                    subtitle=f"尝试 {attempt + 1}/3" if attempt > 0 else None,
                    border_style="blue"
                ))
                result = step_func()  # 执行步骤函数
                if result is not None:
                    globals().update(result)  # 更新全局变量（如video_file）
                break  # 成功则跳出重试循环
            except Exception as e:
                # 如果3次尝试都失败
                if attempt == 2:
                    error_panel = Panel(
                        f"[bold red]步骤 '{current_step}' 出错:[/]\n{str(e)}",
                        border_style="red"
                    )
                    console.print(error_panel)
                    cleanup(ERROR_OUTPUT_DIR)  # 清理并备份错误文件
                    return False, current_step, str(e)  # 返回失败状态
                console.print(Panel(
                    f"[yellow]尝试 {attempt + 1} 失败。正在重试...[/]",
                    border_style="yellow"
                ))
    
    # 所有步骤成功完成
    console.print(Panel("[bold green]所有步骤成功完成! 🎉[/]", border_style="green"))
    cleanup(SAVE_DIR)  # 清理并保存最终文件
    return True, "", ""  # 返回成功状态

def prepare_output_folder(output_folder):
    """清空并创建指定的输出文件夹。"""
    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)  # 如果存在则删除
    os.makedirs(output_folder)  # 创建新文件夹

def process_input_file(file):
    """处理输入文件，如果是URL则下载，如果是本地文件则复制。"""
    if file.startswith('http'):
        # 下载YouTube视频
        _1_ytdlp.download_video_ytdlp(file, resolution=load_key(YTB_RESOLUTION_KEY))
        video_file = _1_ytdlp.find_video_files()  # 查找下载的视频文件
    else:
        # 复制本地视频文件到处理目录
        input_file = os.path.join('batch', 'input', file)
        output_file = os.path.join(OUTPUT_DIR, file)
        shutil.copy(input_file, output_file)
        video_file = output_file
    return {'video_file': video_file}  # 返回视频文件路径

def split_sentences():
    """执行句子拆分流程。"""
    _3_1_split_nlp.split_by_spacy()  # 基于NLP工具进行拆分
    _3_2_split_meaning.split_sentences_by_meaning()  # 基于语义进行拆分

def summarize_and_translate():
    """执行总结和翻译流程。"""
    _4_1_summarize.get_summary()  # 生成内容摘要
    _4_2_translate.translate_all()  # 进行翻译

def process_and_align_subtitles():
    """处理和对齐字幕。"""
    _5_split_sub.split_for_sub_main()  # 拆分字幕以匹配时长
    _6_gen_sub.align_timestamp_main()  # 对齐时间戳

def gen_audio_tasks():
    """为配音生成音频任务。"""
    _8_1_audio_task.gen_audio_task_main()  # 生成音频任务列表
    _8_2_dub_chunks.gen_dub_chunks()  # 生成配音片段
