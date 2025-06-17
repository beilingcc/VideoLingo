# -*- coding: utf-8 -*-
"""
本模块封装了通过 302.ai 平台调用 F5-TTS 服务进行声音克隆的功能。

核心流程:
1. **参考音频选择与合并**: `_get_ref_audio` 函数从一个包含多个音频片段的列表中，智能选择一组片段，
   将它们合并成一个总时长在8到14.5秒之间的参考音频。这是 F5-TTS 获得最佳效果所推荐的时长范围。
2. **音频上传**: `upload_file_to_302` 函数将本地生成的参考音频文件上传到 302.ai 的服务器，并获取一个可供调用的 URL。
3. **TTS 调用**: `_f5_tts` 函数使用上传后的参考音频 URL 和目标文本，向 302.ai 的 F5-TTS 接口发起请求，生成克隆声音的音频。
4. **缓存机制**: 为了效率，成功上传一次参考音频后，其 URL 会被存储在全局变量 `UPLOADED_REFER_URL` 中。
   在后续的同一次任务中，将直接复用此 URL，避免了反复创建和上传同一个参考音频，显著提高了处理速度。
5. **主函数封装**: `f5_tts_for_videolingo` 是暴露给外部调用的主函数，它协调了以上所有步骤，实现了完整的“获取参考 -> 上传 -> 调用TTS”的逻辑。

依赖:
- `requests`: 用于文件上传。
- `pydub`: 用于合并音频片段和添加静音。
- `core.utils`: 用于加载 API 密钥和打印彩色日志。
- `core.asr_backend.audio_preprocess`: 用于对合并后的参考音频进行音量标准化，以提升克隆效果。
"""

# 导入标准库
import http.client  # 用于发起HTTP请求
import json         # 用于处理JSON数据
import os           # 用于操作系统相关功能，如文件路径处理

# 导入第三方库
import requests               # 更方便的HTTP请求库
from pydub import AudioSegment  # 用于音频处理，如合并、添加静音等

# 导入项目内部模块
from core.asr_backend.audio_preprocess import normalize_audio_volume  # 音频预处理：音量标准化
from core.utils import load_key, rprint, _AUDIO_REFERS_DIR  # 导入自定义工具函数和常量

# --- 全局变量和初始化 ---

# 从配置文件加载F5-TTS服务的API密钥
API_KEY = load_key("f5tts.302_api")
# 用于缓存上传后的参考音频URL，避免在同一次任务中重复创建和上传
UPLOADED_REFER_URL = None


def upload_file_to_302(file_path: str) -> str:
    """
    将本地文件上传到 302.ai 的文件服务器。

    Args:
        file_path (str): 要上传的本地文件的路径。

    Returns:
        str: 上传成功后返回的文件 URL，如果失败则返回 None。
    """
    api_key = load_key("f5tts.302_api")  # 重新加载以确保获取最新密钥
    url = "https://api.302.ai/302/upload-file"  # 上传接口地址
    
    # 准备要上传的文件数据 (multipart/form-data)
    try:
        with open(file_path, 'rb') as f:
            files = [('file', (os.path.basename(file_path), f, 'application/octet-stream'))]
            headers = {'Authorization': f'Bearer {api_key}'}  # 设置认证头
            
            # 发送POST请求进行上传
            response = requests.post(url, headers=headers, files=files)
            response.raise_for_status()  # 如果HTTP状态码不是200-299，则抛出异常

            response_data = response.json()
            if response_data.get('code') == 200:
                rprint(f"[green]文件上传成功: {file_path}")
                return response_data.get('data')  # 返回文件URL
            else:
                rprint(f"[red]文件上传API返回错误: {response_data}")
                return None
    except requests.exceptions.RequestException as e:
        rprint(f"[red]文件上传请求失败: {e}")
        return None
    except IOError as e:
        rprint(f"[red]读取文件失败: {e}")
        return None


