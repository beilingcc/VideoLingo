# -*- coding: utf-8 -*-
"""
本模块通过 302.ai 提供的代理接口调用 OpenAI 的文本转语音 (TTS) 服务。

主要功能:
- 从配置文件加载 OpenAI TTS 的 API 密钥和所选的声音 (voice)。
- 验证所选声音是否为 OpenAI 支持的有效选项。
- 构建请求体并向代理 API 端点发送请求。
- 将返回的音频流保存到指定的本地文件。
- 使用装饰器提供了请求失败后的自动重试机制。

API 参考:
- OpenAI TTS 文档: https://platform.openai.com/docs/guides/text-to-speech/quickstart

注意:
    使用前请确保已在 `config.yaml` 文件中正确配置了 `openai_tts` 相关的 `api_key` 和 `voice`。
"""

from pathlib import Path
import requests
import json
from core.utils import load_key, except_handler

# OpenAI TTS 代理 API 的基础 URL
BASE_URL = "https://api.302.ai/v1/audio/speech"

# OpenAI TTS 支持的声音列表
VOICE_LIST = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

@except_handler("使用 OpenAI TTS 生成音频失败", retry=3, delay=1)
def openai_tts(text: str, save_path: str):
    """
    调用 OpenAI TTS API 将文本转换为语音并保存。

    Args:
        text (str): 需要转换为语音的文本。
        save_path (str): 音频文件的保存路径。

    Raises:
        ValueError: 如果配置文件中指定的声音无效。
        requests.exceptions.RequestException: 如果 API 请求失败。
    """
    # 从配置文件加载 API 密钥和声音设置
    api_key = load_key("openai_tts.api_key")
    voice = load_key("openai_tts.voice")

    # 校验声音是否有效
    if voice not in VOICE_LIST:
        raise ValueError(f"无效的声音: {voice}。请从 {VOICE_LIST} 中选择。")

    # 构建发送给 API 的请求体
    payload = json.dumps({
        "model": "tts-1",         # 使用的模型
        "input": text,            # 输入文本
        "voice": voice,           # 选择的声音
        "response_format": "wav"  # 希望返回的音频格式
    })
    
    # 设置请求头，包含授权信息
    headers = {
        'Authorization': f"Bearer {api_key}",
        'Content-Type': 'application/json'
    }
    
    # 创建保存路径的目录
    speech_file_path = Path(save_path)
    speech_file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 发送 POST 请求
    response = requests.post(BASE_URL, headers=headers, data=payload)
    
    # 处理响应
    if response.status_code == 200:
        # 请求成功，将音频内容写入文件
        with open(speech_file_path, 'wb') as f:
            f.write(response.content)
        print(f"音频已成功保存到 {speech_file_path}")
    else:
        # 请求失败，打印错误信息
        print(f"错误: 状态码 {response.status_code}")
        print(f"错误详情: {response.text}")

# --- 主程序入口，用于测试 ---
if __name__ == "__main__":
    test_text = "Hi! Welcome to VideoLingo! 这是一个测试。"
    output_file = "test_openai_tts.wav"
    
    print(f"正在使用 OpenAI TTS 生成音频，文本: '{test_text}'")
    openai_tts(test_text, output_file)
    print(f"测试完成，请检查文件 '{output_file}'。")