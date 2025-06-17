# ------------
# 该模块用于调用302.ai的WhisperX API进行音频转录，并对结果进行缓存
# ------------
import os
import io
import json
import time
import requests
import librosa
import soundfile as sf
from rich import print as rprint
from core.utils import *
from core.utils.models import *

# 输出日志目录
OUTPUT_LOG_DIR = "output/log"

# ------------
# 使用302.ai WhisperX API进行音频转录
# 支持对音频片段进行切片、缓存、全局时间戳偏移等
# ------------
def transcribe_audio_302(raw_audio_path, vocal_audio_path, start = None, end = None):
    """
    使用302.ai的WhisperX API进行音频转录，并对结果进行缓存。
    参数:
        raw_audio_path (str): 原始音频文件路径
        vocal_audio_path (str): 人声音频文件路径
        start (float): 起始时间（秒）
        end (float): 结束时间（秒）
    返回:
        dict: 转录结果（包含分段和词级时间戳）
    """
    # 创建日志目录
    os.makedirs(OUTPUT_LOG_DIR, exist_ok=True)
    LOG_FILE = f"{OUTPUT_LOG_DIR}/whisperx302_{start}_{end}.json"
    # 如果已存在缓存，直接读取
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # 获取语言设置
    WHISPER_LANGUAGE = load_key("whisper.language")
    update_key("whisper.language", WHISPER_LANGUAGE)
    url = "https://api.302.ai/302/whisperx"
    # 读取音频并按需切片
    y, sr = librosa.load(vocal_audio_path, sr=16000)
    audio_duration = len(y) / sr
    if start is None or end is None:
        start = 0
        end = audio_duration
    start_sample = int(start * sr)
    end_sample = int(end * sr)
    y_slice = y[start_sample:end_sample]
    # 写入内存缓冲区
    audio_buffer = io.BytesIO()
    sf.write(audio_buffer, y_slice, sr, format='WAV', subtype='PCM_16')
    audio_buffer.seek(0)
    # 构造API请求
    files = [('audio_input', ('audio_slice.wav', audio_buffer, 'application/octet-stream'))]
    payload = {"processing_type": "align", "language": WHISPER_LANGUAGE, "output": "raw"}
    start_time = time.time()
    rprint(f"[cyan]🎤 正在转录音频，语言:  <{WHISPER_LANGUAGE}> ...[/cyan]")
    headers = {'Authorization': f'Bearer {load_key("whisper.whisperX_302_api_key")}' }
    response = requests.request("POST", url, headers=headers, data=payload, files=files)
    response_json = response.json()
    # 对分段和词级时间戳进行全局偏移
    if start is not None:
        for segment in response_json['segments']:
            segment['start'] += start
            segment['end'] += start
            for word in segment.get('words', []):
                if 'start' in word:
                    word['start'] += start
                if 'end' in word:
                    word['end'] += start
    # 缓存结果
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(response_json, f, indent=4, ensure_ascii=False)
    elapsed_time = time.time() - start_time
    rprint(f"[green]✓ 转录完成，用时 {elapsed_time:.2f} 秒[/green]")
    return response_json

if __name__ == "__main__":
    # ------------
    # 测试主程序，直接转录_RAW_AUDIO_FILE
    # ------------
    result = transcribe_audio_302(_RAW_AUDIO_FILE, _RAW_AUDIO_FILE)
    rprint(result)
