# -*- coding: utf-8 -*-
"""
本模块封装了与 SiliconFlow Fish-Speech TTS 服务相关的 API 调用和音频处理功能。

核心功能包括:
1.  **TTS 音频生成**: 支持三种模式调用 `siliconflow_fish_tts` 函数：
    - `preset`: 使用在 `config.yaml` 中预设的官方音色。
    - `custom`: 使用通过 `create_custom_voice` 创建并返回的自定义音色 ID。
    - `dynamic`: 提供参考音频和对应文本，进行即时的声音克隆（零样本 TTS）。
2.  **自定义音色创建**: `create_custom_voice` 函数允许用户上传一段音频和对应的文本，
    在 SiliconFlow 平台创建永久性的自定义音色，并返回一个可复用的 `voice_id`。
3.  **参考音频准备**: `get_ref_audio` 函数为 `dynamic` 模式智能准备参考材料。
    它会从任务列表中选择合适的音频片段，将它们合并，并确保总文本长度在 API 限制内。
4.  **音频合并**: `merge_audio` 是一个工具函数，用于将多个 WAV 文件合并成一个，
    并在片段之间插入短暂的静音，以提高合成质量。

依赖:
- `requests`: 用于发送 HTTP API 请求。
- `pydub`: 用于音频处理，如合并和添加静音。
- `rich`: 用于在控制台美化输出。
- `core.utils`: 提供通用工具，如加载配置、异常处理等。

使用前，请确保在 `config.yaml` 中配置了 `sf_fish_tts` 的 `api_key` 和默认 `voice`。
"""
import os
import time
import uuid
import base64
import requests
from pathlib import Path
from pydub import AudioSegment
from rich.panel import Panel
from rich.text import Text
from core.asr_backend.audio_preprocess import get_audio_duration
from core.utils import load_key, except_handler, rprint
from core.utils.models import _AUDIO_REFERS_DIR

# API 端点地址
API_URL_SPEECH = "https://api.siliconflow.cn/v1/audio/speech"  # TTS 合成接口
API_URL_VOICE = "https://api.siliconflow.cn/v1/uploads/audio/voice" # 自定义音色创建接口

# 模型和参数配置
MODEL_NAME = "fishaudio/fish-speech-1.4"  # 使用的 TTS 模型
REFER_MAX_LENGTH = 90  # 参考音频对应的文本最大长度限制


@except_handler("使用 SiliconFlow Fish TTS 生成音频失败", retry=2, delay=1)
def siliconflow_fish_tts(text: str, save_path: str, mode: str = "preset", voice_id: str = None, ref_audio: str = None, ref_text: str = None, check_duration: bool = False):
    """
    调用 SiliconFlow Fish TTS API 生成音频，支持多种音色模式。

    Args:
        text (str): 要转换为语音的文本。
        save_path (str): 音频文件的保存路径。
        mode (str, optional): 音色模式，可选 'preset', 'custom', 'dynamic'。默认为 'preset'。
        voice_id (str, optional): 自定义音色ID，在 'custom' 模式下必须提供。
        ref_audio (str, optional): 参考音频文件路径，在 'dynamic' 模式下必须提供。
        ref_text (str, optional): 参考音频对应的文本，在 'dynamic' 模式下必须提供。
        check_duration (bool, optional): 是否在生成后检查并打印音频时长。默认为 False。

    Returns:
        bool: 成功返回 True，失败返回 False。

    Raises:
        ValueError: 如果模式无效或缺少所需参数。
    """
    sf_fish_set = load_key("sf_fish_tts")
    headers = {"Authorization": f'Bearer {sf_fish_set["api_key"]}', "Content-Type": "application/json"}
    payload = {"model": MODEL_NAME, "response_format": "wav", "stream": False, "input": text}

    # --- 根据不同模式构建请求体 ---
    if mode == "preset":
        # 使用配置文件中预设的音色
        payload["voice"] = f"fishaudio/fish-speech-1.4:{sf_fish_set['voice']}"
    elif mode == "custom":
        # 使用用户提供的自定义音色 ID
        if not voice_id:
            raise ValueError("自定义模式 (custom) 需要提供 voice_id")
        payload["voice"] = voice_id
    elif mode == "dynamic":
        # 使用参考音频和文本进行即时声音克隆
        if not ref_audio or not ref_text:
            raise ValueError("动态模式 (dynamic) 需要提供 ref_audio 和 ref_text")
        with open(ref_audio, 'rb') as f:
            audio_base64 = base64.b64encode(f.read()).decode('utf-8')
        payload.update({
            "voice": None,
            "references": [{"audio": f"data:audio/wav;base64,{audio_base64}", "text": ref_text}]
        })
    else:
        raise ValueError(f"无效的模式: '{mode}'")

    response = requests.post(API_URL_SPEECH, json=payload, headers=headers)

    if response.status_code == 200:
        wav_file_path = Path(save_path).with_suffix('.wav')
        wav_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(wav_file_path, 'wb') as f:
            f.write(response.content)

        if check_duration:
            duration = get_audio_duration(wav_file_path)
            rprint(f"[blue]音频时长: {duration:.2f} 秒")

        rprint(f"[green]音频文件生成成功: {wav_file_path}")
        return True
    else:
        # 使用 rprint 美化错误输出
        error_msg = response.json()
        rprint(f"[red]音频生成失败 | HTTP {response.status_code}")
        rprint(f"[red]文本: {text}")
        rprint(f"[red]错误详情: {error_msg}")
        return False