def _f5_tts(text: str, refer_url: str, save_path: str) -> bool:
    """
    调用 302.ai 的 F5-TTS 接口，生成语音并保存到本地。

    Args:
        text (str): 要转换为语音的文本。
        refer_url (str): 经过上传后获得的参考音频的 URL。
        save_path (str): 生成的音频文件的保存路径。

    Returns:
        bool: 成功返回 True，失败返回 False。
    """
    conn = http.client.HTTPSConnection("api.302.ai")
    payload = json.dumps({"gen_text": text, "ref_audio_url": refer_url, "model_type": "F5-TTS"})
    headers = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}

    try:
        # 提交TTS任务
        conn.request("POST", "/302/submit/f5-tts", payload, headers)
        res = conn.getresponse()
        data = json.loads(res.read().decode("utf-8"))
        
        # 检查响应中是否包含有效的音频URL
        if res.status == 200 and "audio_url" in data and "url" in data["audio_url"]:
            audio_url = data["audio_url"]["url"]
            
            # 下载生成的音频文件
            rprint(f"[dim]正在下载生成的音频: {audio_url}[/dim]")
            audio_response = requests.get(audio_url)
            audio_response.raise_for_status()
            
            with open(save_path, "wb") as f:
                f.write(audio_response.content)
            rprint(f"[green]音频文件已保存到: {save_path}")
            return True
        else:
            rprint(f"[red]TTS 请求失败: {data}")
            return False
    except Exception as e:
        rprint(f"[red]执行 F5-TTS 请求时发生异常: {e}")
        return False
    finally:
        conn.close()


def _merge_audio(files: list, output: str) -> bool:
    """
    将多个 WAV 音频文件合并为一个，并在每个文件之间添加短暂的静音。

    Args:
        files (list): 要合并的 WAV 文件路径列表。
        output (str): 合并后输出的 WAV 文件路径。

    Returns:
        bool: 成功返回 True，失败返回 False。
    """
    try:
        combined = AudioSegment.empty()  # 创建一个空的音频段
        silence = AudioSegment.silent(duration=100)  # 100毫秒的静音
        
        # 逐个添加音频文件和静音
        for file in files:
            audio = AudioSegment.from_wav(file)
            combined += audio + silence
        
        # 导出为 16kHz, 16-bit, 单声道的 WAV 文件，这是许多TTS模型推荐的格式
        combined.export(output, format="wav", parameters=["-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1"])
        
        if not os.path.exists(output) or os.path.getsize(output) == 0:
            rprint(f"[red]错误: 合并后的输出文件不存在或大小为0。")
            return False
            
        rprint(f"[green]成功合并 {len(files)} 个音频文件到: {output}")
        return True
        
    except Exception as e:
        rprint(f"[red]合并音频时发生错误: {e}")
        return False


def _get_ref_audio(task_df, min_duration=8, max_duration=14.5) -> str:
    """
    从任务数据帧中智能选择合适的音频片段，合并成一个参考音频。
    该函数旨在创建一个总时长在 `min_duration` 和 `max_duration` 之间的音频文件，以达到最佳克隆效果。

    Args:
        task_df (pd.DataFrame): 包含待处理任务信息的 Pandas DataFrame，应有 'duration' 和 'number' 列。
        min_duration (int, optional): 参考音频的最小总时长（秒）。默认为 8。
        max_duration (float, optional): 参考音频的最大总时长（秒）。默认为 14.5。

    Returns:
        str: 成功时返回合并后的参考音频文件路径，失败则返回 None。
    """
    rprint(f"[blue]🎯 开始从 {len(task_df)} 个片段中选择参考音频 (目标时长: {min_duration}-{max_duration}s)...[/blue]")
    
    total_duration = 0
    selected_rows = []
    
    # 贪心算法：遍历所有音频片段，构建参考音频
    for _, row in task_df.iterrows():
        current_duration = row['duration']
        
        # 如果加上当前片段会超过最大时长，则跳过此片段
        if total_duration + current_duration > max_duration:
            continue
            
        # 添加片段
        selected_rows.append(row)
        total_duration += current_duration
        
        # 一旦总时长达到最小要求，就停止选择，避免参考音频过长
        if total_duration >= min_duration:
            break
    
    # 如果循环结束后总时长仍未达到最小要求
    if total_duration < min_duration:
        rprint(f"[red]❌ 错误: 未能找到足够的音频片段来构成最少 {min_duration}s 的参考音频。当前总时长: {total_duration:.2f}s")
        return None
        
    rprint(f"[blue]📊 已选择 {len(selected_rows)} 个片段, 总时长: {total_duration:.2f}s")
    
    audio_files = [os.path.join(_AUDIO_REFERS_DIR, f"{row['number']}.wav") for row in selected_rows]
    rprint(f"[yellow]🎵 准备合并以下音频文件: {', '.join(os.path.basename(f) for f in audio_files)}")
    
    combined_audio_path = os.path.join(_AUDIO_REFERS_DIR, "refer.wav")
    success = _merge_audio(audio_files, combined_audio_path)
    
    if not success:
        rprint(f"[red]❌ 错误: 合并所选的音频文件失败。")
        return None
    
    rprint(f"[green]✅ 成功创建合并的参考音频: {combined_audio_path}")
    return combined_audio_path


