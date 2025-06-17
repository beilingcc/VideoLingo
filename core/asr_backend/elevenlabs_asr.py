# ------------
# 本模块用于调用elevenlabs的API进行音频转录，并将结果转为whisper格式
# ------------
import os
import json
import time
import requests
import tempfile
import librosa
import soundfile as sf
from rich import print as rprint
from core.utils import *

# ------------
# ISO 639-2转1位语言码映射
# ------------
iso_639_2_to_1 = {
    "eng": "en",
    "fra": "fr", 
    "deu": "de",
    "ita": "it",
    "spa": "es",
    "rus": "ru",
    "kor": "ko",
    "jpn": "ja",
    "zho": "zh",
    "yue": "zh"
}

# ------------
# elevenlabs转whisper格式
# ------------
SPLIT_GAP = 1
def elev2whisper(elev_json, word_level_timestamp = False):
    words = elev_json.get("words", [])
    if not words:
        return {"segments": []}
    segments, seg = [], {
        "text": "",                     # 累积文本
        "start": words[0]["start"],     # 段起始时间
        "end": words[0]["end"],         # 段结束时间
        "speaker_id": words[0]["speaker_id"],
        "words": []                       # 可选词级信息
    }
    for prev, nxt in zip(words, words[1:] + [None]):  # 两两配对
        seg["text"] += prev["text"]
        seg["end"] = prev["end"]
        if word_level_timestamp:
            seg["words"].append({"text": prev["text"], "start": prev["start"], "end": prev["end"]})
        # 判断是否分段
        if nxt is None or (nxt["start"] - prev["end"] > SPLIT_GAP) or (nxt["speaker_id"] != seg["speaker_id"]):
            seg["text"] = seg["text"].strip()
            if not word_level_timestamp:
                seg.pop("words")
            segments.append(seg)
            if nxt is not None:  # 新建下一个段
                seg = {
                    "text": "",
                    "start": nxt["start"],
                    "end": nxt["end"],
                    "speaker_id": nxt["speaker_id"],
                    "words": []
                }
    return {"segments": segments}

# ------------
# elevenlabs音频转录主流程
# ------------
def transcribe_audio_elevenlabs(raw_audio_path, vocal_audio_path, start = None, end = None):
    rprint(f"[cyan]🎤 开始elevenlabs音频转录，文件路径: {vocal_audio_path}[/cyan]")
    LOG_FILE = f"output/log/elevenlabs_transcribe_{start}_{end}.json"
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # 读取音频并切片
    y, sr = librosa.load(vocal_audio_path, sr=16000)
    audio_duration = len(y) / sr
    if start is None or end is None:
        start = 0
        end = audio_duration
    # 切片
    start_sample = int(start * sr)
    end_sample = int(end * sr)
    y_slice = y[start_sample:end_sample]
    # 临时文件保存切片
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
        temp_filepath = temp_file.name
        sf.write(temp_filepath, y_slice, sr, format='MP3')
    try:
        api_key = load_key("whisper.elevenlabs_api_key")
        base_url = "https://api.elevenlabs.io/v1/speech-to-text"
        headers = {"xi-api-key": api_key}
        data = {
            "model_id": "scribe_v1",
            "timestamps_granularity": "word",
            "language_code": load_key("whisper.language"),
            "diarize": True,
            "num_speakers": None,
            "tag_audio_events": False
        }
        with open(temp_filepath, 'rb') as audio_file:
            files = {"file": (os.path.basename(temp_filepath), audio_file, 'audio/mpeg')}
            start_time = time.time()
            response = requests.post(base_url, headers=headers, data=data, files=files)
        rprint(f"[yellow]API请求已发送，状态码: {response.status_code}[/yellow]")
        result = response.json()
        # 保存检测到的语言
        detected_language = iso_639_2_to_1.get(result["language_code"], result["language_code"])
        update_key("whisper.detected_language", detected_language)
        # 时间戳全局偏移
        if start is not None and 'words' in result:
            for word in result['words']:
                if 'start' in word:
                    word['start'] += start
                if 'end' in word:
                    word['end'] += start
        rprint(f"[green]✓ 转录完成，用时 {time.time() - start_time:.2f} 秒[/green]")
        parsed_result = elev2whisper(result)
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(parsed_result, f, indent=4, ensure_ascii=False)
        return parsed_result
    finally:
        # 清理临时文件
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)

if __name__ == "__main__":
    # ------------
    # 测试主程序，交互式输入音频路径和语言
    # ------------
    file_path = input("请输入本地音频文件路径（mp3格式）: ")
    language = input("请输入转录语言代码（en/zh/其他）: ")
    result = transcribe_audio_elevenlabs(file_path, language_code=language)
    print(result)
    # 保存结果
    with open("output/transcript.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