@except_handler("创建自定义音色失败")
def create_custom_voice(audio_path: str, text: str, custom_name: str = None):
    """
    上传音频和文本到 SiliconFlow 以创建自定义音色。

    Args:
        audio_path (str): 用于创建音色的 WAV 音频文件路径。
        text (str): 音频文件中对应的文本。
        custom_name (str, optional): 为音色指定的自定义名称。如果未提供，则生成一个随机名称。

    Returns:
        str: 创建成功后返回的音色 ID (voice_id)，失败则抛出异常。

    Raises:
        FileNotFoundError: 如果音频文件不存在。
        ValueError: 如果 API 请求失败。
    """
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    # 将音频文件编码为 Base64
    audio_base64 = f"data:audio/wav;base64,{base64.b64encode(open(audio_path, 'rb').read()).decode('utf-8')}"
    rprint(f"[yellow]音频文件编码成功")

    # 构建请求体
    payload = {
        "audio": audio_base64,
        "model": MODEL_NAME,
        "customName": custom_name or str(uuid.uuid4())[:8], # 如果没有提供名称，则生成一个
        "text": text
    }

    rprint(f"[yellow]发送创建音色请求...")
    api_key = load_key("sf_fish_tts.api_key")
    headers = {"Authorization": f'Bearer {api_key}', "Content-Type": "application/json"}
    response = requests.post(API_URL_VOICE, json=payload, headers=headers)
    response_json = response.json()

    if response.status_code == 200:
        voice_id = response_json.get('uri')
        status_text = Text()
        status_text.append("✨ 自定义音色创建成功!\n", style="green")
        status_text.append(f"🎙️ 音色ID: {voice_id}\n", style="green")
        status_text.append(f"⏳ 创建时间: {time.strftime('%Y-%m-%d %H:%M:%S')}", style="green")
        rprint(Panel(status_text, title="音色创建状态", border_style="green"))
        return voice_id
    else:
        error_text = Text()
        error_text.append("❌ 自定义音色创建失败\n", style="red")
        error_text.append(f"⚠️ HTTP状态: {response.status_code}\n", style="red")
        error_text.append(f"💬 错误详情: {response_json}", style="red")
        rprint(Panel(error_text, title="错误", border_style="red"))
        raise ValueError(f"自定义音色创建失败 ❌ HTTP {response.status_code}, 错误详情: {response_json}")


@except_handler("合并音频失败")
def merge_audio(files: list, output: str) -> bool:
    """
    将多个 WAV 音频文件合并为一个，并在它们之间插入短暂的静音。

    Args:
        files (list): 包含待合并音频文件路径的列表。
        output (str): 合并后输出文件的路径。

    Returns:
        bool: 成功返回 True，失败返回 False。
    """
    combined = AudioSegment.empty()
    silence = AudioSegment.silent(duration=100)  # 100毫秒静音

    for file in files:
        audio = AudioSegment.from_wav(file)
        combined += audio + silence

    # 导出为特定格式的 WAV 文件
    combined.export(output, format="wav", parameters=["-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1"])

    if os.path.getsize(output) == 0:
        rprint(f"[red]输出文件 '{output}' 大小为0，合并可能失败。")
        return False

    rprint(f"[green]音频合并成功: {output}")
    return True


