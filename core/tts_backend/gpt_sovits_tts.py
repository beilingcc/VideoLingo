# -*- coding: utf-8 -*-
"""
本模块用于集成和调用 GPT-SoVITS 本地推理服务，实现高质量的文本转语音功能。

主要功能:
- 自动检测并启动 GPT-SoVITS 的 API 服务器。
- 支持 Windows 和 macOS (手动启动) 平台。
- 根据配置文件，灵活处理三种不同的参考音频模式。
- 封装了向 GPT-SoVITS API 发送 TTS 请求的逻辑。
- 对输入语言进行检查和标准化处理。
- 提供了针对 VideoLingo 项目的特定调用流程 `gpt_sovits_tts_for_videolingo`。
"""

from pathlib import Path
import requests
import os, sys
import subprocess
import socket
import time
from core.utils import load_key, find_and_check_config_path, rprint

def check_lang(text_lang: str, prompt_lang: str) -> tuple[str, str]:
    """
    检查并标准化文本语言和提示文本语言，确保它们是支持的格式 ('zh' 或 'en')。
    """
    # 标准化目标文本语言
    if any(lang in text_lang.lower() for lang in ['zh', 'cn', '中文', 'chinese']):
        text_lang = 'zh'
    elif any(lang in text_lang.lower() for lang in ['英文', '英语', 'english']):
        text_lang = 'en'
    else:
        raise ValueError("不支持的文本语言。目前只支持中文和英文。")
    
    # 标准化参考文本语言
    if any(lang in prompt_lang.lower() for lang in ['en', 'english', '英文', '英语']):
        prompt_lang = 'en'
    elif any(lang in prompt_lang.lower() for lang in ['zh', 'cn', '中文', 'chinese']):
        prompt_lang = 'zh'
    else:
        raise ValueError("不支持的提示语言。目前只支持中文和英文。")
    return text_lang, prompt_lang

