# -*- coding: utf-8 -*-
"""
本模块封装了对微软 Azure 文本转语音 (TTS) 服务的调用。

功能:
- 通过一个代理 API (`https://api.302.ai/cognitiveservices/v1`) 来访问 Azure TTS 服务。
- 从 `config.yaml` 配置文件中动态加载 API 密钥和所需的声音名称 (voice)。
- 使用 SSML (Speech Synthesis Markup Language) 格式构建请求体，这允许对语音合成进行更精细的控制，
  例如指定语言、声音、语速、音调等。
- 将输入的文本转换为 16kHz 采样率、16位深度的单声道 WAV 音频文件。

使用方法:
- 在 `config.yaml` 中配置 `azure_tts.api_key` 和 `azure_tts.voice`。
- 调用 `azure_tts(text, save_path)` 函数即可。

依赖:
- `requests`: 用于发送 HTTP POST 请求。
- `core.utils.load_key`: 用于安全、便捷地从配置文件加载配置项。
"""

# 导入第三方库
import requests  # 用于发送HTTP请求

# 导入项目内部模块
from core.utils import load_key, rprint  # 用于从配置文件加载密钥和设置，并进行格式化输出


def azure_tts(text: str, save_path: str) -> bool:
    """
    使用 Azure 的文本转语音（TTS）服务将文本转换为语音，并通过一个代理 API 进行调用。

    Args:
        text (str): 需要转换为语音的文本内容。
        save_path (str): 生成的音频文件的保存路径。

    Returns:
        bool: 成功返回 True，失败返回 False。
    """
    try:
        # 1. 从配置文件中加载 Azure TTS 的 API 密钥和所选的声音名称
        #    这种方式将敏感信息与代码分离，提高了安全性。
        api_key = load_key("azure_tts.api_key")
        voice = load_key("azure_tts.voice")
        if not api_key or not voice:
            rprint("[red]错误: Azure TTS 的 API 密钥或声音名称未在 config.yaml 中配置。")
            return False

        # 2. 代理 API 的 URL，该 URL 将请求转发到 Azure 认知服务
        url = "https://api.302.ai/cognitiveservices/v1"
        
        # 3. 构建符合 SSML（语音合成标记语言）格式的请求体
        #    SSML 允许更精细地控制语音的输出。这里指定了语言为中文，并使用了配置的声音。
        payload = f"""<speak version='1.0' xml:lang='zh-CN'><voice name='{voice}'>{text}</voice></speak>"""
        
        # 4. 设置 HTTP 请求头
        headers = {
           'Authorization': f'Bearer {api_key}',  # 使用 Bearer Token 进行身份验证
           'X-Microsoft-OutputFormat': 'riff-16khz-16bit-mono-pcm',  # 指定输出音频的格式：16kHz采样率、16位深度、单声道的PCM WAV格式
           'Content-Type': 'application/ssml+xml'  # 声明请求体的内容类型为SSML
        }

        # 5. 发送 POST 请求到 TTS 服务
        #    请求体(payload)需要被编码为 UTF-8 字节流。
        response = requests.post(url, headers=headers, data=payload.encode('utf-8'))
        response.raise_for_status()  # 如果HTTP状态码不是 2xx，则抛出异常

        # 6. 检查响应内容是否为空
        if not response.content:
            rprint("[red]错误: Azure TTS 服务返回了空的音频内容。")
            return False

        # 7. 将返回的音频内容写入到指定的文件中
        with open(save_path, 'wb') as f:
            f.write(response.content)
        # rprint(f"[green]Azure TTS 音频已保存到: {save_path}")
        return True

    except requests.exceptions.RequestException as e:
        rprint(f"[red]调用 Azure TTS 服务时发生网络错误: {e}")
        return False
    except Exception as e:
        rprint(f"[red]处理 Azure TTS 时发生未知错误: {e}")
        return False

# --- 测试代码 ---
if __name__ == "__main__":
    # 当该脚本作为主程序运行时，执行以下测试代码
    # 确保在运行前已在 config.yaml 中正确配置了 azure_tts.api_key 和 azure_tts.voice
    rprint("开始测试 Azure TTS 功能...")
    success = azure_tts("你好！欢迎使用 VideoLingo！这是一个测试。", "test_azure.wav")
    if success:
        rprint("[green]测试成功，请检查生成的 test_azure.wav 文件。")
    else:
        rprint("[red]测试失败。")