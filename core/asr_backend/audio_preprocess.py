# ------------
# 本模块用于音频预处理，包括音量归一化、视频转音频、音频分割、转录结果处理等
# ------------
import os, subprocess
import pandas as pd
from typing import Dict, List, Tuple
from pydub import AudioSegment
from core.utils import *
from core.utils.models import *
from pydub import AudioSegment
from pydub.silence import detect_silence
from pydub.utils import mediainfo
from rich import print as rprint

# ------------
# 音量归一化
# ------------
def normalize_audio_volume(audio_path, output_path, target_db = -20.0, format = "wav"):
    audio = AudioSegment.from_file(audio_path)
    change_in_dBFS = target_db - audio.dBFS
    normalized_audio = audio.apply_gain(change_in_dBFS)
    normalized_audio.export(output_path, format=format)
    rprint(f"[green]✅ 音频音量已归一化: {audio.dBFS:.1f}dB → {target_db:.1f}dB[/green]")
    return output_path

# ------------
# 视频转音频（ffmpeg）
# ------------
def convert_video_to_audio(video_file):
    os.makedirs(_AUDIO_DIR, exist_ok=True)
    if not os.path.exists(_RAW_AUDIO_FILE):
        rprint(f"[blue]🎬➡️🎵 正在用FFmpeg高质量提取音频...[/blue]")
        subprocess.run([
            'ffmpeg', '-y', '-i', video_file, '-vn',
            '-c:a', 'libmp3lame', '-b:a', '32k',
            '-ar', '16000',
            '-ac', '1', 
            '-metadata', 'encoding=UTF-8', _RAW_AUDIO_FILE
        ], check=True, stderr=subprocess.PIPE)
        rprint(f"[green]🎬➡️🎵 <{video_file}> 已转为 <{_RAW_AUDIO_FILE}>\n[/green]")

# ------------
# 获取音频时长
# ------------
def get_audio_duration(audio_file):
    """用ffmpeg获取音频时长"""
    cmd = ['ffmpeg', '-i', audio_file]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, stderr = process.communicate()
    output = stderr.decode('utf-8', errors='ignore')
    try:
        duration_str = [line for line in output.split('\n') if 'Duration' in line][0]
        duration_parts = duration_str.split('Duration: ')[1].split(',')[0].split(':')
        duration = float(duration_parts[0])*3600 + float(duration_parts[1])*60 + float(duration_parts[2])
    except Exception as e:
        print(f"[red]❌ 获取音频时长失败: {e}[/red]")
        duration = 0
    return duration

# ------------
# 音频分割，自动寻找静默点
# ------------
def split_audio(audio_file, target_len = 30*60, win = 60):
    # 在 [target_len-win, target_len+win] 区间内用pydub检测静默，切分音频
    rprint(f"[blue]🎙️ 开始音频分割 {audio_file} {target_len} {win}[/blue]")
    audio = AudioSegment.from_file(audio_file)
    duration = float(mediainfo(audio_file)["duration"])
    if duration <= target_len + win:
        return [(0, duration)]
    segments, pos = [], 0.0
    safe_margin = 0.5  # 静默点前后安全边界，单位秒
    while pos < duration:
        if duration - pos <= target_len:
            segments.append((pos, duration)); break
        threshold = pos + target_len
        ws, we = int((threshold - win) * 1000), int((threshold + win) * 1000)
        # 获取完整的静默区间
        silence_regions = detect_silence(audio[ws:we], min_silence_len=int(safe_margin*1000), silence_thresh=-30)
        silence_regions = [(s/1000 + (threshold - win), e/1000 + (threshold - win)) for s, e in silence_regions]
        # 筛选长度足够且位置合适的静默区间
        valid_regions = [
            (start, end) for start, end in silence_regions 
            if (end - start) >= (safe_margin * 2) and threshold <= start + safe_margin <= threshold + win
        ]
        if valid_regions:
            start, end = valid_regions[0]
            split_at = start + safe_margin  # 在静默区间起始点后0.5秒处切分
        else:
            rprint(f"[yellow]⚠️ {audio_file} {threshold}s 未找到合适静默区，直接用阈值切分[/yellow]")
            split_at = threshold
        segments.append((pos, split_at)); pos = split_at
    rprint(f"[green]🎙️ 音频分割完成，共{len(segments)}段[/green]")
    return segments

# ------------
# 处理转录结果，整理为DataFrame
# ------------
def process_transcription(result):
    all_words = []
    for segment in result['segments']:
        # 获取说话人id
        speaker_id = segment.get('speaker_id', None)
        for word in segment['words']:
            # 检查单词长度
            if len(word["word"]) > 30:
                rprint(f"[yellow]⚠️ 检测到超长单词，跳过: {word['word']}[/yellow]")
                continue
            # 法语特殊处理
            word["word"] = word["word"].replace('»', '').replace('«', '')
            if 'start' not in word and 'end' not in word:
                if all_words:
                    # 没有时间戳，继承上一个单词的结束时间
                    word_dict = {
                        'text': word["word"],
                        'start': all_words[-1]['end'],
                        'end': all_words[-1]['end'],
                        'speaker_id': speaker_id
                    }
                    all_words.append(word_dict)
                else:
                    # 第一个词，向后找有时间戳的词
                    next_word = next((w for w in segment['words'] if 'start' in w and 'end' in w), None)
                    if next_word:
                        word_dict = {
                            'text': word["word"],
                            'start': next_word["start"],
                            'end': next_word["end"],
                            'speaker_id': speaker_id
                        }
                        all_words.append(word_dict)
                    else:
                        raise Exception(f"未找到下一个带时间戳的词: {word}")
            else:
                # 正常情况
                word_dict = {
                    'text': f'{word["word"]}',
                    'start': word.get('start', all_words[-1]['end'] if all_words else 0),
                    'end': word['end'],
                    'speaker_id': speaker_id
                }
                all_words.append(word_dict)
    return pd.DataFrame(all_words)

# ------------
# 保存结果到Excel
# ------------
def save_results(df):
    os.makedirs('output/log', exist_ok=True)
    # 删除空文本行
    initial_rows = len(df)
    df = df[df['text'].str.len() > 0]
    removed_rows = initial_rows - len(df)
    if removed_rows > 0:
        rprint(f"[blue]ℹ️ 移除{removed_rows}行空文本[/blue]")
    # 检查超长单词
    long_words = df[df['text'].str.len() > 30]
    if not long_words.empty:
        rprint(f"[yellow]⚠️ 检测到{len(long_words)}个超长单词，已移除[/yellow]")
        df = df[df['text'].str.len() <= 30]
    df['text'] = df['text'].apply(lambda x: f'"{x}"')
    df.to_excel(_2_CLEANED_CHUNKS, index=False)
    rprint(f"[green]📊 Excel已保存到 {_2_CLEANED_CHUNKS}[/green]")

# ------------
# 保存检测到的语言
# ------------
def save_language(language):
    update_key("whisper.detected_language", language)