def gpt_sovits_tts(text: str, text_lang: str, save_path: str, ref_audio_path: str, prompt_lang: str, prompt_text: str) -> bool:
    """
    向 GPT-SoVITS 服务器发送 TTS 请求并保存生成的音频。
    """
    text_lang, prompt_lang = check_lang(text_lang, prompt_lang)

    current_dir = Path.cwd()
    
    payload = {
        'text': text,                      # 要合成的文本
        'text_lang': text_lang,            # 文本的语言
        'ref_audio_path': str(ref_audio_path), # 参考音频路径
        'prompt_lang': prompt_lang,        # 参考文本的语言
        'prompt_text': prompt_text,        # 参考文本内容
        "speed_factor": 1.0,               # 语速因子
    }

    def save_audio(response, save_path, current_dir):
        """辅助函数，用于保存音频文件。"""
        if save_path:
            full_save_path = current_dir / save_path
            full_save_path.parent.mkdir(parents=True, exist_ok=True)
            full_save_path.write_bytes(response.content)
            rprint(f"[bold green]音频保存成功:[/bold green] {full_save_path}")
        return True

    try:
        response = requests.post('http://127.0.0.1:9880/tts', json=payload)
        if response.status_code == 200:
            return save_audio(response, save_path, current_dir)
        else:
            rprint(f"[bold red]TTS 请求失败，状态码:[/bold red] {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        rprint(f"[bold red]无法连接到 GPT-SoVITS 服务器: {e}[/bold red]")
        return False

def gpt_sovits_tts_for_videolingo(text: str, save_as: str, number: int, task_df):
    """
    为 VideoLingo 项目定制的 TTS 函数，处理不同的参考音频模式。
    """
    start_gpt_sovits_server()  # 确保服务器已启动
    
    # 从配置加载所需参数
    TARGET_LANGUAGE = load_key("target_language")
    WHISPER_LANGUAGE = load_key("whisper.language")
    sovits_set = load_key("gpt_sovits")
    DUBBING_CHARACTER = sovits_set["character"]
    REFER_MODE = sovits_set["refer_mode"]

    current_dir = Path.cwd()
    prompt_lang = load_key("whisper.detected_language") if WHISPER_LANGUAGE == 'auto' else WHISPER_LANGUAGE
    prompt_text = task_df.loc[task_df['number'] == number, 'origin'].values[0]

    # 根据不同的参考模式 (REFER_MODE) 确定参考音频路径和提示文本
    if REFER_MODE == 1:
        # 模式1：使用配置文件中指定的默认参考音频
        _, config_path = find_and_check_config_path(DUBBING_CHARACTER)
        config_dir = config_path.parent

        ref_audio_files = list(config_dir.glob(f"{DUBBING_CHARACTER}_*.wav")) + list(config_dir.glob(f"{DUBBING_CHARACTER}_*.mp3"))
        if not ref_audio_files:
            raise FileNotFoundError(f"在配置目录中未找到角色 '{DUBBING_CHARACTER}' 的参考音频文件。")
        ref_audio_path = ref_audio_files[0]

        content = ref_audio_path.stem.split('_', 1)[1]
        prompt_lang = 'zh' if any('\u4e00' <= char <= '\u9fff' for char in content) else 'en'
        prompt_text = content
        
    elif REFER_MODE in [2, 3]:
        # 模式2和3：使用从视频中提取的参考音频
        ref_audio_path = current_dir / ("output/audio/refers/1.wav" if REFER_MODE == 2 else f"output/audio/refers/{number}.wav")
        if not ref_audio_path.exists():
            # 如果参考音频不存在，尝试动态提取
            try:
                from core._9_refer_audio import extract_refer_audio_main
                rprint(f"[yellow]参考音频不存在，尝试提取: {ref_audio_path}[/yellow]")
                extract_refer_audio_main()
            except Exception as e:
                rprint(f"[bold red]提取参考音频失败: {e}[/bold red]")
                raise
    else:
        raise ValueError("无效的 REFER_MODE。请选择 1, 2, 或 3.")

    # 调用核心 TTS 函数
    success = gpt_sovits_tts(text, TARGET_LANGUAGE, save_as, ref_audio_path, prompt_lang, prompt_text)
    
    # 如果模式3失败，回退到模式2重试
    if not success and REFER_MODE == 3:
        rprint(f"[bold red]TTS 请求失败，切换到模式2并重试...[/bold red]")
        ref_audio_path = current_dir / "output/audio/refers/1.wav"
        gpt_sovits_tts(text, TARGET_LANGUAGE, save_as, ref_audio_path, prompt_lang, prompt_text)

def start_gpt_sovits_server():
    """
    检查端口，如果未被占用，则启动 GPT-SoVITS API 服务器。
    """
    # 检查端口 9880 是否已被占用
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sock.connect_ex(('127.0.0.1', 9880)) == 0:
            # print("GPT-SoVITS server is already running.")
            return  # 端口已被占用，说明服务器已启动

    rprint("[bold yellow]🚀 正在初始化 GPT-SoVITS 服务器...[/bold yellow]")
    rprint("[bold red]⏳ 请耐心等待约1分钟，API服务将会在新的命令提示符窗口中启动。[/bold red]")
    
    # 查找并校验配置文件路径
    gpt_sovits_dir, config_path = find_and_check_config_path(load_key("gpt_sovits.character"))

    original_dir = Path.cwd()
    os.chdir(gpt_sovits_dir)  # 切换到 GPT-SoVITS 目录以正确启动服务

    # 根据操作系统平台启动服务器
    if sys.platform == "win32":
        cmd = [
            "runtime\\python.exe", "api_v2.py",
            "-a", "127.0.0.1", "-p", "9880",
            "-c", str(config_path)
        ]
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
    elif sys.platform == "darwin":  # macOS
        rprint("[bold yellow]macOS 用户请手动启动 GPT-SoVITS 服务器 (api_v2.py)。[/bold yellow]")
        # 此处可以添加手动确认的逻辑
    else:
        os.chdir(original_dir)
        raise OSError("不支持的操作系统。目前仅支持 Windows 和 macOS。")

    os.chdir(original_dir)  # 切回原始工作目录

    # 等待服务器启动成功 (设置超时)
    start_time = time.time()
    while time.time() - start_time < 60:
        time.sleep(5) # 每5秒检查一次
        try:
            response = requests.get('http://127.0.0.1:9880/ping')
            if response.status_code == 200:
                rprint("[bold green]✅ GPT-SoVITS 服务器已就绪。[/bold green]")
                return
        except requests.exceptions.RequestException:
            continue # 连接失败，继续等待

    raise Exception("GPT-SoVITS 服务器在60秒内未能成功启动。请检查 GPT-SoVITS-v2 文件夹配置是否正确。")