def f5_tts_for_videolingo(text: str, save_as: str, number: int, task_df):
    """
    VideoLingo 项目的主 F5-TTS 调用函数。
    该函数协调了参考音频的获取、标准化、上传和缓存，并最终调用 TTS 服务。

    Args:
        text (str): 需要转换为语音的文本。
        save_as (str): 生成的音频文件的保存路径。
        number (int): 当前任务的编号（此函数中未使用，但为保持接口一致性而保留）。
        task_df (pd.DataFrame): 包含所有音频片段信息的 DataFrame，用于创建参考音频。

    Returns:
        bool: TTS 任务是否成功。
    """
    global UPLOADED_REFER_URL
    
    try:
        # 步骤 1: 检查是否已有缓存的参考音频 URL
        if UPLOADED_REFER_URL is None:
            rprint("[cyan]首次调用 F5-TTS，正在准备参考音频...[/cyan]")
            # 步骤 1a: 获取合并的参考音频路径
            refer_path = _get_ref_audio(task_df)
            if not refer_path:
                return False  # 如果无法获取参考音频，则直接失败
            
            # 步骤 1b: 对参考音频进行音量标准化
            normalized_refer_path = os.path.join(_AUDIO_REFERS_DIR, "refer_normalized.wav")
            normalize_audio_volume(refer_path, normalized_refer_path)
            rprint(f"[green]参考音频已进行音量标准化: {normalized_refer_path}")

            # 步骤 1c: 上传标准化后的参考音频并缓存 URL
            UPLOADED_REFER_URL = upload_file_to_302(normalized_refer_path)
            if not UPLOADED_REFER_URL:
                rprint("[red]❌ 错误: 上传参考音频失败，无法继续执行 F5-TTS。")
                return False
            rprint(f"[green]✅ 参考音频已上传并缓存 URL，后续将复用此 URL。")
        else:
            rprint("[cyan]检测到已缓存的参考音频 URL，直接复用。[/cyan]")
        
        # 步骤 2: 使用文本和参考音频 URL 调用 TTS 服务
        success = _f5_tts(text=text, refer_url=UPLOADED_REFER_URL, save_path=save_as)
        return success
        
    except Exception as e:
        rprint(f"[bold red]在执行 f5_tts_for_videolingo 主流程时发生未预料的错误: {e}")
        return False
        print(f"f5_tts_for_videolingo 中发生错误: {str(e)}")
        return False

# --- 测试代码 ---
if __name__ == "__main__":
    test_refer_url = "https://file.302.ai/gpt/imgs/20250226/717e574dc8e440e3b6f8cb4b3acb40e0.mp3"
    test_text = "你好，世界！"
    test_save_as = "test_f5_tts.wav"
    success = _f5_tts(text=test_text, refer_url=test_refer_url, save_path=test_save_as)
    print(f"测试结果: {success}")