def get_ref_audio(task_df):
    """
    从任务 DataFrame 中选择并合并音频片段，以创建用于声音克隆的参考音频和文本。

    该函数会迭代字幕片段，选择总文本长度不超过 `REFER_MAX_LENGTH` 的片段进行合并，
    同时确保总时长不超过10秒，以满足 API 的要求并提高克隆效果。

    Args:
        task_df (pd.DataFrame): 包含 'origin', 'duration', 'number' 列的任务数据。

    Returns:
        tuple[str, str] or tuple[None, None]: 
            成功时返回 (合并后的音频路径, 合并后的文本)，
            如果找不到合适的片段或合并失败，则返回 (None, None)。
    """
    rprint(f"[blue]🎯 开始智能选择参考音频...")

    duration = 0
    selected_rows = []
    combined_text = ""
    found_first = False

    for _, row in task_df.iterrows():
        current_text = row['origin']

        # 寻找第一个符合长度要求的片段作为起点
        if not found_first:
            if len(current_text) <= REFER_MAX_LENGTH:
                selected_rows.append(row)
                combined_text = current_text
                duration += row['duration']
                found_first = True
                rprint(f"[yellow]📝 找到首个合格片段: '{current_text[:50]}...' (长度: {len(current_text)})")
            else:
                rprint(f"[yellow]⏭️ 跳过过长片段: '{current_text[:50]}...' (长度: {len(current_text)})")
            continue

        # 在第一个片段的基础上继续添加，直到超过长度或时长限制
        new_text = combined_text + " " + current_text
        if len(new_text) > REFER_MAX_LENGTH:
            rprint(f"[blue]文本长度将超限 ({len(new_text)} > {REFER_MAX_LENGTH})，停止添加。")
            break

        selected_rows.append(row)
        combined_text = new_text
        duration += row['duration']
        rprint(f"[yellow]📝 添加片段: '{current_text[:50]}...' (当前总长: {len(combined_text)})")

        if duration > 10: # 限制总时长不超过10秒
            rprint(f"[blue]音频总时长超过10秒 ({duration:.2f}s)，停止添加。")
            break

    if not selected_rows:
        rprint(f"[red]❌ 未找到任何长度小于 {REFER_MAX_LENGTH} 字符的合格片段。")
        return None, None

    rprint(f"[blue]📊 已选 {len(selected_rows)} 个片段，总时长: {duration:.2f}s")

    audio_files = [f"{_AUDIO_REFERS_DIR}/{row['number']}.wav" for row in selected_rows]
    rprint(f"[yellow]🎵 待合并音频: {audio_files}")

    combined_audio_path = f"{_AUDIO_REFERS_DIR}/combined_reference.wav"
    success = merge_audio(audio_files, combined_audio_path)

    if not success:
        rprint(f"[red]❌ 合并参考音频失败。")
        return None, None

    rprint(f"[green]✅ 合成参考音频成功: {combined_audio_path}")
    rprint(f"[green]📝 最终参考文本: '{combined_text}' | 长度: {len(combined_text)}")

    return combined_audio_path, combined_text

# ------------
# VideoLingo专用TTS入口，自动根据配置选择模式
# ------------
def siliconflow_fish_tts_for_videolingo(text, save_as, number, task_df):
    sf_fish_set = load_key("sf_fish_tts")
    MODE = sf_fish_set["mode"]

    if MODE == "preset":
        return siliconflow_fish_tts(text, save_as, mode="preset")
    elif MODE == "custom":
        video_file = find_video_files()
        custom_name = hashlib.md5(video_file.encode()).hexdigest()[:8]
        rprint(f"[yellow]使用自定义名: {custom_name}")
        log_name = load_key("sf_fish_tts.custom_name")
        
        if log_name != custom_name:
            # 获取合并后的参考音频和文本
            ref_audio, ref_text = get_ref_audio(task_df)
            if ref_audio is None or ref_text is None:
                rprint(f"[red]获取参考音频和文本失败，回退到预设模式")
                return siliconflow_fish_tts(text, save_as, mode="preset")
                
            voice_id = create_custom_voice(ref_audio, ref_text, custom_name)
            update_key("sf_fish_tts.voice_id", voice_id)
            update_key("sf_fish_tts.custom_name", custom_name)
        else:
            voice_id = load_key("sf_fish_tts.voice_id")
        return siliconflow_fish_tts(text=text, save_path=save_as, mode="custom", voice_id=voice_id)
    elif MODE == "dynamic":
        ref_audio_path = f"{_AUDIO_REFERS_DIR}/{number}.wav"
        if not Path(ref_audio_path).exists():
            rprint(f"[red]参考音频未找到: {ref_audio_path}，回退到预设模式")
            return siliconflow_fish_tts(text, save_as, mode="preset")
            
        ref_text = task_df[task_df['number'] == number]['origin'].iloc[0]
        return siliconflow_fish_tts(text=text, save_path=save_as, mode="dynamic", ref_audio=str(ref_audio_path), ref_text=ref_text)
    else:
        raise ValueError("无效模式。请选择 'preset', 'custom', 或 'dynamic'")

if __name__ == '__main__':
    pass
    # create_custom_voice("output/audio/refers/1.wav", "Okay folks, welcome back. This is price action model number four, position trading.")
    siliconflow_fish_tts("가을 나뭇잎이 부드럽게 떨어지는 생생한 색깔을 주목하지 않을 수 없었다", "preset_test.wav", mode="preset", check_duration=True)
    # siliconflow_fish_tts("使用客制化音色测试", "custom_test.wav", mode="custom", voice_id="speech:your-voice-name:cm04pf7az00061413w7kz5qxs:mjtkgbyuunvtybnsvbxd")
    # siliconflow_fish_tts("使用动态音色测试", "dynamic_test.wav", mode="dynamic", ref_audio="output/audio/refers/1.wav", ref_text="Okay folks, welcome back. This is price action model number four, position trading.")
