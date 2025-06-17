# -*- coding: utf-8 -*-
"""
本模块实现了通过调用 302.ai 提供的 Fish-TTS API 来进行文本转语音的功能。

主要功能:
- 从配置文件中加载 API 密钥和角色配置。
- 构建符合 API 要求的请求体。
- 发送 POST 请求到 302.ai 的 TTS 端点。
- 处理 API 响应，下载生成的音频文件并保存到本地。
- 使用装饰器提供了请求失败后的自动重试机制。

使用示例:
    `fish_tts("你好，欢迎使用 VideoLingo！", "output.wav")`

注意:
    使用前请确保已在 `config.yaml` 文件中正确配置了 `fish_tts` 相关的 `api_key`, `character` 和 `character_id_dict`。
"""

import requests
import json
from core.utils import load_key, except_handler

@except_handler("使用 302.ai Fish TTS 生成音频失败", retry=3, delay=1)
def fish_tts(text: str, save_as: str) -> bool:
    """
    调用 302.ai 的 Fish TTS API 将文本转换为语音并保存为文件。

    Args:
        text (str): 需要转换为语音的文本。
        save_as (str): 音频文件的保存路径。

    Returns:
        bool: 如果成功生成并保存音频，则返回 True，否则返回 False。

    Raises:
        requests.exceptions.RequestException: 当网络请求失败或服务器返回错误状态码时抛出。
        KeyError: 如果在配置文件中找不到所需的密钥或角色ID。
    """
    # 从配置文件加载 API 密钥和所选角色信息
    api_key = load_key("fish_tts.api_key")
    character = load_key("fish_tts.character")
    character_id_dict = load_key("fish_tts.character_id_dict")
    refer_id = character_id_dict[character]
    
    # API 的 URL 端点
    url = "https://api.302.ai/fish-audio/v1/tts"
    
    # 构建请求体 (payload)
    payload = json.dumps({
        "text": text,  # 要合成的文本
        "reference_id": refer_id,  # 参考角色的ID
        "chunk_length": 200,  # 文本分块长度
        "normalize": True,  # 是否对文本进行归一化处理
        "format": "wav",  # 输出音频格式
        "latency": "normal"  # 延迟模式
    })
    
    # 设置请求头，包括授权信息和内容类型
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    # 发送 POST 请求到 TTS API
    response = requests.post(url, headers=headers, data=payload)
    response.raise_for_status()  # 如果请求失败（状态码不是2xx），则抛出异常
    response_data = response.json()
    
    # 检查响应中是否包含音频文件的URL
    if "url" in response_data:
        # 如果有URL，则下载音频文件
        audio_response = requests.get(response_data["url"])
        audio_response.raise_for_status()  # 确保下载请求成功
        
        # 将下载的音频内容写入本地文件
        with open(save_as, "wb") as f:
            f.write(audio_response.content)
        # print(f"音频已成功保存到 {save_as}")
        return True
    
    # 如果响应中没有URL，说明请求可能出错了
    print(f"请求失败，API响应: {response_data}")
    return False

# --- 主程序入口，用于测试 ---
if __name__ == '__main__':
    # 测试文本
    test_text = "你好，这是一个测试。Welcome to VideoLingo!"
    # 保存文件名
    output_file = "test_fish_tts.wav"
    
    print(f"正在使用 Fish TTS 生成音频，文本内容: '{test_text}'")
    # 调用函数进行语音合成
    success = fish_tts(test_text, output_file)
    
    if success:
        print(f"测试成功！音频文件已保存为 '{output_file}'。")
    else:
        print("测试失败。未能生成音频文件。")

